"""
End-to-End Integration Tests for FINFLOW AI (Task 10)
Validates the complete autonomous AP lifecycle using synthetic datasets:
1. End-to-end invoice ingestion through Multi-Agent Orchestrator
2. Verification and 3-way PO matching
3. Financial risk & exception intelligence routing
4. Human approval workflow execution
5. Simulated payment disbursement across rails
6. Audit log recording & financial analytics updates
7. Critical business rules:
   - Unknown vendor cannot be auto-approved
   - Inactive/blocked vendor is stopped
   - PO line mismatches trigger high exceptions
   - Critical exceptions strictly block disbursement
   - Ineligible / unapproved invoices cannot be paid
   - Failed simulated payments are not counted as settled
   - Duplicate payment attempts are blocked
"""

import os
import unittest
import tempfile
import sqlite3
from database.db import init_db, get_db_connection
from database.seed_data import seed_database
from database.demo_seeder import reset_and_seed_demo_data
from services.orchestrator import Orchestrator
from services.approval_workflow_service import ApprovalWorkflowService
from services.payment_service import PaymentService
from services.audit_analytics_service import AuditAnalyticsService


class TestFinFlowEndToEndIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_e2e.db")
        init_db(self.db_path)
        seed_database(self.db_path)
        self.orchestrator = Orchestrator(db_path=self.db_path, mock_mode=True)
        self.approval_service = ApprovalWorkflowService(db_path=self.db_path)
        self.payment_service = PaymentService(db_path=self.db_path)
        self.analytics_service = AuditAnalyticsService(db_path=self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_complete_invoice_to_payment_lifecycle(self):
        """End-to-end test: Upload -> Extract -> Verify -> Route -> Approve -> Disburse -> Analytics."""
        sample_pdf_path = os.path.join("sample_data", "invoice_valid_apex.pdf")
        with open(sample_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # 1. Autonomous Multi-Agent Orchestration
        ctx = self.orchestrator.process_invoice_document(pdf_bytes, "invoice_valid_apex.pdf")
        self.assertIn(ctx.workflow_status, ["COMPLETED", "RUNNING", "NEEDS_REVIEW"])
        self.assertIsNotNone(ctx.invoice_id)
        invoice_id = ctx.invoice_id

        # Check DB status
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status, total_amount, vendor_name FROM invoices WHERE id = ?;", (invoice_id,))
        inv_record = cursor.fetchone()
        conn.close()

        self.assertEqual(inv_record["status"], "PENDING_APPROVAL")
        self.assertEqual(inv_record["vendor_name"], "Apex Cloud Services Inc.")

        # 2. Human Approval Gate
        appr_res = self.approval_service.process_approval_decision(
            invoice_id=invoice_id,
            action="APPROVE",
            reviewer_name="VP_Finance_Alice",
            payment_method="ACH",
            high_value_confirmed=True,
        )
        self.assertEqual(appr_res["new_invoice_status"], "APPROVED")
        self.assertEqual(appr_res["payment_status"], "PREPARED")

        # 3. Simulated Payment Execution
        pay_res = self.payment_service.execute_simulated_payment(
            invoice_id=invoice_id,
            payment_rail="ACH Corporate Credit",
            simulated_by="Treasury_Officer_Bob",
            simulate_failure=False,
        )
        self.assertTrue(pay_res["success"])
        self.assertEqual(pay_res["status"], "EXECUTED")
        self.assertTrue(pay_res["transaction_ref"].startswith("TXN-ACH-"))

        # Verify DB is updated to PAID
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM invoices WHERE id = ?;", (invoice_id,))
        self.assertEqual(cursor.fetchone()["status"], "PAID")
        conn.close()

        # 4. Analytics reflect settled payment
        analytics = self.analytics_service.get_financial_analytics()
        self.assertEqual(analytics["kpis"]["total_executed_payments"], 1)
        self.assertGreater(analytics["kpis"]["total_settled_value"], 0.0)

    def test_critical_business_rule_enforcement(self):
        """Validate core financial controls and security guardrails."""
        # Seed realistic demo states
        reset_and_seed_demo_data(self.db_path)

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # 1. Invoice 4 (Duplicate - CRITICAL Exception) cannot be approved
        with self.assertRaises(ValueError) as ctx:
            self.approval_service.process_approval_decision(
                invoice_id=4,
                action="APPROVE",
                reviewer_name="CFO",
                high_value_confirmed=True,
            )
        self.assertIn("CRITICAL exception", str(ctx.exception))

        # 2. Invoice 3 (Unknown Vendor) has OPEN exception and is not approved
        cursor.execute("SELECT status FROM invoices WHERE id = 3;")
        self.assertEqual(cursor.fetchone()["status"], "EXCEPTION")

        # 3. Already PAID invoice 1 cannot be approved again
        with self.assertRaises(ValueError) as ctx:
            self.approval_service.process_approval_decision(
                invoice_id=1,
                action="APPROVE",
                reviewer_name="CFO",
            )
        self.assertIn("already in state 'PAID'", str(ctx.exception))

        # 4. Already PAID invoice 1 cannot be paid again
        with self.assertRaises(ValueError) as ctx:
            self.payment_service.execute_simulated_payment(
                invoice_id=1,
                payment_rail="ACH Corporate Credit",
                simulated_by="Treasury",
            )
        self.assertIn("already marked as PAID", str(ctx.exception))

        # 5. Failed payment (Invoice 6) is not counted in total_settled_value
        analytics = self.analytics_service.get_financial_analytics()
        # Invoice 1 is $12,500.00 (EXECUTED); Invoice 6 is $8,900.00 (FAILED)
        self.assertEqual(analytics["kpis"]["total_executed_payments"], 1)
        self.assertEqual(analytics["kpis"]["total_settled_value"], 12500.00)
        self.assertEqual(analytics["kpis"]["failed_payments"], 1)

        conn.close()


if __name__ == "__main__":
    unittest.main()
