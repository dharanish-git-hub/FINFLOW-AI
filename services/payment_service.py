"""
Payment Execution & Simulation Service (Task 08)
Coordinates human-authorized simulated payment disbursements across supported rails:
- ACH Corporate Credit
- Fedwire High-Value
- Single-Use Virtual Card

Strict backend rules:
1. Purely simulated; no external financial network or banking API is touched.
2. AI agents are strictly blocked from triggering payment execution.
3. Invoices must be human-approved (status='APPROVED').
4. Unresolved CRITICAL exceptions strictly block payment execution.
5. Invoices already paid or with existing EXECUTED transactions cannot be paid again.
6. Handles simulated failure scenarios with detailed error logging and audit trails.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from database.db import get_db_connection


# Supported simulated payment rails
PAYMENT_RAILS = {
    "ACH": "ACH Corporate Credit",
    "WIRE": "Fedwire High-Value",
    "VIRTUAL_CARD": "Single-Use Virtual Card",
}

RAIL_CODES = {
    "ACH Corporate Credit": "ACH",
    "Fedwire High-Value": "WIRE",
    "Single-Use Virtual Card": "VCARD",
}


class PaymentService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def prepare_payment_batch(
        self,
        invoice_id: int,
        decision: str,  # "APPROVED" or "REJECTED"
        decision_by: str,
        payment_method: str = "ACH",  # ACH, WIRE, VIRTUAL_CARD
        comments: str = "",
        override_reason: str = "",
    ) -> Dict[str, Any]:
        """
        Legacy compatibility method for batch approval/payment simulation.
        If APPROVED, executes simulated payment transaction and marks invoice PAID.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id, invoice_number, total_amount, vendor_name, status FROM invoices WHERE id = ?;", (invoice_id,))
        invoice = cursor.fetchone()
        if not invoice:
            conn.close()
            raise ValueError(f"Invoice with ID {invoice_id} not found.")

        simulated_ref = f"PAY-{uuid.uuid4().hex[:8].upper()}"
        payment_status = "EXECUTED" if decision == "APPROVED" else "CANCELLED"
        next_invoice_status = "PAID" if decision == "APPROVED" else "REJECTED"

        cursor.execute(
            """
            INSERT INTO approvals_and_payments (
                invoice_id, decision, decision_by, comments, override_reason, 
                payment_method, simulated_payment_id, payment_status, payment_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                invoice_id,
                decision,
                decision_by,
                comments,
                override_reason,
                payment_method,
                simulated_ref if decision == "APPROVED" else None,
                payment_status,
                datetime.now(timezone.utc).isoformat() if decision == "APPROVED" else None,
            ),
        )
        approval_id = cursor.lastrowid

        # Update invoice status
        cursor.execute("UPDATE invoices SET status = ? WHERE id = ?;", (next_invoice_status, invoice_id))

        # If executed, also log in payment_transactions table for Task 08 integrity
        if decision == "APPROVED":
            rail_name = PAYMENT_RAILS.get(payment_method.upper(), "ACH Corporate Credit")
            cursor.execute(
                """
                INSERT INTO payment_transactions (
                    transaction_ref, invoice_id, approval_id, vendor_name,
                    amount, currency, payment_rail, status, simulated_by, settled_at
                )
                VALUES (?, ?, ?, ?, ?, 'USD', ?, 'EXECUTED', ?, ?);
                """,
                (
                    simulated_ref,
                    invoice_id,
                    approval_id,
                    invoice["vendor_name"] or "Vendor",
                    float(invoice["total_amount"]),
                    rail_name,
                    decision_by,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        # Audit trail
        cursor.execute(
            """
            INSERT INTO audit_logs (invoice_id, agent_name, action, level, message, payload_json)
            VALUES (?, 'HumanApprover', ?, ?, ?, ?);
            """,
            (
                invoice_id,
                f"PAYMENT_{decision}",
                "SUCCESS" if decision == "APPROVED" else "WARNING",
                f"User '{decision_by}' {decision.lower()} invoice #{invoice['invoice_number']} for ${invoice['total_amount']:,.2f}.",
                f'{{"payment_ref": "{simulated_ref}", "method": "{payment_method}", "amount": {invoice["total_amount"]}}}',
            ),
        )

        conn.commit()
        conn.close()

        return {
            "invoice_id": invoice_id,
            "decision": decision,
            "status": payment_status,
            "simulated_ref": simulated_ref if decision == "APPROVED" else None,
            "invoice_status": next_invoice_status,
        }

    def get_payment_queue(self, status_filter: str = "ELIGIBLE") -> List[Dict[str, Any]]:
        """
        Retrieves invoices for the payment management screen.
        ELIGIBLE: status='APPROVED', human approved, and has no successful payment transaction.
        PAID: status='PAID' or has EXECUTED transaction.
        ALL: all approved and paid records.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        if status_filter == "ELIGIBLE":
            # Approved invoices that don't have an EXECUTED transaction and status is 'APPROVED'
            cursor.execute(
                """
                SELECT 
                    inv.id,
                    inv.invoice_number,
                    inv.vendor_name,
                    inv.total_amount,
                    inv.currency,
                    inv.status as invoice_status,
                    inv.due_date,
                    inv.created_at,
                    appr.id as approval_id,
                    appr.decision,
                    appr.decision_by as approved_by,
                    appr.payment_method,
                    appr.created_at as approval_date,
                    (
                        SELECT COUNT(*) 
                        FROM exceptions 
                        WHERE exceptions.invoice_id = inv.id 
                          AND exceptions.severity = 'CRITICAL' 
                          AND exceptions.status = 'OPEN'
                    ) as open_critical_exceptions
                FROM invoices inv
                INNER JOIN (
                    -- Latest approval record per invoice
                    SELECT * FROM approvals_and_payments
                    WHERE id IN (
                        SELECT MAX(id) FROM approvals_and_payments WHERE decision = 'APPROVED' GROUP BY invoice_id
                    )
                ) appr ON inv.id = appr.invoice_id
                WHERE inv.status = 'APPROVED'
                  AND inv.id NOT IN (
                      SELECT invoice_id FROM payment_transactions WHERE status = 'EXECUTED'
                  )
                ORDER BY appr.created_at DESC;
                """
            )
        elif status_filter == "PAID":
            cursor.execute(
                """
                SELECT 
                    inv.id,
                    inv.invoice_number,
                    inv.vendor_name,
                    inv.total_amount,
                    inv.currency,
                    inv.status as invoice_status,
                    inv.due_date,
                    pt.transaction_ref,
                    pt.payment_rail,
                    pt.status as transaction_status,
                    pt.settled_at,
                    pt.simulated_by
                FROM invoices inv
                INNER JOIN payment_transactions pt ON inv.id = pt.invoice_id
                WHERE pt.status = 'EXECUTED'
                ORDER BY pt.settled_at DESC;
                """
            )
        else:  # ALL
            cursor.execute(
                """
                SELECT 
                    inv.id,
                    inv.invoice_number,
                    inv.vendor_name,
                    inv.total_amount,
                    inv.currency,
                    inv.status as invoice_status,
                    inv.due_date,
                    appr.decision_by as approved_by,
                    appr.created_at as approval_date
                FROM invoices inv
                LEFT JOIN approvals_and_payments appr ON inv.id = appr.invoice_id AND appr.decision = 'APPROVED'
                WHERE inv.status IN ('APPROVED', 'PAID')
                ORDER BY inv.id DESC;
                """
            )

        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def verify_payment_eligibility(self, invoice_id: int) -> Dict[str, Any]:
        """
        Validates whether an invoice satisfies all prerequisite criteria for payment disbursement:
        1. Invoice exists.
        2. Status is APPROVED (not REJECTED, CANCELLED, or already PAID).
        3. Human approval record exists.
        4. No open CRITICAL exceptions remain on the invoice.
        5. No previous EXECUTED payment transaction exists.
        6. Associated vendor details exist.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # 1. Invoice Record
        cursor.execute("SELECT * FROM invoices WHERE id = ?;", (invoice_id,))
        invoice_row = cursor.fetchone()
        if not invoice_row:
            conn.close()
            return {"eligible": False, "reason": f"Invoice ID {invoice_id} not found."}
        invoice = dict(invoice_row)

        # 2. Check Invoice Status
        if invoice["status"] == "PAID":
            conn.close()
            return {"eligible": False, "reason": f"Invoice #{invoice['invoice_number']} is already marked as PAID."}
        if invoice["status"] in ["REJECTED", "CORRECTION_REQUESTED", "RECEIVED", "VERIFYING", "EXCEPTION"]:
            conn.close()
            return {
                "eligible": False,
                "reason": f"Invoice #{invoice['invoice_number']} has status '{invoice['status']}'. Only 'APPROVED' invoices can be paid.",
            }

        # 3. Check Human Approval
        cursor.execute(
            """
            SELECT * FROM approvals_and_payments 
            WHERE invoice_id = ? AND decision = 'APPROVED' 
            ORDER BY id DESC LIMIT 1;
            """,
            (invoice_id,),
        )
        approval_row = cursor.fetchone()
        if not approval_row:
            conn.close()
            return {
                "eligible": False,
                "reason": f"No valid human approval record found for Invoice #{invoice['invoice_number']}.",
            }
        approval = dict(approval_row)

        # 4. Check for unresolved CRITICAL exceptions
        cursor.execute(
            """
            SELECT COUNT(*) as crit_count FROM exceptions 
            WHERE invoice_id = ? AND severity = 'CRITICAL' AND status = 'OPEN';
            """,
            (invoice_id,),
        )
        crit_count = cursor.fetchone()["crit_count"]
        if crit_count > 0:
            conn.close()
            return {
                "eligible": False,
                "reason": f"Invoice #{invoice['invoice_number']} has {crit_count} unresolved CRITICAL exception(s). Disbursement blocked.",
            }

        # 5. Check duplicate payment transaction
        cursor.execute(
            """
            SELECT transaction_ref, settled_at FROM payment_transactions 
            WHERE invoice_id = ? AND status = 'EXECUTED';
            """,
            (invoice_id,),
        )
        existing_txn = cursor.fetchone()
        if existing_txn:
            conn.close()
            return {
                "eligible": False,
                "reason": f"Payment already executed for Invoice #{invoice['invoice_number']} (Ref: {existing_txn['transaction_ref']}). Duplicate disbursement prevented.",
            }

        # 6. Retrieve Vendor Bank / Account info if available
        vendor_info = {}
        if invoice.get("vendor_name"):
            cursor.execute("SELECT * FROM vendors WHERE name = ? LIMIT 1;", (invoice["vendor_name"],))
            v_row = cursor.fetchone()
            if v_row:
                vendor_info = dict(v_row)

        conn.close()
        return {
            "eligible": True,
            "invoice": invoice,
            "approval": approval,
            "vendor": vendor_info,
        }

    def execute_simulated_payment(
        self,
        invoice_id: int,
        payment_rail: str,
        simulated_by: str,
        bank_account: Optional[str] = None,
        simulate_failure: bool = False,
        failure_reason: str = "Simulated bank processing failure: insufficient funds or invalid routing.",
    ) -> Dict[str, Any]:
        """
        Executes a transactional simulated payment execution.
        If simulate_failure is False:
          - Creates payment_transactions record with status='EXECUTED'
          - Updates invoices.status = 'PAID'
          - Updates approvals_and_payments.payment_status = 'EXECUTED'
          - Writes structured audit log
        If simulate_failure is True:
          - Creates payment_transactions record with status='FAILED'
          - Keeps invoices.status = 'APPROVED'
          - Writes warning audit log
        """
        # Step 1: Pre-flight Eligibility Validation
        eligibility = self.verify_payment_eligibility(invoice_id)
        if not eligibility["eligible"]:
            raise ValueError(f"PAYMENT EXECUTION BLOCKED: {eligibility['reason']}")

        invoice = eligibility["invoice"]
        approval = eligibility["approval"]
        vendor_name = invoice.get("vendor_name") or "Unknown Vendor"
        amount = float(invoice["total_amount"])

        # Determine rail tag
        rail_tag = RAIL_CODES.get(payment_rail, "PAY")
        random_code = uuid.uuid4().hex[:8].upper()
        txn_ref = f"TXN-{rail_tag}-{random_code}"
        now_iso = datetime.now(timezone.utc).isoformat()

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # Begin transaction
            cursor.execute("BEGIN IMMEDIATE;")

            if not simulate_failure:
                # SUCCESS OUTCOME
                # 1. Insert payment_transaction
                cursor.execute(
                    """
                    INSERT INTO payment_transactions (
                        transaction_ref, invoice_id, approval_id, vendor_name, 
                        amount, currency, payment_rail, bank_account, status, 
                        simulated_by, created_at, settled_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'EXECUTED', ?, ?, ?);
                    """,
                    (
                        txn_ref,
                        invoice_id,
                        approval["id"],
                        vendor_name,
                        amount,
                        invoice.get("currency", "USD"),
                        payment_rail,
                        bank_account or f"SIM-ACCT-****{uuid.uuid4().hex[:4].upper()}",
                        simulated_by,
                        now_iso,
                        now_iso,
                    ),
                )
                txn_id = cursor.lastrowid

                # 2. Update invoice status to PAID
                cursor.execute("UPDATE invoices SET status = 'PAID' WHERE id = ?;", (invoice_id,))

                # 3. Update approval record payment_status
                cursor.execute(
                    """
                    UPDATE approvals_and_payments 
                    SET payment_status = 'EXECUTED', payment_date = ?, simulated_payment_id = ? 
                    WHERE id = ?;
                    """,
                    (now_iso, txn_ref, approval["id"]),
                )

                # 4. Audit Trail
                cursor.execute(
                    """
                    INSERT INTO audit_logs (
                        invoice_id, agent_name, action, level, message, payload_json,
                        actor, previous_status, new_status, category
                    )
                    VALUES (?, 'PaymentExecutionService', 'SIMULATED_PAYMENT_SUCCESS', 'SUCCESS', ?, ?, ?, 'APPROVED', 'PAID', 'PAYMENT');
                    """,
                    (
                        invoice_id,
                        f"Simulated payment {txn_ref} of ${amount:,.2f} executed via {payment_rail} to '{vendor_name}' by '{simulated_by}'.",
                        f'{{"txn_ref": "{txn_ref}", "amount": {amount}, "rail": "{payment_rail}", "operator": "{simulated_by}", "status": "EXECUTED"}}',
                        simulated_by,
                    ),
                )

                conn.commit()
                return {
                    "success": True,
                    "status": "EXECUTED",
                    "transaction_ref": txn_ref,
                    "transaction_id": txn_id,
                    "amount": amount,
                    "payment_rail": payment_rail,
                    "settled_at": now_iso,
                    "vendor_name": vendor_name,
                    "invoice_number": invoice["invoice_number"],
                    "message": f"Successfully simulated payment {txn_ref} for ${amount:,.2f}.",
                }

            else:
                # FAILED OUTCOME (Simulated network/bank error)
                cursor.execute(
                    """
                    INSERT INTO payment_transactions (
                        transaction_ref, invoice_id, approval_id, vendor_name, 
                        amount, currency, payment_rail, bank_account, status, 
                        failure_reason, simulated_by, created_at, settled_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'FAILED', ?, ?, ?, NULL);
                    """,
                    (
                        txn_ref,
                        invoice_id,
                        approval["id"],
                        vendor_name,
                        amount,
                        invoice.get("currency", "USD"),
                        payment_rail,
                        bank_account or f"SIM-ACCT-****{uuid.uuid4().hex[:4].upper()}",
                        failure_reason,
                        simulated_by,
                        now_iso,
                    ),
                )
                txn_id = cursor.lastrowid

                # Update approval record payment_status to FAILED
                cursor.execute(
                    """
                    UPDATE approvals_and_payments 
                    SET payment_status = 'FAILED' 
                    WHERE id = ?;
                    """,
                    (approval["id"],),
                )

                # Audit Log
                cursor.execute(
                    """
                    INSERT INTO audit_logs (
                        invoice_id, agent_name, action, level, message, payload_json,
                        actor, previous_status, new_status, category
                    )
                    VALUES (?, 'PaymentExecutionService', 'SIMULATED_PAYMENT_FAILURE', 'WARNING', ?, ?, ?, 'APPROVED', 'APPROVED', 'PAYMENT');
                    """,
                    (
                        invoice_id,
                        f"Simulated payment attempt {txn_ref} for ${amount:,.2f} via {payment_rail} failed: {failure_reason}",
                        f'{{"txn_ref": "{txn_ref}", "amount": {amount}, "rail": "{payment_rail}", "operator": "{simulated_by}", "status": "FAILED", "reason": "{failure_reason}"}}',
                        simulated_by,
                    ),
                )

                conn.commit()
                return {
                    "success": False,
                    "status": "FAILED",
                    "transaction_ref": txn_ref,
                    "transaction_id": txn_id,
                    "amount": amount,
                    "payment_rail": payment_rail,
                    "failure_reason": failure_reason,
                    "vendor_name": vendor_name,
                    "invoice_number": invoice["invoice_number"],
                    "message": f"Simulated payment failed: {failure_reason}",
                }

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_payment_metrics(self) -> Dict[str, Any]:
        """Calculates summary KPIs across simulated payment operations."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Total executed transactions & volume
        cursor.execute(
            """
            SELECT 
                COUNT(*) as executed_count,
                COALESCE(SUM(amount), 0.0) as executed_volume
            FROM payment_transactions
            WHERE status = 'EXECUTED';
            """
        )
        exec_row = cursor.fetchone()

        # Total failed transactions
        cursor.execute(
            """
            SELECT COUNT(*) as failed_count
            FROM payment_transactions
            WHERE status = 'FAILED';
            """
        )
        fail_row = cursor.fetchone()

        # Eligible invoices in queue awaiting disbursement
        cursor.execute(
            """
            SELECT 
                COUNT(*) as pending_count,
                COALESCE(SUM(total_amount), 0.0) as pending_volume
            FROM invoices
            WHERE status = 'APPROVED'
              AND id NOT IN (SELECT invoice_id FROM payment_transactions WHERE status = 'EXECUTED');
            """
        )
        pend_row = cursor.fetchone()

        conn.close()

        return {
            "executed_count": exec_row["executed_count"] if exec_row else 0,
            "executed_volume": float(exec_row["executed_volume"]) if exec_row else 0.0,
            "failed_count": fail_row["failed_count"] if fail_row else 0,
            "pending_count": pend_row["pending_count"] if pend_row else 0,
            "pending_volume": float(pend_row["pending_volume"]) if pend_row else 0.0,
        }

    def get_transaction_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves past simulated payment transactions."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                pt.id,
                pt.transaction_ref,
                pt.invoice_id,
                inv.invoice_number,
                pt.vendor_name,
                pt.amount,
                pt.currency,
                pt.payment_rail,
                pt.bank_account,
                pt.status,
                pt.failure_reason,
                pt.simulated_by,
                pt.created_at,
                pt.settled_at
            FROM payment_transactions pt
            LEFT JOIN invoices inv ON pt.invoice_id = inv.id
            ORDER BY pt.id DESC
            LIMIT ?;
            """,
            (limit,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
