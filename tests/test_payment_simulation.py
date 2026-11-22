import os
import unittest
import tempfile
import sqlite3
from database.db import init_db, get_db_connection
from services.approval_workflow_service import ApprovalWorkflowService
from services.payment_service import PaymentService


class TestPaymentSimulation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_payment.db")
        init_db(self.db_path)
        self.approval_service = ApprovalWorkflowService(self.db_path)
        self.payment_service = PaymentService(self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _create_approved_invoice(self, inv_num="INV-PAY-001", amount=4500.00, vendor="Apex Cloud Services Inc."):
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES (?, ?, ?, 'PENDING_APPROVAL');
            """,
            (inv_num, vendor, amount),
        )
        inv_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Approve it through ApprovalWorkflowService
        self.approval_service.process_approval_decision(
            invoice_id=inv_id,
            action="APPROVE",
            reviewer_name="CFO_Jane",
            payment_method="ACH",
            high_value_confirmed=(amount >= 10000.0),
        )
        return inv_id

    def test_payment_queue_retrieval(self):
        """Approved invoices appear in the payment queue as eligible."""
        inv_id = self._create_approved_invoice("INV-QUEUE-01", 1200.0)
        queue = self.payment_service.get_payment_queue(status_filter="ELIGIBLE")
        inv_ids = [q["id"] for q in queue]
        self.assertIn(inv_id, inv_ids)

    def test_execute_simulated_payment_success(self):
        """Executing payment moves invoice status to PAID and logs EXECUTED transaction."""
        inv_id = self._create_approved_invoice("INV-EXEC-01", 3500.00)

        res = self.payment_service.execute_simulated_payment(
            invoice_id=inv_id,
            payment_rail="ACH Corporate Credit",
            simulated_by="Treasury_Ops_Alice",
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "EXECUTED")
        self.assertTrue(res["transaction_ref"].startswith("TXN-ACH-"))

        # Verify DB status
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM invoices WHERE id = ?;", (inv_id,))
        self.assertEqual(cursor.fetchone()["status"], "PAID")

        # Verify audit log
        cursor.execute("SELECT * FROM audit_logs WHERE invoice_id = ? AND action = 'SIMULATED_PAYMENT_SUCCESS';", (inv_id,))
        self.assertIsNotNone(cursor.fetchone())
        conn.close()

    def test_execute_simulated_payment_failure(self):
        """Simulated failure leaves invoice in APPROVED status and logs FAILED transaction."""
        inv_id = self._create_approved_invoice("INV-FAIL-01", 7500.00)

        res = self.payment_service.execute_simulated_payment(
            invoice_id=inv_id,
            payment_rail="Fedwire High-Value",
            simulated_by="Treasury_Ops_Alice",
            simulate_failure=True,
            failure_reason="Invalid Fedwire Routing Transit Number.",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("Invalid Fedwire", res["failure_reason"])

        # Invoice should remain APPROVED (not PAID) so it can be retried
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM invoices WHERE id = ?;", (inv_id,))
        self.assertEqual(cursor.fetchone()["status"], "APPROVED")

        # Verify audit log recorded warning
        cursor.execute("SELECT * FROM audit_logs WHERE invoice_id = ? AND action = 'SIMULATED_PAYMENT_FAILURE';", (inv_id,))
        self.assertIsNotNone(cursor.fetchone())
        conn.close()

    def test_duplicate_payment_prevention(self):
        """Cannot execute payment twice for the same invoice."""
        inv_id = self._create_approved_invoice("INV-DUP-01", 2000.00)

        # First execution succeeds
        self.payment_service.execute_simulated_payment(
            invoice_id=inv_id,
            payment_rail="Single-Use Virtual Card",
            simulated_by="Treasury_Ops_Alice",
        )

        # Second execution must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            self.payment_service.execute_simulated_payment(
                invoice_id=inv_id,
                payment_rail="Single-Use Virtual Card",
                simulated_by="Treasury_Ops_Alice",
            )
        self.assertIn("already marked as PAID", str(ctx.exception))

    def test_cannot_pay_unapproved_or_rejected_invoice(self):
        """Invoices that are not APPROVED cannot be processed for payment."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-UNAPP-01', 'Apex Cloud Services Inc.', 1500.00, 'RECEIVED');
            """
        )
        inv_id = cursor.lastrowid
        conn.commit()
        conn.close()

        with self.assertRaises(ValueError) as ctx:
            self.payment_service.execute_simulated_payment(
                invoice_id=inv_id,
                payment_rail="ACH Corporate Credit",
                simulated_by="Treasury_Ops_Alice",
            )
        self.assertIn("Only 'APPROVED' invoices can be paid", str(ctx.exception))

    def test_cannot_pay_invoice_with_critical_exception(self):
        """An invoice with an open CRITICAL exception cannot be paid even if artificially set to APPROVED."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-CRIT-01', 'Apex Cloud Services Inc.', 1500.00, 'APPROVED');
            """
        )
        inv_id = cursor.lastrowid
        # Add approval record
        cursor.execute(
            """
            INSERT INTO approvals_and_payments (invoice_id, decision, decision_by)
            VALUES (?, 'APPROVED', 'Manager');
            """,
            (inv_id,),
        )
        # Add open critical exception
        cursor.execute(
            """
            INSERT INTO exceptions (invoice_id, exception_type, severity, description, status)
            VALUES (?, 'BLOCKED_VENDOR', 'CRITICAL', 'OFAC sanctions match', 'OPEN');
            """,
            (inv_id,),
        )
        conn.commit()
        conn.close()

        with self.assertRaises(ValueError) as ctx:
            self.payment_service.execute_simulated_payment(
                invoice_id=inv_id,
                payment_rail="ACH Corporate Credit",
                simulated_by="Treasury_Ops_Alice",
            )
        self.assertIn("unresolved CRITICAL exception", str(ctx.exception))

    def test_payment_metrics_and_history(self):
        """Payment KPIs and transaction history accurately track disbursements."""
        inv_id1 = self._create_approved_invoice("INV-HIST-01", 1000.0)
        inv_id2 = self._create_approved_invoice("INV-HIST-02", 2000.0)

        # Pay invoice 1
        self.payment_service.execute_simulated_payment(
            invoice_id=inv_id1,
            payment_rail="ACH Corporate Credit",
            simulated_by="User1",
        )

        # Fail invoice 2
        self.payment_service.execute_simulated_payment(
            invoice_id=inv_id2,
            payment_rail="Fedwire High-Value",
            simulated_by="User1",
            simulate_failure=True,
            failure_reason="ACH network timeout",
        )

        metrics = self.payment_service.get_payment_metrics()
        self.assertEqual(metrics["executed_count"], 1)
        self.assertEqual(metrics["executed_volume"], 1000.0)
        self.assertEqual(metrics["failed_count"], 1)

        history = self.payment_service.get_transaction_history()
        self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
