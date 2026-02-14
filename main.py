"""
Invoice Renamer V5 - Cloud Function Entry Point
================================================

Modular invoice processing pipeline:
- pdfplumber for native PDFs (free, 100% accurate)
- Google Cloud Vision OCR for scanned documents
- dateparser for multilingual date extraction
- price-parser for robust amount/currency parsing
- JSON-driven supplier templates (no hardcoded patterns)

Format: [Prefix_]SupplierName_#InvoiceNumber_DD-MM-YYYY_AmountCurrency[_Q1-2025].ext
"""

import json
import logging
import os

from core.pipeline import InvoicePipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def process_invoice_http(request):
    """
    HTTP Cloud Function entry point.
    Expects multipart form data with file upload,
    or JSON body with file_path for local processing.
    """
    try:
        # Initialize pipeline (Vision client is optional for native PDFs)
        vision_client = _get_vision_client()
        pipeline = InvoicePipeline(vision_client=vision_client)

        content_type = request.content_type or ''

        if 'multipart/form-data' in content_type:
            # File upload
            file = request.files.get('file')
            if not file:
                return json.dumps({"error": "No file uploaded"}), 400

            # Save temporarily
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
                file.save(tmp.name)
                result = pipeline.process_file(tmp.name)
                os.unlink(tmp.name)

        elif 'application/json' in content_type:
            # JSON body with file_path
            data = request.get_json()
            filepath = data.get('file_path')
            if not filepath:
                return json.dumps({"error": "file_path required"}), 400

            include_vat = data.get('include_vat_quarter', True)
            debug = data.get('debug', False)
            result = pipeline.process_file(filepath, include_vat_quarter=include_vat, debug=debug)

        else:
            return json.dumps({"error": "Unsupported content type"}), 400

        response = {
            "original_filename": result.original_filename,
            "new_filename": result.new_filename,
            "supplier": result.invoice_data.supplier,
            "invoice_number": result.invoice_data.invoice_number,
            "date": result.invoice_data.format_date(),
            "amount": str(result.invoice_data.amount) if result.invoice_data.amount else None,
            "currency": result.invoice_data.currency,
            "confidence": result.invoice_data.confidence,
            "extraction_method": result.invoice_data.extraction_method,
            "vat_quarter": result.vat_quarter,
            "accounting_prefix": result.accounting_prefix,
            "errors": result.errors,
        }

        # Flag when supplier was not recognized, so the caller can trigger learning
        if result.invoice_data.supplier == "Unknown":
            response["supplier_unknown"] = True
            # Include text preview for the learning UI
            if result.raw_text:
                lines = [l.strip() for l in result.raw_text.split('\n') if l.strip()]
                response["text_preview"] = lines[:15]

        return json.dumps(response), 200

    except Exception as e:
        logger.error(f"Error processing invoice: {e}", exc_info=True)
        return json.dumps({"error": str(e)}), 500


def learn_supplier_http(request):
    """
    HTTP endpoint to register a new supplier.
    Expects JSON body:
    {
        "supplier_name": "Acme Corp",
        "default_currency": "USD",           // optional
        "detection_patterns": ["Acme Corp"]   // optional, auto-detected if omitted
    }
    """
    try:
        if 'application/json' not in (request.content_type or ''):
            return json.dumps({"error": "Content-Type must be application/json"}), 400

        data = request.get_json()
        supplier_name = data.get('supplier_name')
        if not supplier_name:
            return json.dumps({"error": "supplier_name is required"}), 400

        from core.extractors.supplier_learner import create_supplier_template, save_supplier_template

        template = create_supplier_template(
            supplier_name=supplier_name,
            text=data.get('text', ''),
            default_currency=data.get('default_currency'),
            detection_patterns=data.get('detection_patterns'),
        )

        saved = save_supplier_template(template)

        return json.dumps({
            "saved": saved,
            "template": template,
            "message": f"Supplier '{supplier_name}' {'saved' if saved else 'already exists'}",
        }), 200 if saved else 409

    except Exception as e:
        logger.error(f"Error learning supplier: {e}", exc_info=True)
        return json.dumps({"error": str(e)}), 500


