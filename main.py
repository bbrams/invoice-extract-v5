"""
Invoice Renamer V5 - Cloud Function Entry Point
================================================

Hybrid architecture:
- Backend Python Cloud Function (this file)
- Frontend Google Drive Add-on (Apps Script, in apps_script/)

Security: API key validation on every HTTP request.
Features: dry_run, batch, multi-company, correlation ID, structured logging.

Format: [Prefix_]SupplierName_#InvoiceNumber_DD-MM-YYYY_AmountCurrency[_Q1-2025].ext
"""

import hmac
import json
import logging
import os
import tempfile
import uuid
from functools import lru_cache

from core.pipeline import InvoicePipeline
from core.models import ProcessRequest

# ─────────────────────────────────────────────────────────
# Structured JSON logging
# ─────────────────────────────────────────────────────────

class StructuredFormatter(logging.Formatter):
    """JSON log formatter for Cloud Logging."""
    def format(self, record):
        log_entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "timestamp": self.formatTime(record),
        }
        if hasattr(record, 'correlation_id'):
            log_entry["correlation_id"] = record.correlation_id
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Security helpers
# ─────────────────────────────────────────────────────────

def _verify_api_key(request) -> bool:
    """
    Verify X-API-Key header against configured secret.
    Key is stored in INVOICE_API_KEY env var (set via Secret Manager).
    """
    expected = os.environ.get('INVOICE_API_KEY')
    if not expected:
        logger.warning("INVOICE_API_KEY not set - running in INSECURE dev mode")
        return True
    provided = request.headers.get('X-API-Key', '')
    return hmac.compare_digest(provided, expected)


def _make_response(body: dict, status: int, correlation_id: str = None):
    """Build JSON response with proper headers."""
    if correlation_id:
        body["correlation_id"] = correlation_id
    return (
        json.dumps(body, default=str),
        status,
        {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, X-API-Key',
        },
    )


def _handle_cors(request):
    """Handle CORS preflight requests."""
    if request.method == 'OPTIONS':
        return _make_response({}, 204)
    return None


# ─────────────────────────────────────────────────────────
# Cached pipeline singleton (avoids cold-start penalty)
# ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_pipeline():
    """Cached pipeline - created once, reused across requests."""
    vision_client = _get_vision_client()
    return InvoicePipeline(vision_client=vision_client)


def _get_vision_client():
    """Get Google Cloud Vision client if credentials are available."""
    try:
        from google.cloud import vision
        return vision.ImageAnnotatorClient()
    except Exception:
        logger.warning("Google Cloud Vision not available - only native PDFs will work")
        return None


# ─────────────────────────────────────────────────────────
# Drive helpers (use caller's access token when provided)
# ─────────────────────────────────────────────────────────

def _build_drive_service(access_token: str = None):
    """
    Build Drive API service.
    - If access_token provided (from Apps Script): use it
    - Otherwise: fall back to server credentials
    """
    from googleapiclient.discovery import build

    if access_token:
        from google.oauth2.credentials import Credentials
        creds = Credentials(token=access_token)
        return build('drive', 'v3', credentials=creds)

    from core.drive import DriveConnector
    connector = DriveConnector()
    return connector.service


# ─────────────────────────────────────────────────────────
# HTTP ENDPOINT: Process invoice(s) from Drive
# ─────────────────────────────────────────────────────────

