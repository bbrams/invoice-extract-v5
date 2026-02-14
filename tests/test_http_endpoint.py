"""
Tests for the HTTP Cloud Function endpoints.
Covers: API key security, dry_run, company_id, batch, error handling,
CORS, input validation, and scenarios from the architecture spec.

Note: main.py imports are mocked to avoid pdfplumber/cryptography issues
in constrained test environments.
"""

import json
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class FakeRequest:
    """Minimal Flask-like request mock for Cloud Function testing."""

    def __init__(self, json_data=None, headers=None, content_type='application/json',
                 method='POST', files=None):
        self._json = json_data
        self.headers = headers or {}
        self.content_type = content_type
        self.method = method
        self.files = files or {}

    def get_json(self, silent=False):
        return self._json


# Mock heavy dependencies before importing main
_mock_modules = {
    'pdfplumber': MagicMock(),
    'PIL': MagicMock(),
    'PIL.Image': MagicMock(),
    'pdf2image': MagicMock(),
    'google.cloud': MagicMock(),
    'google.cloud.vision': MagicMock(),
}

with patch.dict('sys.modules', _mock_modules):
    import main as _main_module
    from main import (
        _verify_api_key, _make_response, _handle_cors,
        process_invoice_http, learn_supplier_http, health_http,
        StructuredFormatter,
    )


# ─────────────────────────────────────────────────────────
# Scenario 1: API key security
# ─────────────────────────────────────────────────────────

class TestAPIKeySecurity:

    @patch.dict(os.environ, {'INVOICE_API_KEY': 'secret123'})
    def test_rejects_missing_api_key(self):
        req = FakeRequest(json_data={'file_id': 'abc'}, headers={})
        body, status, _ = process_invoice_http(req)
        assert status == 401
        assert 'Unauthorized' in body

    @patch.dict(os.environ, {'INVOICE_API_KEY': 'secret123'})
    def test_rejects_wrong_api_key(self):
        req = FakeRequest(
            json_data={'file_id': 'abc'},
            headers={'X-API-Key': 'wrong_key'}
        )
        body, status, _ = process_invoice_http(req)
        assert status == 401

    @patch.dict(os.environ, {}, clear=True)
    def test_allows_when_no_key_configured(self):
        req = FakeRequest(headers={})
        assert _verify_api_key(req) is True

    @patch.dict(os.environ, {'INVOICE_API_KEY': 'secret123'})
    def test_accepts_correct_api_key(self):
        req = FakeRequest(headers={'X-API-Key': 'secret123'})
        assert _verify_api_key(req) is True


# ─────────────────────────────────────────────────────────
# Scenario 2: CORS handling
# ─────────────────────────────────────────────────────────

class TestCORS:

    def test_options_returns_204(self):
        req = FakeRequest(method='OPTIONS')
        body, status, headers = process_invoice_http(req)
        assert status == 204
        assert 'Access-Control-Allow-Origin' in headers

    def test_response_includes_cors_headers(self):
        _, _, headers = _make_response({"test": True}, 200)
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'X-API-Key' in headers['Access-Control-Allow-Headers']


# ─────────────────────────────────────────────────────────
# Scenario 3: Input validation
# ─────────────────────────────────────────────────────────

class TestInputValidation:

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(_main_module, '_get_pipeline', return_value=MagicMock())
    def test_rejects_empty_body(self, mock_pipeline):
        req = FakeRequest(json_data=None)
        body, status, _ = process_invoice_http(req)
        assert status == 400
        assert 'Empty' in body

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(_main_module, '_get_pipeline', return_value=MagicMock())
    def test_rejects_missing_file_id_and_folder_id(self, mock_pipeline):
        req = FakeRequest(json_data={'company_id': 'test'})
        body, status, _ = process_invoice_http(req)
        assert status == 400
        assert 'file_id or folder_id required' in body

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(_main_module, '_get_pipeline', return_value=MagicMock())
    def test_rejects_invalid_content_type(self, mock_pipeline):
        req = FakeRequest(json_data={}, content_type='text/plain')
        body, status, _ = process_invoice_http(req)
        assert status == 400

    def test_rejects_malicious_file_id(self):
        from core.models import ProcessRequest
        with pytest.raises(Exception):
            ProcessRequest(file_id="'; DROP TABLE --")

    def test_accepts_valid_file_id(self):
        from core.models import ProcessRequest
        req = ProcessRequest(file_id="1AbCdEfGhIjKlMnOpQrStUvWxYz")
        assert req.file_id == "1AbCdEfGhIjKlMnOpQrStUvWxYz"