def process_drive_http(request):
    """
    HTTP endpoint to process invoices from Google Drive.
    Expects JSON body:
    {
        "folder_id": "1AbCdEf...",          // Drive folder ID
        "file_id": "1XyZ...",               // OR single file ID
        "rename": false,                     // rename files in Drive (default: false)
        "move_to": "1FolderID...",           // move processed files to folder (optional)
        "include_vat_quarter": true
    }
    """
    try:
        if 'application/json' not in (request.content_type or ''):
            return json.dumps({"error": "Content-Type must be application/json"}), 400

        data = request.get_json()
        folder_id = data.get('folder_id')
        file_id = data.get('file_id')

        if not folder_id and not file_id:
            return json.dumps({"error": "folder_id or file_id required"}), 400

        from core.drive import DriveConnector
        import tempfile

        drive = DriveConnector()
        vision_client = _get_vision_client()
        pipeline = InvoicePipeline(vision_client=vision_client)
        include_vat = data.get('include_vat_quarter', True)
        do_rename = data.get('rename', False)
        move_to = data.get('move_to')

        # Collect files to process
        if file_id:
            files = [{"id": file_id}]
        else:
            files = drive.list_invoices(folder_id)

        results = []
        with tempfile.TemporaryDirectory(prefix="invoice_drive_") as tmpdir:
            for f in files:
                fid = f['id']
                local_path = drive.download(fid, dest_dir=tmpdir)

                result = pipeline.process_file(local_path, include_vat_quarter=include_vat)

                entry = {
                    "drive_file_id": fid,
                    "original_filename": result.original_filename,
                    "new_filename": result.new_filename,
                    "supplier": result.invoice_data.supplier,
                    "invoice_number": result.invoice_data.invoice_number,
                    "date": result.invoice_data.format_date(),
                    "amount": str(result.invoice_data.amount) if result.invoice_data.amount else None,
                    "currency": result.invoice_data.currency,
                    "confidence": result.invoice_data.confidence,
                    "vat_quarter": result.vat_quarter,
                    "errors": result.errors,
                    "renamed": False,
                    "moved": False,
                }

                if result.invoice_data.supplier == "Unknown":
                    entry["supplier_unknown"] = True

                # Rename in Drive if requested
                if do_rename and not result.errors:
                    drive.rename(fid, result.new_filename)
                    entry["renamed"] = True

                # Move to processed folder if requested
                if move_to and not result.errors:
                    drive.move_to_folder(fid, move_to)
                    entry["moved"] = True

                results.append(entry)

                # Clean up local file
                try:
                    os.unlink(local_path)
                except OSError:
                    pass

        return json.dumps({
            "processed": len(results),
            "results": results,
        }), 200

    except Exception as e:
        logger.error(f"Error processing Drive invoices: {e}", exc_info=True)
        return json.dumps({"error": str(e)}), 500


def _get_vision_client():
    """Get Google Cloud Vision client if credentials are available."""
    try:
        from google.cloud import vision
        return vision.ImageAnnotatorClient()
    except Exception:
        logger.warning("Google Cloud Vision not available - only native PDFs will work")
        return None


# ─────────────────────────────────────────────────────────
# CLI mode for local testing
# ─────────────────────────────────────────────────────────

def _print_result(result):
    """Print extraction result to console."""
    print(f"{result.original_filename} -> {result.new_filename}")
    print(f"  Supplier: {result.invoice_data.supplier}")
    print(f"  Invoice#: {result.invoice_data.invoice_number}")
    print(f"  Date: {result.invoice_data.format_date()}")
    print(f"  Amount: {result.invoice_data.format_amount()}")
    print(f"  Confidence: {result.invoice_data.confidence:.0%}")
    print(f"  Method: {result.invoice_data.extraction_method}")
    if result.vat_quarter:
        print(f"  VAT Quarter: {result.vat_quarter}")
    print()


def _handle_supplier_learning(result, pipeline, no_learn=False):
    """Handle interactive supplier learning for unknown suppliers."""
    if no_learn or result.invoice_data.supplier != "Unknown" or not result.raw_text:
        return result

    from core.extractors.supplier_learner import prompt_supplier_info
    learned = prompt_supplier_info(result.raw_text)
    if learned:
        result = pipeline.reprocess_with_supplier(
            result,
            supplier_name=learned['display_name'],
            supplier_template=learned,
        )
        # Reload supplier extractor to pick up the new template
        from core.extractors.supplier import SupplierExtractor
        pipeline.supplier_extractor = SupplierExtractor()

    return result