def process_invoice_http(request):
    """
    Main HTTP Cloud Function entry point.

    Accepts JSON body:
    {
        "file_id": "1XyZ...",
        "folder_id": "1AbC...",
        "company_id": "brams_tech_llc",
        "dry_run": true,
        "rename": true,
        "move_to": "1FolderID...",
        "include_vat_quarter": true,
        "access_token": "ya29.xxx"
    }

    Also accepts multipart/form-data with file upload (backward compat).
    """
    correlation_id = str(uuid.uuid4())[:8]

    cors = _handle_cors(request)
    if cors:
        return cors

    if not _verify_api_key(request):
        logger.warning("Rejected: invalid API key", extra={'correlation_id': correlation_id})
        return _make_response({"error": "Unauthorized: invalid API key"}, 401, correlation_id)

    try:
        content_type = request.content_type or ''
        pipeline = _get_pipeline()

        # Multipart file upload (backward compat)
        if 'multipart/form-data' in content_type:
            return _handle_file_upload(request, pipeline, correlation_id)

        if 'application/json' not in content_type:
            return _make_response(
                {"error": "Content-Type must be application/json or multipart/form-data"},
                400, correlation_id)

        data = request.get_json(silent=True)
        if not data:
            return _make_response({"error": "Empty or invalid JSON body"}, 400, correlation_id)

        # Validate request payload
        try:
            req = ProcessRequest(**{k: v for k, v in data.items()
                                    if k in ProcessRequest.model_fields})
        except Exception as e:
            return _make_response({"error": f"Invalid request: {e}"}, 400, correlation_id)

        if not req.file_id and not req.folder_id:
            return _make_response({"error": "file_id or folder_id required"}, 400, correlation_id)

        access_token = data.get('access_token')
        drive_service = _build_drive_service(access_token)

        # Collect files to process
        if req.file_id:
            files = [{"id": req.file_id}]
        else:
            files = _list_drive_invoices(drive_service, req.folder_id)

        if len(files) > 50:
            return _make_response(
                {"error": f"Too many files ({len(files)}). Max 50 per request."},
                400, correlation_id)

        logger.info(f"Processing {len(files)} file(s), dry_run={req.dry_run}, company={req.company_id}",
                    extra={'correlation_id': correlation_id})

        results = []
        with tempfile.TemporaryDirectory(prefix="invoice_") as tmpdir:
            for f in files:
                entry = _process_single_drive_file(
                    drive_service=drive_service,
                    pipeline=pipeline,
                    file_info=f,
                    tmpdir=tmpdir,
                    req=req,
                    correlation_id=correlation_id,
                )
                results.append(entry)

        return _make_response({
            "processed": len(results),
            "dry_run": req.dry_run,
            "results": results,
        }, 200, correlation_id)

    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True,
                     extra={'correlation_id': correlation_id})
        return _make_response({"error": str(e)}, 500, correlation_id)


def _list_drive_invoices(drive_service, folder_id: str, max_results: int = 100) -> list:
    """List invoice files (PDF, images) in a Drive folder."""
    invoice_mimes = {
        'application/pdf', 'image/jpeg', 'image/png', 'image/tiff', 'image/bmp',
    }
    mime_filter = " or ".join(f"mimeType='{m}'" for m in invoice_mimes)
    query = f"'{folder_id}' in parents and ({mime_filter}) and trashed=false"

    results = drive_service.files().list(
        q=query,
        pageSize=max_results,
        fields="files(id, name, mimeType, modifiedTime)",
        orderBy="modifiedTime desc",
    ).execute()
    return results.get('files', [])


