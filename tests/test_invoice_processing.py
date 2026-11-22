"""
Tests for PDF extraction diagnostics, handling of empty/corrupted/scanned PDFs,
and structured invoice review and saving into SQLite.
"""

import os
import io
import tempfile
import unittest
from reportlab.pdfgen import canvas
from database.seed_data import seed_database
from database.db import get_db_connection
from services.pdf_service import extract_text_with_diagnostics, generate_all_sample_invoices
from agents.intake_agent import IntakeAgent


class TestInvoicePDFExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_extraction.db")
        seed_database(cls.db_path)
        cls.samples = generate_all_sample_invoices(os.path.join(cls.temp_dir.name, "samples"))

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_synthetic_invoice_text_extraction(self):
        """Test with synthetic invoices from sample_data."""
        valid_pdf = [p for p in self.samples if "valid_apex" in p][0]
        with open(valid_pdf, "rb") as f:
            pdf_bytes = f.read()

        diag = extract_text_with_diagnostics(pdf_bytes, "valid_apex.pdf")
        self.assertTrue(diag["success"])
        self.assertIn("--- Page 1 ---", diag["text"])
        self.assertIn("Apex Cloud Services", diag["text"])
        self.assertIn("PO-2026-001", diag["text"])
        self.assertFalse(diag["is_scanned"])

    def test_empty_pdf_detection(self):
        """Test empty 0-byte PDF validation."""
        diag = extract_text_with_diagnostics(b"", "empty.pdf")
        self.assertFalse(diag["success"])
        self.assertEqual(diag["error_type"], "EMPTY_FILE")

    def test_corrupted_pdf_detection(self):
        """Test garbage bytes pretending to be a PDF."""
        corrupted_bytes = b"%PDF-1.4 completely broken binary junk data"
        diag = extract_text_with_diagnostics(corrupted_bytes, "corrupted.pdf")
        self.assertFalse(diag["success"])
        self.assertEqual(diag["error_type"], "CORRUPTED_FILE")

    def test_scanned_image_pdf_detection(self):
        """Test PDF with pages but no extractable text (scanned document simulation)."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        # Draw a rectangle without any text
        c.rect(50, 50, 400, 400, fill=1)
        c.showPage()
        c.save()
        scanned_bytes = buf.getvalue()

        diag = extract_text_with_diagnostics(scanned_bytes, "scanned_invoice.pdf")
        self.assertFalse(diag["success"])
        self.assertEqual(diag["error_type"], "SCANNED_DOCUMENT")
        self.assertTrue(diag["is_scanned"])
        self.assertIn("OCR is required", diag["message"])

    def test_end_to_end_extraction_and_sqlite_persistence(self):
        """Test extraction via IntakeAgent and saving to SQLite without duplicate records."""
        valid_pdf = [p for p in self.samples if "valid_apex" in p][0]
        with open(valid_pdf, "rb") as f:
            pdf_bytes = f.read()

        agent = IntakeAgent(mock_mode=True)
        extraction, file_hash, raw_text = agent.process(pdf_bytes, "invoice_valid_apex.pdf")

        self.assertEqual(extraction.invoice_number, "INV-2026-801")
        self.assertEqual(extraction.vendor_name, "Apex Cloud Services Inc.")
        self.assertEqual(extraction.total_amount, 13500.00)
        self.assertGreaterEqual(len(extraction.line_items), 3)

        # Save to database
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO invoices (
                invoice_number, vendor_name, po_number, file_name, file_hash,
                invoice_date, due_date, subtotal, tax_amount, total_amount,
                currency, status, payment_terms, extraction_raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'EXTRACTED', ?, ?);
            """,
            (
                extraction.invoice_number,
                extraction.vendor_name,
                extraction.po_number,
                "invoice_valid_apex.pdf",
                file_hash,
                extraction.invoice_date,
                extraction.due_date,
                extraction.subtotal,
                extraction.tax_amount,
                extraction.total_amount,
                extraction.currency,
                extraction.payment_terms,
                extraction.model_dump_json(),
            ),
        )
        saved_id = cursor.lastrowid
        conn.commit()

        # Verify record exists
        cursor.execute("SELECT id, invoice_number, total_amount, status FROM invoices WHERE id = ?;", (saved_id,))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["invoice_number"], "INV-2026-801")
        self.assertEqual(row["total_amount"], 13500.00)

        conn.close()


if __name__ == "__main__":
    unittest.main()