def main():
    """CLI entry point for local testing and batch processing."""
    import argparse

    parser = argparse.ArgumentParser(description="Invoice Renamer V5")
    subparsers = parser.add_subparsers(dest="command")

    # ── Local files command (default) ─────────────────────
    local_parser = subparsers.add_parser("local", help="Process local files")
    local_parser.add_argument("files", nargs="+", help="Files to process")
    local_parser.add_argument("--rename", action="store_true", help="Actually rename files")
    local_parser.add_argument("--no-vat", action="store_true", help="Skip VAT quarter")
    local_parser.add_argument("--no-learn", action="store_true", help="Skip supplier learning prompts")
    local_parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    # ── Google Drive command ──────────────────────────────
    drive_parser = subparsers.add_parser("drive", help="Process invoices from Google Drive")
    drive_parser.add_argument("folder_id", help="Google Drive folder ID")
    drive_parser.add_argument("--rename", action="store_true", help="Rename files in Drive")
    drive_parser.add_argument("--move-to", help="Move processed files to this Drive folder ID")
    drive_parser.add_argument("--no-vat", action="store_true", help="Skip VAT quarter")
    drive_parser.add_argument("--no-learn", action="store_true", help="Skip supplier learning prompts")
    drive_parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    # Also support the old direct-files syntax (no subcommand)
    parser.add_argument("files", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--rename", action="store_true", help="Actually rename files")
    parser.add_argument("--no-vat", action="store_true", help="Skip VAT quarter")
    parser.add_argument("--no-learn", action="store_true", help="Skip supplier learning prompts")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Route to the right handler
    if args.command == "drive":
        _main_drive(args)
    elif args.command == "local":
        _main_local(args)
    elif args.files:
        # Backward-compat: direct file args without subcommand
        _main_local(args)
    else:
        parser.print_help()


def _main_local(args):
    """Process local files."""
    vision_client = _get_vision_client()
    pipeline = InvoicePipeline(vision_client=vision_client)

    for filepath in args.files:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            continue

        result = pipeline.process_file(
            filepath,
            include_vat_quarter=not args.no_vat,
            debug=getattr(args, 'debug', False),
        )

        if result.errors:
            print(f"ERRORS for {result.original_filename}: {result.errors}")
            continue

        result = _handle_supplier_learning(result, pipeline, no_learn=args.no_learn)
        _print_result(result)

        if args.rename:
            dirpath = os.path.dirname(filepath)
            new_path = os.path.join(dirpath, result.new_filename)
            if not os.path.exists(new_path):
                os.rename(filepath, new_path)
                print(f"  RENAMED: {result.new_filename}")
            else:
                print(f"  SKIPPED: {result.new_filename} already exists")


def _main_drive(args):
    """Process invoices from Google Drive."""
    import tempfile

    try:
        from core.drive import DriveConnector
    except ImportError as e:
        print(f"Google Drive dependencies missing: {e}")
        print("Install with: pip install google-api-python-client google-auth-oauthlib")
        return

    print(f"Connecting to Google Drive...")
    drive = DriveConnector()

    print(f"Listing invoices in folder {args.folder_id}...")
    files = drive.list_invoices(args.folder_id)

    if not files:
        print("No invoice files found in this folder.")
        return

    print(f"Found {len(files)} invoice(s):\n")
    for f in files:
        print(f"  {f['name']} ({f['mimeType']})")
    print()

    vision_client = _get_vision_client()
    pipeline = InvoicePipeline(vision_client=vision_client)

    with tempfile.TemporaryDirectory(prefix="invoice_drive_") as tmpdir:
        for f in files:
            print(f"--- Processing: {f['name']} ---")

            local_path = drive.download(f['id'], dest_dir=tmpdir)

            result = pipeline.process_file(
                local_path,
                include_vat_quarter=not args.no_vat,
                debug=args.debug,
            )

            if result.errors:
                print(f"ERRORS: {result.errors}")
                continue

            result = _handle_supplier_learning(result, pipeline, no_learn=args.no_learn)
            _print_result(result)

            # Rename in Drive
            if args.rename:
                drive.rename(f['id'], result.new_filename)
                print(f"  RENAMED in Drive: {result.new_filename}")

            # Move to processed folder
            if args.move_to:
                drive.move_to_folder(f['id'], args.move_to)
                print(f"  MOVED to folder: {args.move_to}")

            # Clean up local temp
            try:
                os.unlink(local_path)
            except OSError:
                pass

    print(f"\nDone! Processed {len(files)} invoice(s).")


if __name__ == "__main__":
    main()
