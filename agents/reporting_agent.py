"""
Reporting Agent
Maintains audit logs, computes financial KPIs, and prepares compliance reports.
"""

import json
from typing import Optional, List, Dict
from database.db import get_db_connection


class ReportingAgent:
    def __init__(self, db_path: Optional[str] = None):
        self.agent_name = "Reporting Agent"
        self.db_path = db_path

    def record_audit(
        self,
        invoice_id: Optional[int],
        agent_name: str,
        action: str,
        message: str,
        level: str = "INFO",
        payload: Optional[dict] = None,
        actor: Optional[str] = None,
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        category: str = "SYSTEM",
    ):
        """Records an immutable audit event."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_logs (
                invoice_id, agent_name, action, level, message, 
                payload_json, actor, previous_status, new_status, category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                invoice_id,
                agent_name,
                action,
                level,
                message,
                json.dumps(payload or {}),
                actor or agent_name,
                previous_status,
                new_status,
                category,
            ),
        )
        conn.commit()
        conn.close()

    def get_kpi_summary(self) -> Dict:
        """Calculates current financial metrics across all invoices and payments."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Total counts
        cursor.execute("SELECT COUNT(*) FROM invoices;")
        total_invoices = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM invoices WHERE status = 'PENDING_APPROVAL';")
        pending_approval = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM exceptions WHERE status = 'OPEN';")
        open_exceptions = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(total_amount), 0.0) FROM invoices WHERE status = 'PAID';")
        paid_volume = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(total_amount), 0.0) FROM invoices WHERE status != 'REJECTED';")
        total_pipeline_volume = cursor.fetchone()[0]

        conn.close()
        return {
            "total_invoices": total_invoices,
            "pending_approval": pending_approval,
            "exceptions": open_exceptions,
            "paid_volume": paid_volume,
            "pipeline_volume": total_pipeline_volume,
        }

    def get_recent_audit_logs(self, limit: int = 15) -> List[Dict]:
        """Returns the latest audit events."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, invoice_id, agent_name, action, level, message, payload_json, timestamp 
            FROM audit_logs 
            ORDER BY id DESC 
            LIMIT ?;
            """,
            (limit,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
