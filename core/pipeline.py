"""
Main extraction pipeline orchestrator.
Coordinates text extraction, data extraction, classification, and naming.
"""

import logging
import os
from typing import Optional

from .models import InvoiceData, ExtractionResult
from .text.smart_extractor import SmartTextExtractor
from .extractors.supplier import SupplierExtractor
from .extractors.invoice_number import extract_invoice_number
from .extractors.date_amount import extract_date, extract_amount_and_currency
from .extractors.accounting_prefix import extract_accounting_prefix
from .classifier import VATQuarterClassifier
from .naming import generate_filename

logger = logging.getLogger(__name__)


class InvoicePipeline:
    """
    Orchestrates the full invoice processing pipeline:
    1. Text extraction (pdfplumber or Vision OCR)
    2. Supplier detection (templates + heuristic)
    3. Field extraction (invoice#, date, amount, currency)
    4. VAT quarter classification
    5. Filename generation
    """

    def __init__(
        self,
        vision_client=None,
        suppliers_config: Optional[str] = None,
        companies_config: Optional[str] = None,
    ):
        self.text_extractor = SmartTextExtractor(vision_client=vision_client)
        self.supplier_extractor = SupplierExtractor(config_path=suppliers_config)
        self.vat_classifier = VATQuarterClassifier(config_path=companies_config)

    def process_file(
        self,
        filepath: str,
        include_vat_quarter: bool = True,
        debug: bool = False,
    ) -> ExtractionResult:
        """
        Process a single file end-to-end.
        Returns ExtractionResult with all extracted data and suggested filename.
        """
        filename = os.path.basename(filepath)
        dirpath = os.path.dirname(filepath)
        errors = []

        # Step 0: Validate file
        is_valid, error_msg = self.text_extractor.validate_file(filepath)
        if not is_valid:
            return ExtractionResult(
                invoice_data=InvoiceData(),
                original_filename=filename,
                errors=[error_msg or "File validation failed"],
            )

        # Step 1: Extract text
        try:
            text, method = self.text_extractor.extract_from_path(filepath)
        except Exception as e:
            return ExtractionResult(
                invoice_data=InvoiceData(),
                original_filename=filename,
                errors=[f"Text extraction failed: {e}"],
            )

        if not text or len(text.strip()) < 10:
            return ExtractionResult(
                invoice_data=InvoiceData(extraction_method=method),
                original_filename=filename,
                errors=["No text could be extracted from file"],
            )

        if debug:
            logger.info(f"DEBUG - File: {filename}")
            logger.info(f"DEBUG - Method: {method}")
            logger.info(f"DEBUG - Text length: {len(text)}")
            logger.info(f"DEBUG - First 300 chars:\n{text[:300]}")

        # Step 2: Extract supplier
        supplier_name, supplier_template = self.supplier_extractor.extract(text)

        # Step 3: Extract fields using supplier template for context
        invoice_number = extract_invoice_number(text, supplier_template)
        invoice_date = extract_date(text, supplier_template)
        amount, currency = extract_amount_and_currency(text, supplier_template)

        # Build InvoiceData
        invoice_data = InvoiceData(
            supplier=supplier_name,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            amount=amount,
            currency=currency,
            extraction_method=method,
        )

        # Calculate confidence
        invoice_data.confidence = self._calculate_confidence(invoice_data)

        if debug:
            logger.info(f"DEBUG - Extracted: {invoice_data}")

        # Step 4: Accounting prefix
        accounting_prefix = extract_accounting_prefix(filename)

        # Step 5: VAT quarter
        vat_quarter = None
        if include_vat_quarter and invoice_date:
            vat_quarter = self.vat_classifier.classify(invoice_date)

        # Step 6: Generate filename
        new_filename = generate_filename(
            data=invoice_data,
            original_filename=filename,
            accounting_prefix=accounting_prefix,
            vat_quarter=vat_quarter,
            dirpath=dirpath,
        )

        return ExtractionResult(
            invoice_data=invoice_data,
            supplier_template=supplier_template,
            original_filename=filename,
            new_filename=new_filename,
            accounting_prefix=accounting_prefix,
            vat_quarter=vat_quarter,
            errors=errors,
        )

    def process_text(
        self,
        text: str,
        filename: str = "invoice.pdf",
        include_vat_quarter: bool = True,
    ) -> ExtractionResult:
        """
        Process already-extracted text (useful for testing).
        """
        supplier_name, supplier_template = self.supplier_extractor.extract(text)
        invoice_number = extract_invoice_number(text, supplier_template)
        invoice_date = extract_date(text, supplier_template)
        amount, currency = extract_amount_and_currency(text, supplier_template)

        invoice_data = InvoiceData(
            supplier=supplier_name,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            amount=amount,
            currency=currency,
            extraction_method="direct_text",
        )
        invoice_data.confidence = self._calculate_confidence(invoice_data)

        accounting_prefix = extract_accounting_prefix(filename)

        vat_quarter = None
        if include_vat_quarter and invoice_date:
            vat_quarter = self.vat_classifier.classify(invoice_date)

        new_filename = generate_filename(
            data=invoice_data,
            original_filename=filename,
            accounting_prefix=accounting_prefix,
            vat_quarter=vat_quarter,
        )

        return ExtractionResult(
            invoice_data=invoice_data,
            supplier_template=supplier_template,
            original_filename=filename,
            new_filename=new_filename,
            accounting_prefix=accounting_prefix,
            vat_quarter=vat_quarter,
        )

    @staticmethod
    def _calculate_confidence(data: InvoiceData) -> float:
        """Calculate confidence score based on how many fields were extracted."""
        score = 0.0
        weights = {
            'supplier': 0.25,
            'invoice_number': 0.20,
            'date': 0.25,
            'amount': 0.20,
            'currency': 0.10,
        }
        if data.supplier and data.supplier != "Unknown":
            score += weights['supplier']
        if data.invoice_number:
            score += weights['invoice_number']
        if data.invoice_date:
            score += weights['date']
        if data.amount:
            score += weights['amount']
        if data.currency and data.currency != "XXX":
            score += weights['currency']
        return round(score, 2)
