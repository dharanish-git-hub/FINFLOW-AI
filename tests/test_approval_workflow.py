"""
Tests for Human Approval and Workflow Management (Task 07):
- Approving a valid invoice
- Attempting to approve an invoice with unresolved critical exception
- Rejecting an invoice with reason
- Requesting corrections
- Preventing duplicate approval
- Preventing rejected invoices from reaching payment preparation
- Preserving approval history
"""

import os
import tempfile
import unittest
from database.seed_data import seed_database
from database.db import get_db_connection
from services.approval_workflow_service import ApprovalWorkflowService, HIGH_VALUE_THRESHOLD


class TestApprovalWorkflowService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_approvals.db")
        seed_database(self.db_path)
        self.service = ApprovalWorkflowService(db_path=self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_approve_valid_invoice(self):
        """Approving a clean, eligible invoice succeeds and generates simulated payment reference."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-APPR-001', 'Apex Cloud Services Inc.', 5000.00, 'PENDING_APPROVAL');
            """
        )
        inv_id = cursor.lastrowid
        conn.commit()
        conn.close()

        res = self.service.process_approval_decision(
            invoice_id=inv_id,
            action="APPROVE",
            reviewer_name="CFO_Jane",
            payment_method="ACH",
        )
        self.assertEqual(res["new_invoice_status"], "APPROVED")
        self.assertEqual(res["payment_status"], "PREPARED")
        self.assertTrue(res["simulated_payment_ref"].startswith("PAY-"))

    def test_approve_blocked_by_critical_exception(self):
        """Attempting to approve an invoice with an unresolved CRITICAL exception is blocked."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-CRIT-002', 'Blocked Shell Corp', 15000.00, 'PENDING_APPROVAL');
            """
        )
        inv_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO exceptions (invoice_id, exception_type, severity, description, status)
            VALUES (?, 'BLOCKED_VENDOR', 'CRITICAL', 'Restricted entity', 'OPEN');
            """,
            (inv_id,),
        )
        conn.commit()
        conn.close()

        with self.assertRaises(ValueError) as ctx:
            self.service.process_approval_decision(
                invoice_id=inv_id,
                action="APPROVE",
                reviewer_name="CFO_Jane",
                high_value_confirmed=True,
            )
        self.assertIn("CRITICAL exception", str(ctx.exception))

    def test_high_value_confirmation_required(self):
        """High-value invoices (>= $10,000) require explicit confirmation."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-HIGH-VAL-003', 'Apex Cloud Services Inc.', 25000.00, 'PENDING_APPROVAL');
            """
        )
        inv_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Without confirmation -> must fail
        with self.assertRaises(ValueError) as ctx:
            self.service.process_approval_decision(
                invoice_id=inv_id,
                action="APPROVE",
                reviewer_name="CFO_Jane",
                high_value_confirmed=False,
            )
        self.assertIn("HIGH VALUE CONFIRMATION REQUIRED", str(ctx.exception))

        # With confirmation -> must succeed
        res = self.service.process_approval_decision(
            invoice_id=inv_id,
            action="APPROVE",
            reviewer_name="CFO_Jane",
            high_value_confirmed=True,
        )
        self.assertEqual(res["new_invoice_status"], "APPROVED")

    def test_reject_invoice_requires_reason_and_blocks_disbursement(self):
        """Rejecting an invoice requires an explicit reason and blocks subsequent payment approval."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-REJ-004', 'Apex Cloud Services Inc.', 3000.00, 'PENDING_APPROVAL');
            """
        )
        inv_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Rejection without reason fails
        with self.assertRaises(ValueError):
            self.service.process_approval_decision(
                invoice_id=inv_id,
                action="REJECT",
                reviewer_name="Auditor_Tom",
                rejection_reason="",
            )

        # Rejection with reason succeeds
        res = self.service.process_approval_decision(
            invoice_id=inv_id,
            action="REJECT",
            reviewer_name="Auditor_Tom",
            rejection_reason="Duplicate billing claimed by vendor.",
        )
        self.assertEqual(res["new_invoice_status"], "REJECTED")

        # Attempt to approve a rejected invoice -> must fail
        with self.assertRaises(ValueError) as ctx:
            self.service.process_approval_decision(
                invoice_id=inv_id,
                action="APPROVE",
                reviewer_name="CFO_Jane",
            )
        self.assertIn("permanently REJECTED", str(ctx.exception))

    def test_request_correction_workflow(self):
        """Requesting correction returns invoice to CORRECTION_REQUESTED status."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-CORR-005', 'Modern Office Interiors', 4500.00, 'PENDING_APPROVAL');
            """
        )
        inv_id = cursor.lastrowid
        conn.commit()
        conn.close()

        res = self.service.process_approval_decision(
            invoice_id=inv_id,
            action="REQUEST_CORRECTION",
            reviewer_name="Auditor_Tom",
            correction_reason="Please provide proof of delivery for 10 ergonomic chairs.",
        )
        self.assertEqual(res["new_invoice_status"], "CORRECTION_REQUESTED")

    def test_prevent_duplicate_approval(self):
        """Once an invoice is approved/paid, duplicate approval attempts are rejected."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-DUP-APP-006', 'Apex Cloud Services Inc.', 1500.00, 'PENDING_APPROVAL');
            """
        )
        inv_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Initial approval
        self.service.process_approval_decision(
            invoice_id=inv_id,
            action="APPROVE",
            reviewer_name="CFO_Jane",
        )

        # Second approval attempt must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            self.service.process_approval_decision(
                invoice_id=inv_id,
                action="APPROVE",
                reviewer_name="CFO_Jane",
            )
        self.assertIn("Duplicate approval is prohibited", str(ctx.exception))

    def test_preserve_approval_history(self):
        """Historical approval actions are preserved in SQLite."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-HIST-007', 'CyberShield Security Corp', 2000.00, 'PENDING_APPROVAL');
            """
        )
        inv_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Step 1: Request correction
        self.service.process_approval_decision(
            invoice_id=inv_id,
            action="REQUEST_CORRECTION",
            reviewer_name="Auditor_Tom",
            correction_reason="Missing PO line reconciliation.",
        )

        bundle = self.service.get_invoice_full_review_bundle(inv_id)
        self.assertEqual(len(bundle["approval_history"]), 1)
        self.assertEqual(bundle["approval_history"][0]["decision"], "CORRECTION_REQUESTED")


if __name__ == "__main__":
    unittest.main()
