"""
End-to-End Orchestrator and Agent Pipeline Unit Tests.
"""

import os
import tempfile
import unittest
from database.seed_data import seed_database
from services.orchestrator import Orchestrator
from services.payment_service import PaymentService
from services.pdf_service import generate_all_sample_invoices


class TestFinFlowPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_finflow.db")
        seed_database(cls.db_path)
        cls.sample_pdfs = generate_all_sample_invoices(os.path.join(cls.temp_dir.name, "samples"))

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_valid_invoice_pipeline(self):
        # 1. Valid Invoice should route cleanly
        valid_pdf_path = [p for p in self.sample_pdfs if "valid_apex" in p][0]
        with open(valid_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        res = orchestrator.process_invoice_document(pdf_bytes, "invoice_valid_apex.pdf")

        self.assertIn(res["status"], ["PENDING_APPROVAL", "COMPLETED"])
        self.assertEqual(len(res["exceptions"]), 0)

        # 2. Human Approval & Simulated Payment Execution
        payment_service = PaymentService(db_path=self.db_path)
        pay_res = payment_service.prepare_payment_batch(
            invoice_id=res["invoice_id"],
            decision="APPROVED",
            decision_by="CFO_Jane_Doe",
            payment_method="ACH",
            comments="Approved for automated corporate disbursement.",
        )
        self.assertEqual(pay_res["status"], "EXECUTED")
        self.assertEqual(pay_res["invoice_status"], "PAID")
        self.assertTrue(pay_res["simulated_ref"].startswith("PAY-"))

    def test_po_mismatch_exception_generation(self):
        mismatch_pdf_path = [p for p in self.sample_pdfs if "mismatch_logistics" in p][0]
        with open(mismatch_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        res = orchestrator.process_invoice_document(pdf_bytes, "invoice_mismatch_logistics.pdf")

        self.assertIn(res["status"], ["EXCEPTION", "NEEDS_REVIEW"])
        self.assertTrue(len(res["exceptions"]) > 0)

    def test_tax_and_math_anomaly_detection(self):
        tax_pdf_path = [p for p in self.sample_pdfs if "tax_error" in p][0]
        with open(tax_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        res = orchestrator.process_invoice_document(pdf_bytes, "invoice_tax_error.pdf")

        self.assertIn(res["status"], ["EXCEPTION", "NEEDS_REVIEW"])
        self.assertTrue(len(res["exceptions"]) > 0)


if __name__ == "__main__":
    unittest.main()