def _process_single_drive_file(
    drive_service,
    pipeline: InvoicePipeline,
    file_info: dict,
    tmpdir: str,
    req: ProcessRequest,
    correlation_id: str,
) -> dict:
    """Process a single Drive file through the full pipeline."""
    fid = file_info['id']
    entry = {
        "drive_file_id": fid,
        "original_filename": file_info.get('name', 'unknown'),
        "new_filename": "",
        "supplier": None,
        "invoice_number": None,
        "date": None,
        "amount": None,
        "currency": None,
        "confidence": 0.0,
        "vat_quarter": None,
        "errors": [],
        "renamed": False,
        "moved": False,
        "dry_run": req.dry_run,
    }

    try:
        # Step 1: Download
        local_path = _download_drive_file(drive_service, fid, tmpdir)
        entry["original_filename"] = os.path.basename(local_path)

        # Step 2: Process through pipeline
        result = pipeline.process_file(
            local_path,
            include_vat_quarter=req.include_vat_quarter,
            company_id=req.company_id,
            debug=req.debug,
        )

        entry.update({
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
        })

        if result.invoice_data.supplier == "Unknown":
            entry["supplier_unknown"] = True

        # Step 3: Rename in Drive (unless dry_run)
        if req.rename and not req.dry_run and not result.errors:
            try:
                drive_service.files().update(
                    fileId=fid, body={"name": result.new_filename}, fields="id,name"
                ).execute()
                entry["renamed"] = True
            except Exception as e:
                entry["errors"].append(f"Drive rename failed: {e}")

        # Step 4: Move to processed folder (unless dry_run)
        if req.move_to and not req.dry_run and not result.errors:
            try:
                file_meta = drive_service.files().get(fileId=fid, fields='parents').execute()
                prev_parents = ",".join(file_meta.get('parents', []))
                drive_service.files().update(
                    fileId=fid,
                    addParents=req.move_to,
                    removeParents=prev_parents,
                    fields='id,name,parents',
                ).execute()
                entry["moved"] = True
            except Exception as e:
                entry["errors"].append(f"Drive move failed: {e}")

        # Clean up
        try:
            os.unlink(local_path)
        except OSError:
            pass

    except Exception as e:
        logger.error(f"Error processing file {fid}: {e}",
                     exc_info=True, extra={'correlation_id': correlation_id})
        entry["errors"].append(str(e))

    return entry