# ─────────────────────────────────────────────────────────
# Scenario 4: Dry run
# ─────────────────────────────────────────────────────────

class TestDryRun:

    def test_dry_run_flag_in_request(self):
        from core.models import ProcessRequest
        req = ProcessRequest(file_id="abc123", dry_run=True)
        assert req.dry_run is True

    def test_dry_run_default_false(self):
        from core.models import ProcessRequest
        req = ProcessRequest(file_id="abc123")
        assert req.dry_run is False


# ─────────────────────────────────────────────────────────
# Scenario 5: Company ID / multi-company
# ─────────────────────────────────────────────────────────

class TestCompanyId:

    def test_company_id_in_request(self):
        from core.models import ProcessRequest
        req = ProcessRequest(file_id="abc", company_id="brams_tech_llc")
        assert req.company_id == "brams_tech_llc"

    def test_pipeline_accepts_company_id(self):
        """Pipeline.process_file should accept company_id parameter."""
        # Read the source directly to avoid pdfplumber import issues
        import ast
        source_path = os.path.join(os.path.dirname(__file__), '..', 'core', 'pipeline.py')
        with open(source_path) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'process_file':
                param_names = [arg.arg for arg in node.args.args]
                assert 'company_id' in param_names
                return
        pytest.fail("process_file method not found in pipeline.py")


# ─────────────────────────────────────────────────────────
# Scenario 6: Correlation ID
# ─────────────────────────────────────────────────────────

class TestCorrelationId:

    def test_make_response_includes_correlation_id(self):
        body_str, _, _ = _make_response({"test": True}, 200, "abc123")
        body = json.loads(body_str)
        assert body["correlation_id"] == "abc123"

    def test_make_response_without_correlation_id(self):
        body_str, _, _ = _make_response({"test": True}, 200)
        body = json.loads(body_str)
        assert "correlation_id" not in body


# ─────────────────────────────────────────────────────────
# Scenario 7: Structured logging
# ─────────────────────────────────────────────────────────

class TestStructuredLogging:

    def test_formatter_produces_json(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='test.py',
            lineno=1, msg='Test message', args=(), exc_info=None
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed['message'] == 'Test message'
        assert parsed['severity'] == 'INFO'


# ─────────────────────────────────────────────────────────
# Scenario 8: Health check
# ─────────────────────────────────────────────────────────

class TestHealthCheck:

    def test_health_returns_ok(self):
        body_str, status, _ = health_http(FakeRequest())
        assert status == 200
        body = json.loads(body_str)
        assert body['status'] == 'ok'
        assert body['version'] == '5.0'


# ─────────────────────────────────────────────────────────
# Scenario 9: Learn supplier endpoint security
# ─────────────────────────────────────────────────────────

class TestLearnSupplier:

    @patch.dict(os.environ, {'INVOICE_API_KEY': 'secret123'})
    def test_rejects_without_api_key(self):
        req = FakeRequest(json_data={'supplier_name': 'Test'}, headers={})
        body, status, _ = learn_supplier_http(req)
        assert status == 401

    @patch.dict(os.environ, {}, clear=True)
    def test_rejects_empty_supplier_name(self):
        req = FakeRequest(json_data={'supplier_name': ''})
        body, status, _ = learn_supplier_http(req)
        assert status == 400

    @patch.dict(os.environ, {}, clear=True)
    def test_rejects_long_supplier_name(self):
        req = FakeRequest(json_data={'supplier_name': 'A' * 101})
        body, status, _ = learn_supplier_http(req)
        assert status == 400


# ─────────────────────────────────────────────────────────
# Scenario 10: ExtractionResult mutable default fix
# ─────────────────────────────────────────────────────────

class TestModelDefaults:

    def test_errors_not_shared(self):
        from core.models import ExtractionResult, InvoiceData
        r1 = ExtractionResult(invoice_data=InvoiceData(), original_filename="a.pdf")
        r2 = ExtractionResult(invoice_data=InvoiceData(), original_filename="b.pdf")
        r1.errors.append("error1")
        assert r2.errors == []  # Must NOT be affected

    def test_process_request_validation(self):
        from core.models import ProcessRequest
        req = ProcessRequest(file_id="test123", dry_run=True, company_id="brams_tech_llc")
        assert req.file_id == "test123"
        assert req.dry_run is True
        assert req.company_id == "brams_tech_llc"
