"""
Pydantic models for invoice data extraction and validation.
"""

from datetime import date as date_type
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class InvoiceData(BaseModel):
    """Validated invoice data extracted from a document."""
    supplier: str = "Unknown"
    invoice_number: Optional[str] = None
    invoice_date: Optional[date_type] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    confidence: float = 0.0
    extraction_method: str = ""  # "pdfplumber" or "vision_ocr"

    @field_validator('amount')
    @classmethod
    def amount_must_be_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Amount must be positive')
        if v is not None and v > 10_000_000:
            raise ValueError('Amount unrealistically high')
        return v

    @field_validator('currency')
    @classmethod
    def currency_must_be_valid(cls, v):
        valid = {
            'USD', 'EUR', 'AED', 'GBP', 'INR', 'SAR', 'MAD', 'CHF',
            'CAD', 'AUD', 'JPY', 'SGD', 'QAR', 'KWD', 'BHD', 'OMR',
            'EGP', 'PKR', 'XXX',
        }
        if v is not None and v not in valid:
            raise ValueError(f'Unknown currency: {v}')
        return v

    def format_date(self) -> str:
        """Return date as DD-MM-YYYY string."""
        if self.invoice_date:
            return self.invoice_date.strftime('%d-%m-%Y')
        return 'NoDate'

    def format_amount(self) -> str:
        """Return amount with currency as string for filename."""
        if self.amount and self.currency:
            return f"{self.amount:.2f}{self.currency}"
        return "0.00XXX"


class SupplierTemplate(BaseModel):
    """A supplier detection and extraction template."""
    id: str
    display_name: str
    detection_patterns: list[str]
    default_currency: Optional[str] = None
    invoice_number_pattern: Optional[str] = None
    amount_patterns: Optional[list[dict]] = None
    date_context: Optional[list[str]] = None
    notes: Optional[str] = None


class CompanyConfig(BaseModel):
    """Company configuration with VAT calendar."""
    id: str
    name: str
    vat_calendar: Optional[dict] = None


class ExtractionResult(BaseModel):
    """Full result of the extraction pipeline."""
    invoice_data: InvoiceData
    supplier_template: Optional[SupplierTemplate] = None
    original_filename: str
    new_filename: str = ""
    accounting_prefix: Optional[str] = None
    vat_quarter: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
    raw_text: Optional[str] = None  # Kept for supplier learning when supplier is Unknown


class ProcessRequest(BaseModel):
    """Validated request payload for the Cloud Function."""
    file_id: Optional[str] = None
    folder_id: Optional[str] = None
    company_id: Optional[str] = None
    dry_run: bool = False
    rename: bool = False
    move_to: Optional[str] = None
    include_vat_quarter: bool = True
    debug: bool = False

    @field_validator('file_id', 'folder_id', 'company_id', 'move_to')
    @classmethod
    def sanitize_ids(cls, v):
        """Reject IDs with suspicious characters (injection protection)."""
        if v is not None:
            import re
            if not re.match(r'^[A-Za-z0-9_-]{1,128}$', v):
                raise ValueError(f'Invalid ID format: must be alphanumeric, max 128 chars')
        return v
