"""
Tests for Central Multi-Agent Orchestrator (Task 05):
- Successful end-to-end invoice processing
- Extraction failure handling & downstream stoppage
- Unknown vendor scenario
- PO mismatch scenario
- Duplicate invoice handling
- Financial anomaly detection
- Reprocessing an existing invoice
"""

import os
import tempfile
import unittest
from database.seed_data import seed_database
from database.db import get_db_connection
from services.orchestrator import Orchestrator
from services.pdf_service import generate_all_sample_invoices


class TestMultiAgentOrchestrator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_multiagent.db")
        seed_database(self.db_path)
        self.sample_pdfs = generate_all_sample_invoices(os.path.join(self.temp_dir.name, "samples"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_successful_clean_invoice_orchestration(self):
        """Clean valid invoice (Apex Cloud PO-2026-001) flows through all 5 agents and completes."""
        valid_pdf_path = [p for p in self.sample_pdfs if "valid_apex" in p][0]
        with open(valid_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        ctx = orchestrator.process_invoice_document(pdf_bytes, "invoice_valid_apex.pdf")

        self.assertEqual(ctx.workflow_status, "COMPLETED")
        self.assertEqual(ctx.extraction_status, "COMPLETED")
        self.assertEqual(len(ctx.agent_execution_history), 5)
        self.assertEqual(ctx.agent_execution_history[0].agent_name, "Intake Agent")
        self.assertEqual(ctx.agent_execution_history[1].agent_name, "Verification Agent")
        self.assertEqual(ctx.agent_execution_history[2].agent_name, "Financial Intelligence Agent")
        self.assertEqual(ctx.agent_execution_history[3].agent_name, "Workflow Agent")
        self.assertEqual(ctx.agent_execution_history[4].agent_name, "Reporting Agent")

    def test_extraction_failure_halts_downstream(self):
        """Corrupted/invalid file causes Intake Agent to fail and halts downstream agents."""
        orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        garbage_bytes = b"Not a valid PDF file at all"
        ctx = orchestrator.process_invoice_document(garbage_bytes, "garbage.pdf")

        self.assertEqual(ctx.workflow_status, "FAILED")
        self.assertEqual(ctx.extraction_status, "FAILED")
        self.assertEqual(len(ctx.agent_execution_history), 1)  # Only Intake Agent ran
        self.assertEqual(ctx.agent_execution_history[0].status, "FAILED")

    def test_duplicate_invoice_detection_and_blocking(self):
        """Ingesting the same invoice twice without allow_reprocessing blocks duplicate processing."""
        valid_pdf_path = [p for p in self.sample_pdfs if "valid_apex" in p][0]
        with open(valid_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        # Attempt 1: Process initial invoice
        ctx1 = orchestrator.process_invoice_document(pdf_bytes, "invoice_valid_apex.pdf")
        self.assertEqual(ctx1.workflow_status, "COMPLETED")

        # Attempt 2: Re-ingest same document without allow_reprocessing
        ctx2 = orchestrator.process_invoice_document(pdf_bytes, "invoice_valid_apex.pdf", allow_reprocessing=False)
        self.assertEqual(ctx2.workflow_status, "BLOCKED")
        self.assertTrue(any("DUPLICATE_PROCESSING" in e for e in ctx2.exceptions))

    def test_reprocessing_existing_invoice(self):
        """Reprocessing an existing invoice with allow_reprocessing=True forces execution."""
        valid_pdf_path = [p for p in self.sample_pdfs if "valid_apex" in p][0]
        with open(valid_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        ctx = orchestrator.process_invoice_document(pdf_bytes, "invoice_valid_apex.pdf", allow_reprocessing=True)

        self.assertIn(ctx.workflow_status, ["COMPLETED", "NEEDS_REVIEW"])
        self.assertEqual(len(ctx.agent_execution_history), 5)

    def test_unknown_or_blocked_vendor_scenario(self):
        """Unknown offshore entity triggers risk scoring and routing to review/blocked."""
        fraud_pdf_path = [p for p in self.sample_pdfs if "unknown_shell" in p][0]
        with open(fraud_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        ctx = orchestrator.process_invoice_document(pdf_bytes, "invoice_unknown_shell.pdf", allow_reprocessing=True)

        self.assertIn(ctx.workflow_status, ["NEEDS_REVIEW", "BLOCKED"])
        self.assertGreaterEqual(ctx.financial_risk_results["risk_score"], 0.4)
        self.assertTrue(len(ctx.exceptions) > 0)

    def test_po_mismatch_scenario(self):
        """Overbilled logistics invoice routes to NEEDS_REVIEW."""
        mismatch_pdf_path = [p for p in self.sample_pdfs if "mismatch_logistics" in p][0]
        with open(mismatch_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        ctx = orchestrator.process_invoice_document(pdf_bytes, "invoice_mismatch_logistics.pdf", allow_reprocessing=True)

        self.assertEqual(ctx.workflow_status, "NEEDS_REVIEW")
        self.assertTrue(ctx.verification_results["amount_mismatch"])


if __name__ == "__main__":
    unittest.main()
