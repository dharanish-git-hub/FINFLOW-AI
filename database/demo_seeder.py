"""
Synthetic Demo Data Seeder for FINFLOW AI (Task 10)
Seeds realistic, reproducible AP demo scenarios:
1. Valid Invoice -> Reaches simulated payment execution success ($12,500.00).
2. PO Mismatch Invoice -> Line quantity / amount discrepancy needing review ($7,500.00).
3. Unknown Vendor Invoice -> Unregistered vendor requiring compliance onboarding ($4,200.00).
4. Duplicate Invoice -> Duplicate submission of previously processed invoice.
5. Critical Exception Invoice -> Blocked / sanctioned entity invoice ($45,000.00).
6. Simulated Payment Failure -> Approved invoice with simulated routing decline ($8,900.00).

Can be executed standalone or called via `reset_and_seed_demo_data(db_path)`.
Safe for testing: clears tables and re-seeds known clean reference data without touching credentials.
"""

import os
import uuid
from datetime import datetime, timezone
from database.db import get_db_connection, init_db
from database.seed_data import seed_database


def reset_and_seed_demo_data(db_path: str = None):
    """Resets transactional tables and populates full synthetic demo scenario records."""
    init_db(db_path)
    seed_database(db_path)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Clear previous transactional data
    cursor.execute("DELETE FROM payment_transactions;")
    cursor.execute("DELETE FROM approvals_and_payments;")
    cursor.execute("DELETE FROM exceptions;")
    cursor.execute("DELETE FROM invoice_items;")
    cursor.execute("DELETE FROM verification_history;")
    cursor.execute("DELETE FROM orchestrator_runs;")
    cursor.execute("DELETE FROM audit_logs;")
    cursor.execute("DELETE FROM invoices;")
    conn.commit()

    now_iso = datetime.now(timezone.utc).isoformat()

    # =========================================================================
    # SCENARIO 1: Valid Invoice (Apex Cloud) -> APPROVED & PAID (Success)
    # =========================================================================
    cursor.execute(
        """
        INSERT INTO invoices (
            invoice_number, vendor_id, vendor_name, po_number, file_name, file_hash,
            invoice_date, due_date, subtotal, tax_amount, total_amount, currency, status, payment_terms
        )
        VALUES ('INV-2026-001', 'VND-001', 'Apex Cloud Services Inc.', 'PO-2026-001', 'invoice_valid_apex.pdf', 'hash_demo_apex_001',
                '2026-11-01', '2026-12-01', 11500.00, 1000.00, 12500.00, 'USD', 'PAID', 'Net 30');
        """
    )
    inv1_id = cursor.lastrowid

    # Items for Inv 1
    cursor.execute(
        """
        INSERT INTO invoice_items (invoice_id, item_description, quantity, unit_price, total_price)
        VALUES 
            (?, 'Cloud Compute Enterprise Tier (Monthly)', 1, 8000.00, 8000.00),
            (?, 'Dedicated High-Speed Interconnect', 1, 3500.00, 3500.00);
        """,
        (inv1_id, inv1_id),
    )

    # Human Approval record
    cursor.execute(
        """
        INSERT INTO approvals_and_payments (
            invoice_id, decision, decision_by, comments, payment_method, simulated_payment_id, payment_status, payment_date
        )
        VALUES (?, 'APPROVED', 'cfo@enterprise.com', 'Approved based on verified 3-way match against PO-2026-001.', 'ACH', 'PAY-AUTH-9910', 'EXECUTED', ?);
        """,
        (inv1_id, now_iso),
    )
    appr1_id = cursor.lastrowid

    # Simulated Payment Transaction (Executed)
    cursor.execute(
        """
        INSERT INTO payment_transactions (
            transaction_ref, invoice_id, approval_id, vendor_name, amount, currency, payment_rail, bank_account, status, simulated_by, settled_at
        )
        VALUES ('TXN-ACH-DEMO881', ?, ?, 'Apex Cloud Services Inc.', 12500.00, 'USD', 'ACH Corporate Credit', 'US-ACH-121000358-992384', 'EXECUTED', 'Treasury_Officer_Jane', ?);
        """,
        (inv1_id, appr1_id, now_iso),
    )

    # Audit Logs for Inv 1
    cursor.execute(
        """
        INSERT INTO audit_logs (invoice_id, agent_name, action, level, message, actor, previous_status, new_status, category)
        VALUES 
            (?, 'IntakeAgent', 'INVOICE_EXTRACTED', 'SUCCESS', 'Extracted invoice #INV-2026-001 ($12,500.00)', 'IntakeAgent', 'RECEIVED', 'EXTRACTED', 'INTAKE'),
            (?, 'HumanSignatory', 'WORKFLOW_APPROVE', 'SUCCESS', 'CFO Jane signed off on voucher ($12,500.00)', 'cfo@enterprise.com', 'PENDING_APPROVAL', 'APPROVED', 'APPROVAL'),
            (?, 'PaymentExecutionService', 'SIMULATED_PAYMENT_SUCCESS', 'SUCCESS', 'Simulated disbursement TXN-ACH-DEMO881 executed for $12,500.00', 'Treasury_Officer_Jane', 'APPROVED', 'PAID', 'PAYMENT');
        """,
        (inv1_id, inv1_id, inv1_id),
    )

    # =========================================================================
    # SCENARIO 2: PO Mismatch Invoice (Global Logistics) -> EXCEPTION / NEEDS_REVIEW
    # =========================================================================
    cursor.execute(
        """
        INSERT INTO invoices (
            invoice_number, vendor_id, vendor_name, po_number, file_name, file_hash,
            invoice_date, due_date, subtotal, tax_amount, total_amount, currency, status, payment_terms
        )
        VALUES ('INV-2026-002', 'VND-002', 'Global Logistics & Freight LLC', 'PO-2026-002', 'invoice_mismatch_logistics.pdf', 'hash_demo_log_002',
                '2026-11-05', '2026-12-05', 7100.00, 400.00, 7500.00, 'USD', 'EXCEPTION', 'Net 30');
        """
    )
    inv2_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO exceptions (invoice_id, exception_type, severity, description, status, ai_summary, recommended_action)
        VALUES (?, 'AMOUNT_MISMATCH', 'HIGH', 'Billed total $7,500.00 exceeds PO-2026-002 expected total $4,800.00 by $2,700.00 (+56.25%).',
                'OPEN', 'Invoice contains 2 additional unbudgeted freight containers not specified in original purchase agreement.',
                'Request credit memo or revised invoice from vendor referencing amended purchase order.');
        """,
        (inv2_id,),
    )

    cursor.execute(
        """
        INSERT INTO audit_logs (invoice_id, agent_name, action, level, message, actor, previous_status, new_status, category)
        VALUES (?, 'VerificationAgent', 'PO_LINE_MISMATCH', 'WARNING', 'Flagged amount mismatch of $2,700.00 against PO-2026-002', 'VerificationAgent', 'EXTRACTED', 'EXCEPTION', 'VERIFICATION');
        """,
        (inv2_id,),
    )

    # =========================================================================
    # SCENARIO 3: Unknown Vendor Invoice (Shell Logistics Corp) -> EXCEPTION
    # =========================================================================
    cursor.execute(
        """
        INSERT INTO invoices (
            invoice_number, vendor_id, vendor_name, po_number, file_name, file_hash,
            invoice_date, due_date, subtotal, tax_amount, total_amount, currency, status, payment_terms
        )
        VALUES ('INV-2026-003', NULL, 'Apex Cloud Services Inc (Spoofed)', NULL, 'invoice_unknown_shell.pdf', 'hash_demo_unknown_003',
                '2026-11-10', '2026-11-20', 4000.00, 200.00, 4200.00, 'USD', 'EXCEPTION', 'Due on Receipt');
        """
    )
    inv3_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO exceptions (invoice_id, exception_type, severity, description, status, ai_summary, recommended_action)
        VALUES (?, 'UNKNOWN_VENDOR', 'HIGH', 'Vendor name could not be mapped to any registered master vendor record.',
                'OPEN', 'Billing address and remit-to routing number do not match approved master records.',
                'Initiate formal supplier onboarding verification before routing for approval.');
        """,
        (inv3_id,),
    )

    # =========================================================================
    # SCENARIO 4: Duplicate Invoice Submission -> CRITICAL EXCEPTION / BLOCKED
    # =========================================================================
    cursor.execute(
        """
        INSERT INTO invoices (
            invoice_number, vendor_id, vendor_name, po_number, file_name, file_hash,
            invoice_date, due_date, subtotal, tax_amount, total_amount, currency, status, payment_terms
        )
        VALUES ('INV-2026-001', 'VND-001', 'Apex Cloud Services Inc.', 'PO-2026-001', 'invoice_valid_apex_resubmit.pdf', 'hash_demo_apex_001',
                '2026-11-01', '2026-12-01', 11500.00, 1000.00, 12500.00, 'USD', 'EXCEPTION', 'Net 30');
        """
    )
    inv4_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO exceptions (invoice_id, exception_type, severity, description, status, ai_summary, recommended_action)
        VALUES (?, 'DUPLICATE_INVOICE', 'CRITICAL', 'Identical invoice number INV-2026-001 already settled under payment ref TXN-ACH-DEMO881.',
                'OPEN', 'Exact file hash and invoice identifier match existing paid voucher #1.',
                'Block invoice disbursement immediately to prevent duplicate cash leakage.');
        """,
        (inv4_id,),
    )

    # =========================================================================
    # SCENARIO 5: Critical Sanction Exception (Blocked Shell Corp) -> BLOCKED
    # =========================================================================
    cursor.execute(
        """
        INSERT INTO invoices (
            invoice_number, vendor_id, vendor_name, po_number, file_name, file_hash,
            invoice_date, due_date, subtotal, tax_amount, total_amount, currency, status, payment_terms
        )
        VALUES ('INV-2026-005', 'VND-005', 'Blocked Shell Corp International', 'PO-2026-005', 'invoice_sanction_shell.pdf', 'hash_demo_shell_005',
                '2026-11-12', '2026-11-25', 45000.00, 0.00, 45000.00, 'USD', 'EXCEPTION', 'Immediate Wire');
        """
    )
    inv5_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO exceptions (invoice_id, exception_type, severity, description, status, ai_summary, recommended_action)
        VALUES (?, 'BLOCKED_VENDOR', 'CRITICAL', 'Entity identified on OFAC / restricted treasury compliance watch list.',
                'OPEN', 'Secondary verification matched offshore remit beneficiary against watch list.',
                'Completely freeze invoice voucher and notify Chief Compliance Officer.');
        """,
        (inv5_id,),
    )

    # =========================================================================
    # SCENARIO 6: Simulated Payment Failure -> APPROVED with FAILED Transaction
    # =========================================================================
    cursor.execute(
        """
        INSERT INTO invoices (
            invoice_number, vendor_id, vendor_name, po_number, file_name, file_hash,
            invoice_date, due_date, subtotal, tax_amount, total_amount, currency, status, payment_terms
        )
        VALUES ('INV-2026-006', 'VND-003', 'CyberShield Security Corp', 'PO-2026-003', 'invoice_cybershield_audit.pdf', 'hash_demo_cyber_006',
                '2026-11-15', '2026-12-15', 8200.00, 700.00, 8900.00, 'USD', 'APPROVED', 'Net 30');
        """
    )
    inv6_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO approvals_and_payments (
            invoice_id, decision, decision_by, comments, payment_method, simulated_payment_id, payment_status, payment_date
        )
        VALUES (?, 'APPROVED', 'cfo@enterprise.com', 'Approved annual security tooling license.', 'Fedwire High-Value', 'PAY-AUTH-CYBER', 'FAILED', ?);
        """,
        (inv6_id, now_iso),
    )
    appr6_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO payment_transactions (
            transaction_ref, invoice_id, approval_id, vendor_name, amount, currency, payment_rail, bank_account, status, failure_reason, simulated_by, settled_at
        )
        VALUES ('TXN-WIRE-FAIL702', ?, ?, 'CyberShield Security Corp', 8900.00, 'USD', 'Fedwire High-Value', 'US-ACH-051400549-332910', 'FAILED',
                'Simulated bank network timeout: Fedwire RTN unreachable during processing window.', 'Treasury_Officer_Jane', NULL);
        """,
        (inv6_id, appr6_id),
    )

    cursor.execute(
        """
        INSERT INTO audit_logs (invoice_id, agent_name, action, level, message, actor, previous_status, new_status, category)
        VALUES (?, 'PaymentExecutionService', 'SIMULATED_PAYMENT_FAILURE', 'WARNING', 'Payment attempt TXN-WIRE-FAIL702 declined: Fedwire RTN unreachable.', 'Treasury_Officer_Jane', 'APPROVED', 'APPROVED', 'PAYMENT');
        """,
        (inv6_id,),
    )

    conn.commit()
    conn.close()
    print("FINFLOW AI synthetic demo dataset successfully populated.")


if __name__ == "__main__":
    import sys
    custom_db = sys.argv[1] if len(sys.argv) > 1 else None
    reset_and_seed_demo_data(custom_db)