def _download_drive_file(drive_service, file_id: str, dest_dir: str) -> str:
    """Download a single file from Drive to a local temp path."""
    import io as _io
    from googleapiclient.http import MediaIoBaseDownload

    meta = drive_service.files().get(fileId=file_id, fields="name").execute()
    filename = meta['name']
    local_path = os.path.join(dest_dir, filename)

    request = drive_service.files().get_media(fileId=file_id)
    with open(local_path, 'wb') as f:
        downloader = MediaIoBaseDownload(_io.FileIO(f.fileno(), 'wb'), request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    return local_path


def _handle_file_upload(request, pipeline, correlation_id):
    """Handle multipart file upload (backward compatibility)."""
    file = request.files.get('file')
    if not file:
        return _make_response({"error": "No file uploaded"}, 400, correlation_id)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.bmp'):
        return _make_response({"error": f"Unsupported file type: {ext}"}, 400, correlation_id)

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        file.save(tmp.name)
        try:
            result = pipeline.process_file(tmp.name)
        finally:
            os.unlink(tmp.name)

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

    if result.invoice_data.supplier == "Unknown":
        response["supplier_unknown"] = True
        if result.raw_text:
            lines = [l.strip() for l in result.raw_text.split('\n') if l.strip()]
            response["text_preview"] = lines[:15]

    return _make_response(response, 200, correlation_id)


# ─────────────────────────────────────────────────────────
# HTTP ENDPOINT: Learn new supplier
# ─────────────────────────────────────────────────────────

def learn_supplier_http(request):
    """
    HTTP endpoint to register a new supplier.
    Expects JSON body:
    {
        "supplier_name": "Acme Corp",
        "default_currency": "USD",
        "detection_patterns": ["Acme Corp"]
    }
    """
    correlation_id = str(uuid.uuid4())[:8]

    cors = _handle_cors(request)
    if cors:
        return cors

    if not _verify_api_key(request):
        return _make_response({"error": "Unauthorized"}, 401, correlation_id)

    try:
        if 'application/json' not in (request.content_type or ''):
            return _make_response({"error": "Content-Type must be application/json"}, 400, correlation_id)

        data = request.get_json(silent=True)
        if not data:
            return _make_response({"error": "Empty JSON body"}, 400, correlation_id)

        supplier_name = data.get('supplier_name', '').strip()
        if not supplier_name or len(supplier_name) > 100:
            return _make_response({"error": "supplier_name required (max 100 chars)"}, 400, correlation_id)

        from core.extractors.supplier_learner import create_supplier_template, save_supplier_template

        template = create_supplier_template(
            supplier_name=supplier_name,
            text=data.get('text', ''),
            default_currency=data.get('default_currency'),
            detection_patterns=data.get('detection_patterns'),
        )

        saved = save_supplier_template(template)

        return _make_response({
            "saved": saved,
            "template": template,
            "message": f"Supplier '{supplier_name}' {'saved' if saved else 'already exists'}",
        }, 200 if saved else 409, correlation_id)

    except Exception as e:
        logger.error(f"Error learning supplier: {e}", exc_info=True,
                     extra={'correlation_id': correlation_id})
        return _make_response({"error": str(e)}, 500, correlation_id)


# ─────────────────────────────────────────────────────────
# HTTP ENDPOINT: Health check
# ─────────────────────────────────────────────────────────

def health_http(request):
    """Health check endpoint for monitoring."""
    return _make_response({"status": "ok", "version": "5.0"}, 200)


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
        from core.extractors.supplier import SupplierExtractor
        pipeline.supplier_extractor = SupplierExtractor()

    return result


def main():
    """CLI entry point for local testing and batch processing."""
    import argparse

    parser = argparse.ArgumentParser(description="Invoice Renamer V5")
    subparsers = parser.add_subparsers(dest="command")

    # Local files command
    local_parser = subparsers.add_parser("local", help="Process local files")
    local_parser.add_argument("files", nargs="+", help="Files to process")
    local_parser.add_argument("--rename", action="store_true", help="Actually rename files")
    local_parser.add_argument("--no-vat", action="store_true", help="Skip VAT quarter")
    local_parser.add_argument("--no-learn", action="store_true", help="Skip supplier learning prompts")
    local_parser.add_argument("--company", default=None, help="Company ID for VAT calendar")
    local_parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    # Google Drive command
    drive_parser = subparsers.add_parser("drive", help="Process invoices from Google Drive")
    drive_parser.add_argument("folder_id", help="Google Drive folder ID")
    drive_parser.add_argument("--rename", action="store_true", help="Rename files in Drive")
    drive_parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    drive_parser.add_argument("--move-to", help="Move processed files to this Drive folder ID")
    drive_parser.add_argument("--no-vat", action="store_true", help="Skip VAT quarter")
    drive_parser.add_argument("--no-learn", action="store_true", help="Skip supplier learning prompts")
    drive_parser.add_argument("--company", default=None, help="Company ID for VAT calendar")
    drive_parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if hasattr(args, 'debug') and args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "drive":
        _main_drive(args)
    elif args.command == "local":
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
            company_id=args.company,
            debug=args.debug,
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
    try:
        from core.drive import DriveConnector
    except ImportError as e:
        print(f"Google Drive dependencies missing: {e}")
        print("Install with: pip install google-api-python-client google-auth-oauthlib")
        return

    print("Connecting to Google Drive...")
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
                company_id=args.company,
                debug=args.debug,
            )

            if result.errors:
                print(f"ERRORS: {result.errors}")
                continue

            result = _handle_supplier_learning(result, pipeline, no_learn=args.no_learn)
            _print_result(result)

            if args.dry_run:
                print("  [DRY RUN] No changes applied.")
                continue

            if args.rename:
                drive.rename(f['id'], result.new_filename)
                print(f"  RENAMED in Drive: {result.new_filename}")

            if args.move_to:
                drive.move_to_folder(f['id'], args.move_to)
                print(f"  MOVED to folder: {args.move_to}")

            try:
                os.unlink(local_path)
            except OSError:
                pass

    print(f"\nDone! Processed {len(files)} invoice(s).")


if __name__ == "__main__":
    main()
