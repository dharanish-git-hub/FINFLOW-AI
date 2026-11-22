"""
Unit Tests for Audit Logs, Financial Analytics & Reporting (Task 09)
Validates:
- Audit event creation with actor, previous_status, new_status, and category
- Status transition recording
- Chronological retrieval of audit events
- Audit log filtering by category, level, and search keyword
- Accurate financial analytics computations (KPIs, top vendors, status distributions)
- Exclusion of FAILED payment transactions from settled totals
- CSV report generation (invoices, payments, exceptions, audit logs)
- Clean handling of empty database states
"""

import os
import unittest
import tempfile
import sqlite3
import csv
import io
from database.db import init_db, get_db_connection
from services.audit_analytics_service import AuditAnalyticsService
from services.payment_service import PaymentService
from services.approval_workflow_service import ApprovalWorkflowService


class TestAuditAnalyticsReporting(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_audit_analytics.db")
        init_db(self.db_path)
        self.service = AuditAnalyticsService(self.db_path)
        self.payment_service = PaymentService(self.db_path)
        self.approval_service = ApprovalWorkflowService(self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_audit_event_creation(self):
        """Audit events record complete metadata including actor, category, and payload."""
        audit_id = self.service.record_audit_event(
            action="INVOICE_UPLOADED",
            message="Uploaded vendor invoice from portal.",
            invoice_id=101,
            actor="Operator_Sarah",
            agent_name="IntakeAgent",
            level="SUCCESS",
            category="INTAKE",
            previous_status="NONE",
            new_status="RECEIVED",
            payload={"file_size": 204800, "mime": "application/pdf"},
        )
        self.assertGreater(audit_id, 0)

        logs = self.service.get_audit_logs(invoice_id=101)
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log["action"], "INVOICE_UPLOADED")
        self.assertEqual(log["actor"], "Operator_Sarah")
        self.assertEqual(log["category"], "INTAKE")
        self.assertEqual(log["level"], "SUCCESS")
        self.assertEqual(log["previous_status"], "NONE")
        self.assertEqual(log["new_status"], "RECEIVED")
        self.assertIn("file_size", log["payload_json"])

    def test_status_transition_recording(self):
        """Audit trail accurately tracks multiple lifecycle status transitions."""
        self.service.record_audit_event(
            action="EXTRACTION_COMPLETED",
            message="Extracted invoice data.",
            invoice_id=202,
            actor="IntakeAgent",
            previous_status="RECEIVED",
            new_status="EXTRACTED",
            category="INTAKE",
        )
        self.service.record_audit_event(
            action="WORKFLOW_APPROVED",
            message="Approved invoice.",
            invoice_id=202,
            actor="CFO_Jane",
            previous_status="PENDING_APPROVAL",
            new_status="APPROVED",
            category="APPROVAL",
        )

        logs = self.service.get_audit_logs(invoice_id=202)
        self.assertEqual(len(logs), 2)
        # Most recent first
        self.assertEqual(logs[0]["action"], "WORKFLOW_APPROVED")
        self.assertEqual(logs[1]["action"], "EXTRACTION_COMPLETED")

    def test_chronological_audit_retrieval_and_filtering(self):
        """Audit logs can be searched by keyword and filtered by category and level."""
        self.service.record_audit_event(
            action="VENDOR_VERIFIED",
            message="Vendor Apex Cloud verified.",
            category="VERIFICATION",
            level="INFO",
            actor="VerificationAgent",
        )
        self.service.record_audit_event(
            action="EXCEPTION_DETECTED",
            message="Price variance exceeded threshold.",
            category="EXCEPTION",
            level="WARNING",
            actor="FinIntelAgent",
        )
        self.service.record_audit_event(
            action="PAYMENT_FAILED",
            message="Fedwire routing invalid.",
            category="PAYMENT",
            level="ERROR",
            actor="PaymentService",
        )

        # Filter by category
        pay_logs = self.service.get_audit_logs(category="PAYMENT")
        self.assertEqual(len(pay_logs), 1)
        self.assertEqual(pay_logs[0]["action"], "PAYMENT_FAILED")

        # Filter by level
        warn_logs = self.service.get_audit_logs(level="WARNING")
        self.assertEqual(len(warn_logs), 1)
        self.assertEqual(warn_logs[0]["action"], "EXCEPTION_DETECTED")

        # Search query
        search_logs = self.service.get_audit_logs(search_query="Apex Cloud")
        self.assertEqual(len(search_logs), 1)
        self.assertEqual(search_logs[0]["action"], "VENDOR_VERIFIED")

    def test_analytics_calculations_and_failed_payment_exclusion(self):
        """Financial analytics derive directly from DB and strictly exclude FAILED payments from settled totals."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Insert Invoices
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status, invoice_date)
            VALUES 
                ('INV-001', 'Apex Cloud Services Inc.', 10000.0, 'PAID', '2026-11-01'),
                ('INV-002', 'Apex Cloud Services Inc.', 5000.0, 'APPROVED', '2026-11-02'),
                ('INV-003', 'Global Logistics & Freight LLC', 2500.0, 'PENDING_APPROVAL', '2026-11-03');
            """
        )
        inv1_id = 1
        inv2_id = 2

        # Insert Exceptions
        cursor.execute(
            """
            INSERT INTO exceptions (invoice_id, exception_type, severity, description, status)
            VALUES (3, 'PO_MISMATCH', 'HIGH', 'Line count variance', 'OPEN');
            """
        )

        # Insert Payment Transactions: 1 EXECUTED ($10,000) and 1 FAILED ($5,000)
        cursor.execute(
            """
            INSERT INTO payment_transactions (
                transaction_ref, invoice_id, vendor_name, amount, payment_rail, status, simulated_by, settled_at
            )
            VALUES 
                ('TXN-ACH-001', ?, 'Apex Cloud Services Inc.', 10000.0, 'ACH Corporate Credit', 'EXECUTED', 'CFO', '2026-11-05'),
                ('TXN-WIRE-002', ?, 'Apex Cloud Services Inc.', 5000.0, 'Fedwire High-Value', 'FAILED', 'CFO', NULL);
            """,
            (inv1_id, inv2_id),
        )

        conn.commit()
        conn.close()

        analytics = self.service.get_financial_analytics()
        kpis = analytics["kpis"]

        # Assertions
        self.assertEqual(kpis["total_invoices"], 3)
        self.assertEqual(kpis["total_invoice_value"], 17500.0)
        self.assertEqual(kpis["total_executed_payments"], 1)
        # CRITICAL: Settled payment volume must be 10000.0, NOT 15000.0 (Failed is excluded!)
        self.assertEqual(kpis["total_settled_value"], 10000.0)
        self.assertEqual(kpis["failed_payments"], 1)
        self.assertEqual(kpis["open_exceptions"], 1)
        self.assertEqual(kpis["pending_approvals"], 1)

        # Top vendors verification
        top_v = analytics["top_vendors"]
        self.assertEqual(top_v[0]["vendor_name"], "Apex Cloud Services Inc.")
        self.assertEqual(top_v[0]["total_value"], 15000.0)

    def test_csv_report_generation(self):
        """CSV generators produce well-formed CSV strings with expected headers and row data."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-CSV-01', 'CyberShield Security Corp', 12000.0, 'PAID');
            """
        )
        inv_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO payment_transactions (
                transaction_ref, invoice_id, vendor_name, amount, payment_rail, status, simulated_by, settled_at
            )
            VALUES ('TXN-VCARD-01', ?, 'CyberShield Security Corp', 12000.0, 'Single-Use Virtual Card', 'EXECUTED', 'Treasury', '2026-11-15');
            """,
            (inv_id,),
        )
        cursor.execute(
            """
            INSERT INTO exceptions (invoice_id, exception_type, severity, description, status)
            VALUES (?, 'AMOUNT_MISMATCH', 'MEDIUM', 'Slight tax rounding', 'RESOLVED');
            """,
            (inv_id,),
        )
        conn.commit()
        conn.close()

        # 1. Invoice CSV
        inv_csv = self.service.generate_invoice_summary_csv()
        reader = list(csv.reader(io.StringIO(inv_csv)))
        self.assertEqual(reader[0][1], "Invoice Number")
        self.assertIn("INV-CSV-01", inv_csv)

        # 2. Payment CSV
        pay_csv = self.service.generate_payment_transactions_csv()
        self.assertIn("TXN-VCARD-01", pay_csv)
        self.assertIn("Single-Use Virtual Card", pay_csv)

        # 3. Exception CSV
        exc_csv = self.service.generate_exceptions_csv()
        self.assertIn("AMOUNT_MISMATCH", exc_csv)

        # 4. Audit CSV
        self.service.record_audit_event(
            action="CSV_EXPORT_TEST",
            message="Testing audit export.",
            category="SYSTEM",
        )
        audit_csv = self.service.generate_audit_logs_csv()
        self.assertIn("CSV_EXPORT_TEST", audit_csv)

    def test_empty_database_handling(self):
        """All analytics and export functions execute gracefully without errors on an empty database."""
        analytics = self.service.get_financial_analytics()
        kpis = analytics["kpis"]
        self.assertEqual(kpis["total_invoices"], 0)
        self.assertEqual(kpis["total_invoice_value"], 0.0)
        self.assertEqual(kpis["total_settled_value"], 0.0)
        self.assertEqual(kpis["failed_payments"], 0)
        self.assertEqual(kpis["open_exceptions"], 0)

        # Empty CSVs should contain header rows without exceptions
        inv_csv = self.service.generate_invoice_summary_csv()
        self.assertTrue(inv_csv.startswith("Invoice ID,Invoice Number"))

        pay_csv = self.service.generate_payment_transactions_csv()
        self.assertTrue(pay_csv.startswith("Transaction ID,Transaction Ref"))

        exc_csv = self.service.generate_exceptions_csv()
        self.assertTrue(exc_csv.startswith("Exception ID,Invoice ID"))

        logs = self.service.get_audit_logs()
        self.assertEqual(logs, [])


if __name__ == "__main__":
    unittest.main()
