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

def main():
    """CLI entry point for local testing and batch processing."""
    import argparse

    parser = argparse.ArgumentParser(description="Invoice Renamer V5")
    parser.add_argument("files", nargs="+", help="Files to process")
    parser.add_argument("--rename", action="store_true", help="Actually rename files")
    parser.add_argument("--no-vat", action="store_true", help="Skip VAT quarter")
    parser.add_argument("--no-learn", action="store_true", help="Skip supplier learning prompts")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    vision_client = _get_vision_client()
    pipeline = InvoicePipeline(vision_client=vision_client)

    for filepath in args.files:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            continue

        result = pipeline.process_file(
            filepath,
            include_vat_quarter=not args.no_vat,
            debug=args.debug,
        )

        if result.errors:
            print(f"ERRORS for {result.original_filename}: {result.errors}")
            continue

        # If supplier is unknown, offer interactive learning
        if not args.no_learn and result.invoice_data.supplier == "Unknown" and result.raw_text:
            from core.extractors.supplier_learner import prompt_supplier_info
            learned = prompt_supplier_info(result.raw_text)
            if learned:
                result = pipeline.reprocess_with_supplier(
                    result,
                    supplier_name=learned['display_name'],
                    supplier_template=learned,
                )
                # Reload supplier extractor to pick up the new template
                pipeline.supplier_extractor = __import__(
                    'core.extractors.supplier', fromlist=['SupplierExtractor']
                ).SupplierExtractor()

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

        if args.rename:
            dirpath = os.path.dirname(filepath)
            new_path = os.path.join(dirpath, result.new_filename)
            if not os.path.exists(new_path):
                os.rename(filepath, new_path)
                print(f"  RENAMED: {result.new_filename}")
            else:
                print(f"  SKIPPED: {result.new_filename} already exists")


if __name__ == "__main__":
    main()
