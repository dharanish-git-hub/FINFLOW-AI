"""
Audit & Analytics Service (Task 09)
Provides centralized immutable audit logging, advanced audit querying,
deterministic financial analytics calculations, and CSV report export generators.

Strict Rules:
- Audit records are immutable; UI has no edit or delete access.
- Calculations derive from real SQLite records, never hardcoded.
- FAILED payment transactions are strictly excluded from settled payment totals.
- Prevents duplicate settlement count.
- Handles empty database states cleanly without crashing.
"""

import json
import csv
import io
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from database.db import get_db_connection


class AuditAnalyticsService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    # =========================================================================
    # 1. CENTRALIZED AUDIT LOGGING
    # =========================================================================

    def record_audit_event(
        self,
        action: str,
        message: str,
        invoice_id: Optional[int] = None,
        actor: str = "System",
        agent_name: str = "AuditService",
        level: str = "INFO",  # INFO, SUCCESS, WARNING, ERROR
        category: str = "SYSTEM",  # INTAKE, VERIFICATION, EXCEPTION, APPROVAL, PAYMENT, SYSTEM
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Records a comprehensive, immutable audit log event into SQLite.
        Returns the generated audit log record ID.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT INTO audit_logs (
                invoice_id, agent_name, action, level, message, 
                payload_json, actor, previous_status, new_status, category, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                invoice_id,
                agent_name,
                action,
                level,
                message,
                json.dumps(payload or {}),
                actor,
                previous_status,
                new_status,
                category,
                now_iso,
            ),
        )
        audit_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return audit_id

    def get_audit_logs(
        self,
        search_query: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[str] = None,
        invoice_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves audit records in reverse chronological order with flexible filters:
        - Search by invoice ID, action, actor, or message text.
        - Filter by event category, level (severity), and timestamp bounds.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT 
                al.id,
                al.invoice_id,
                inv.invoice_number,
                al.agent_name,
                al.action,
                al.level,
                al.message,
                al.actor,
                al.previous_status,
                al.new_status,
                al.category,
                al.payload_json,
                al.timestamp
            FROM audit_logs al
            LEFT JOIN invoices inv ON al.invoice_id = inv.id
            WHERE 1=1
        """
        params: List[Any] = []

        if invoice_id is not None:
            query += " AND al.invoice_id = ?"
            params.append(invoice_id)

        if category and category != "ALL":
            query += " AND al.category = ?"
            params.append(category)

        if level and level != "ALL":
            query += " AND al.level = ?"
            params.append(level)

        if start_date:
            query += " AND al.timestamp >= ?"
            params.append(start_date)

        if end_date:
            query += " AND al.timestamp <= ?"
            params.append(end_date)

        if search_query and search_query.strip():
            sq = f"%{search_query.strip()}%"
            query += """ AND (
                al.action LIKE ? OR 
                al.message LIKE ? OR 
                al.actor LIKE ? OR 
                CAST(al.invoice_id AS TEXT) LIKE ? OR 
                inv.invoice_number LIKE ?
            )"""
            params.extend([sq, sq, sq, sq, sq])

        query += " ORDER BY al.id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    # =========================================================================
    # 2. FINANCIAL ANALYTICS & KPIS
    # =========================================================================

    def get_financial_analytics(self) -> Dict[str, Any]:
        """
        Computes financial metrics, distributions, and time-series breakdowns.
        Guarantees:
        - Excludes FAILED transactions from settled payment totals.
        - Accurately computes pending approvals, failed payments, and open exceptions.
        - Safe handling of empty databases.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # 1. Total invoices processed & Total invoice value
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_invoices,
                COALESCE(SUM(total_amount), 0.0) as total_invoice_value
            FROM invoices;
            """
        )
        inv_summary = cursor.fetchone()
        total_invoices = inv_summary["total_invoices"] if inv_summary else 0
        total_invoice_value = float(inv_summary["total_invoice_value"]) if inv_summary else 0.0

        # 2. Total payments successfully executed & settled value (EXCLUDING FAILED)
        cursor.execute(
            """
            SELECT 
                COUNT(DISTINCT id) as total_executed_payments,
                COALESCE(SUM(amount), 0.0) as total_settled_value
            FROM payment_transactions
            WHERE status = 'EXECUTED';
            """
        )
        exec_summary = cursor.fetchone()
        total_executed_payments = exec_summary["total_executed_payments"] if exec_summary else 0
        total_settled_value = float(exec_summary["total_settled_value"]) if exec_summary else 0.0

        # 3. Pending approvals
        cursor.execute(
            """
            SELECT COUNT(*) as pending_count 
            FROM invoices 
            WHERE status IN ('PENDING_APPROVAL', 'RECEIVED', 'VERIFYING');
            """
        )
        pending_approvals = cursor.fetchone()["pending_count"]

        # 4. Failed simulated payments
        cursor.execute(
            """
            SELECT COUNT(*) as failed_count 
            FROM payment_transactions 
            WHERE status = 'FAILED';
            """
        )
        failed_payments = cursor.fetchone()["failed_count"]

        # 5. Open exceptions
        cursor.execute(
            """
            SELECT COUNT(*) as open_exceptions 
            FROM exceptions 
            WHERE status = 'OPEN';
            """
        )
        open_exceptions = cursor.fetchone()["open_exceptions"]

        # 6. Monthly invoice value
        cursor.execute(
            """
            SELECT 
                strftime('%Y-%m', COALESCE(invoice_date, created_at)) as month,
                COALESCE(SUM(total_amount), 0.0) as total_value,
                COUNT(*) as count
            FROM invoices
            WHERE month IS NOT NULL
            GROUP BY month
            ORDER BY month ASC;
            """
        )
        monthly_invoices = [dict(r) for r in cursor.fetchall()]

        # 7. Monthly settled payment value (EXECUTED only)
        cursor.execute(
            """
            SELECT 
                strftime('%Y-%m', COALESCE(settled_at, created_at)) as month,
                COALESCE(SUM(amount), 0.0) as settled_value,
                COUNT(*) as count
            FROM payment_transactions
            WHERE status = 'EXECUTED' AND month IS NOT NULL
            GROUP BY month
            ORDER BY month ASC;
            """
        )
        monthly_payments = [dict(r) for r in cursor.fetchall()]

        # 8. Invoice status distribution
        cursor.execute(
            """
            SELECT status, COUNT(*) as count, COALESCE(SUM(total_amount), 0.0) as total_amount
            FROM invoices
            GROUP BY status;
            """
        )
        status_dist = [dict(r) for r in cursor.fetchall()]

        # 9. Payment success vs failure
        cursor.execute(
            """
            SELECT status, COUNT(*) as count, COALESCE(SUM(amount), 0.0) as total_amount
            FROM payment_transactions
            GROUP BY status;
            """
        )
        payment_dist = [dict(r) for r in cursor.fetchall()]

        # 10. Exception severity distribution
        cursor.execute(
            """
            SELECT severity, COUNT(*) as count 
            FROM exceptions 
            GROUP BY severity;
            """
        )
        severity_dist = [dict(r) for r in cursor.fetchall()]

        # 11. Top vendors by invoice value
        cursor.execute(
            """
            SELECT 
                COALESCE(vendor_name, 'Unknown Vendor') as vendor_name,
                COALESCE(SUM(total_amount), 0.0) as total_value,
                COUNT(*) as invoice_count
            FROM invoices
            GROUP BY vendor_name
            ORDER BY total_value DESC
            LIMIT 10;
            """
        )
        top_vendors = [dict(r) for r in cursor.fetchall()]

        conn.close()

        return {
            "kpis": {
                "total_invoices": total_invoices,
                "total_invoice_value": total_invoice_value,
                "total_executed_payments": total_executed_payments,
                "total_settled_value": total_settled_value,
                "pending_approvals": pending_approvals,
                "failed_payments": failed_payments,
                "open_exceptions": open_exceptions,
            },
            "monthly_invoices": monthly_invoices,
            "monthly_payments": monthly_payments,
            "status_distribution": status_dist,
            "payment_distribution": payment_dist,
            "severity_distribution": severity_dist,
            "top_vendors": top_vendors,
        }

    # =========================================================================
    # 3. REPORT GENERATION (CSV EXPORTS)
    # =========================================================================

    def generate_invoice_summary_csv(self) -> str:
        """Generates CSV string of all invoices."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                id, invoice_number, vendor_name, po_number, 
                subtotal, tax_amount, total_amount, currency, 
                status, invoice_date, due_date, created_at
            FROM invoices
            ORDER BY id ASC;
            """
        )
        rows = cursor.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Invoice ID", "Invoice Number", "Vendor Name", "PO Number",
            "Subtotal", "Tax Amount", "Total Amount", "Currency",
            "Status", "Invoice Date", "Due Date", "Created At"
        ])
        for r in rows:
            writer.writerow([
                r["id"], r["invoice_number"], r["vendor_name"], r["po_number"],
                r["subtotal"], r["tax_amount"], r["total_amount"], r["currency"],
                r["status"], r["invoice_date"], r["due_date"], r["created_at"]
            ])
        return output.getvalue()

    def generate_payment_transactions_csv(self) -> str:
        """Generates CSV string of all simulated payment transactions."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                id, transaction_ref, invoice_id, vendor_name, 
                amount, currency, payment_rail, bank_account, 
                status, failure_reason, simulated_by, created_at, settled_at
            FROM payment_transactions
            ORDER BY id ASC;
            """
        )
        rows = cursor.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Transaction ID", "Transaction Ref", "Invoice ID", "Vendor Name",
            "Amount", "Currency", "Payment Rail", "Bank Account",
            "Status", "Failure Reason", "Simulated By", "Created At", "Settled At"
        ])
        for r in rows:
            writer.writerow([
                r["id"], r["transaction_ref"], r["invoice_id"], r["vendor_name"],
                r["amount"], r["currency"], r["payment_rail"], r["bank_account"],
                r["status"], r["failure_reason"], r["simulated_by"], r["created_at"], r["settled_at"]
            ])
        return output.getvalue()

    def generate_exceptions_csv(self) -> str:
        """Generates CSV string of all detected exceptions and investigation notes."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                id, invoice_id, exception_type, severity, 
                description, status, resolution_notes, 
                created_at, resolved_at
            FROM exceptions
            ORDER BY id ASC;
            """
        )
        rows = cursor.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Exception ID", "Invoice ID", "Type", "Severity",
            "Description", "Status", "Resolution Notes",
            "Created At", "Resolved At"
        ])
        for r in rows:
            writer.writerow([
                r["id"], r["invoice_id"], r["exception_type"], r["severity"],
                r["description"], r["status"], r["resolution_notes"],
                r["created_at"], r["resolved_at"]
            ])
        return output.getvalue()

    def generate_audit_logs_csv(
        self,
        category: Optional[str] = None,
        level: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> str:
        """Generates CSV string of audit log records preserving full details."""
        logs = self.get_audit_logs(
            search_query=search_query,
            category=category,
            level=level,
            limit=5000,
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Audit ID", "Timestamp", "Category", "Level", "Action",
            "Actor", "Agent Name", "Invoice ID", "Invoice Number",
            "Previous Status", "New Status", "Message", "Payload JSON"
        ])
        for r in logs:
            writer.writerow([
                r["id"], r["timestamp"], r["category"], r["level"], r["action"],
                r["actor"], r["agent_name"], r["invoice_id"], r["invoice_number"],
                r["previous_status"], r["new_status"], r["message"], r["payload_json"]
            ])
        return output.getvalue()
