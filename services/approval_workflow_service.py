"""
Approval and Workflow Management Service for FINFLOW AI.
Enforces strict human-in-the-loop validation, prevents duplicate approvals, blocks invalid transitions,
mandates justification for rejections and corrections, and handles high-value invoice confirmations.
"""

import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from database.db import get_db_connection

HIGH_VALUE_THRESHOLD = 10000.00  # Requires explicit high-value confirmation


class ApprovalWorkflowService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def get_approval_queue(self, status_filter: str = "PENDING_APPROVAL") -> List[Dict[str, Any]]:
        """
        Retrieves invoices based on workflow status:
        PENDING_APPROVAL, APPROVED, REJECTED, CORRECTION_REQUESTED, ALL
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        where_clause = ""
        params = []
        if status_filter != "ALL":
            where_clause = "WHERE i.status = ?"
            params.append(status_filter)

        cursor.execute(
            f"""
            SELECT i.id, i.invoice_number, i.vendor_name, i.vendor_id, i.po_number,
                   i.total_amount, i.subtotal, i.tax_amount, i.currency, i.invoice_date,
                   i.due_date, i.status, i.payment_terms, i.created_at,
                   (SELECT COUNT(*) FROM exceptions e WHERE e.invoice_id = i.id AND e.status = 'OPEN') as open_exceptions_count,
                   (SELECT COUNT(*) FROM exceptions e WHERE e.invoice_id = i.id AND e.status = 'OPEN' AND e.severity = 'CRITICAL') as critical_exceptions_count,
                   (SELECT COUNT(*) FROM exceptions e WHERE e.invoice_id = i.id AND e.status = 'OPEN' AND e.severity = 'HIGH') as high_exceptions_count
            FROM invoices i
            {where_clause}
            ORDER BY CASE i.status WHEN 'PENDING_APPROVAL' THEN 1 WHEN 'CORRECTION_REQUESTED' THEN 2 ELSE 3 END, i.id DESC;
            """,
            params,
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_invoice_full_review_bundle(self, invoice_id: int) -> Dict[str, Any]:
        """
        Gathers complete review bundle for an invoice:
        - Invoice metadata & itemized line items
        - Vendor verification results
        - Purchase order match details
        - Financial validation results
        - Exceptions list with severities and AI root-cause investigation
        - Historical approval actions
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # 1. Invoice record
        cursor.execute("SELECT * FROM invoices WHERE id = ?;", (invoice_id,))
        invoice = cursor.fetchone()
        if not invoice:
            conn.close()
            raise ValueError(f"Invoice #{invoice_id} not found.")
        invoice_dict = dict(invoice)

        # 2. Line items
        cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?;", (invoice_id,))
        line_items = [dict(r) for r in cursor.fetchall()]
        invoice_dict["line_items"] = line_items

        # 3. Exceptions
        cursor.execute(
            """
            SELECT id, exception_type, severity, description, ai_summary, recommended_action, 
                   status, investigation_notes, resolution_notes, created_at 
            FROM exceptions 
            WHERE invoice_id = ? 
            ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END;
            """,
            (invoice_id,),
        )
        exceptions = [dict(r) for r in cursor.fetchall()]

        # 4. Verification History
        cursor.execute(
            """
            SELECT * FROM verification_history 
            WHERE invoice_id = ? 
            ORDER BY id DESC LIMIT 1;
            """,
            (invoice_id,),
        )
        verif_row = cursor.fetchone()
        verification_history = dict(verif_row) if verif_row else {}

        # 5. Approval & Payment History
        cursor.execute(
            """
            SELECT * FROM approvals_and_payments 
            WHERE invoice_id = ? 
            ORDER BY id DESC;
            """,
            (invoice_id,),
        )
        approval_history = [dict(r) for r in cursor.fetchall()]

        conn.close()

        return {
            "invoice": invoice_dict,
            "line_items": line_items,
            "exceptions": exceptions,
            "verification": verification_history,
            "approval_history": approval_history,
        }

    def process_approval_decision(
        self,
        invoice_id: int,
        action: str,  # "APPROVE", "REJECT", "REQUEST_CORRECTION"
        reviewer_name: str,
        comments: str = "",
        rejection_reason: str = "",
        correction_reason: str = "",
        payment_method: str = "ACH",  # ACH, WIRE, VIRTUAL_CARD
        high_value_confirmed: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes human approval decision with strict backend security guardrails:
        - Prevents duplicate approval of already PAID/APPROVED invoices
        - Blocks APPROVE if unresolved CRITICAL exceptions exist
        - Rejects APPROVE on high-value invoices without explicit confirmation
        - Enforces mandatory reason for REJECT and REQUEST_CORRECTION
        - Prevents rejected invoices from proceeding to payment
        - Updates SQLite invoices, approvals_and_payments, and audit_logs tables
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id, invoice_number, vendor_name, total_amount, status FROM invoices WHERE id = ?;", (invoice_id,))
        invoice = cursor.fetchone()
        if not invoice:
            conn.close()
            raise ValueError(f"Invoice with ID {invoice_id} not found.")

        current_status = invoice["status"]
        inv_num = invoice["invoice_number"]
        total_amt = float(invoice["total_amount"])

        # Security Rule 1: Prevent duplicate approval
        if current_status in ["APPROVED", "PAID"]:
            conn.close()
            raise ValueError(f"Invoice #{inv_num} is already in state '{current_status}'. Duplicate approval is prohibited.")

        # Security Rule 2: Cannot approve or disburse an already rejected invoice
        if current_status == "REJECTED":
            conn.close()
            raise ValueError(f"Invoice #{inv_num} has been permanently REJECTED. Cannot proceed to approval or disbursement.")

        now_str = datetime.now(timezone.utc).isoformat()
        simulated_payment_ref = None

        if action == "APPROVE":
            # Security Rule 3: Check for unresolved CRITICAL exceptions
            cursor.execute(
                """
                SELECT COUNT(*) FROM exceptions 
                WHERE invoice_id = ? AND status IN ('OPEN', 'UNDER_INVESTIGATION', 'REOPENED') AND severity = 'CRITICAL';
                """,
                (invoice_id,),
            )
            critical_count = cursor.fetchone()[0]
            if critical_count > 0:
                conn.close()
                raise ValueError(
                    f"APPROVAL BLOCKED: Invoice #{inv_num} has {critical_count} unresolved CRITICAL exception(s). "
                    "All critical anomalies must be resolved or voided in the Exception Center prior to approval."
                )

            # Security Rule 4: High-value confirmation requirement
            if total_amt >= HIGH_VALUE_THRESHOLD and not high_value_confirmed:
                conn.close()
                raise ValueError(
                    f"HIGH VALUE CONFIRMATION REQUIRED: Total billed amount of ${total_amt:,.2f} exceeds the high-value "
                    f"threshold (${HIGH_VALUE_THRESHOLD:,.2f}). Explicit dual-signoff confirmation is mandatory."
                )

            simulated_payment_ref = f"PAY-AUTH-{uuid.uuid4().hex[:6].upper()}"
            next_status = "APPROVED"
            payment_status = "PREPARED"
            db_decision = "APPROVED"

        elif action == "REJECT":
            if not rejection_reason.strip():
                conn.close()
                raise ValueError("REJECTION REASON REQUIRED: Rejection requires an explicit justification for the vendor record.")
            next_status = "REJECTED"
            payment_status = "CANCELLED"
            db_decision = "REJECTED"

        elif action == "REQUEST_CORRECTION":
            if not correction_reason.strip():
                conn.close()
                raise ValueError("CORRECTION REASON REQUIRED: Please specify what corrections or documentation the vendor must supply.")
            next_status = "CORRECTION_REQUESTED"
            payment_status = "ON_HOLD"
            db_decision = "CORRECTION_REQUESTED"

        else:
            conn.close()
            raise ValueError(f"Unknown approval action: '{action}'. Must be APPROVE, REJECT, or REQUEST_CORRECTION.")

        # Record in approvals_and_payments table
        cursor.execute(
            """
            INSERT INTO approvals_and_payments (
                invoice_id, decision, decision_by, comments, override_reason, 
                correction_reason, payment_method, simulated_payment_id, payment_status, payment_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                invoice_id,
                db_decision,
                reviewer_name,
                comments,
                rejection_reason if action == "REJECT" else None,
                correction_reason if action == "REQUEST_CORRECTION" else None,
                payment_method if action == "APPROVE" else None,
                simulated_payment_ref,
                payment_status,
                now_str if action == "APPROVE" else None,
            ),
        )

        # Update invoice status
        cursor.execute("UPDATE invoices SET status = ? WHERE id = ?;", (next_status, invoice_id))

        # Record immutable audit trail
        audit_level = "SUCCESS" if action == "APPROVE" else ("WARNING" if action == "REJECT" else "INFO")
        cursor.execute(
            """
            INSERT INTO audit_logs (
                invoice_id, agent_name, action, level, message, payload_json,
                actor, previous_status, new_status, category
            )
            VALUES (?, 'HumanSignatory', ?, ?, ?, ?, ?, ?, ?, 'APPROVAL');
            """,
            (
                invoice_id,
                f"WORKFLOW_{action}",
                audit_level,
                f"Reviewer '{reviewer_name}' executed '{action}' on invoice #{inv_num} (Total: ${total_amt:,.2f}). Transitioned status to '{next_status}'.",
                json.dumps({
                    "action": action,
                    "reviewer": reviewer_name,
                    "rejection_reason": rejection_reason,
                    "correction_reason": correction_reason,
                    "payment_ref": simulated_payment_ref,
                    "previous_status": current_status,
                    "next_status": next_status,
                }),
                reviewer_name,
                current_status,
                next_status,
            ),
        )

        conn.commit()
        conn.close()

        return {
            "invoice_id": invoice_id,
            "invoice_number": inv_num,
            "decision": db_decision,
            "reviewer": reviewer_name,
            "new_invoice_status": next_status,
            "payment_status": payment_status,
            "simulated_payment_ref": simulated_payment_ref,
            "timestamp": now_str,
        }
