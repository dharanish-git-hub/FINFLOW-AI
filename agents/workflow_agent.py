"""
Workflow Agent
Coordinates state transitions, evaluates approval criteria, records exceptions,
and routes invoices to the appropriate state.
"""

import json
from typing import Optional, List, Tuple
from database.db import get_db_connection
from agents.base_agent import (
    InvoiceExtractionResult,
    VerificationResult,
    FinancialIntelligenceResult,
)
from services.exception_intelligence_service import (
    ExceptionIntelligenceService,
    classify_exception_severity,
)


class WorkflowAgent:
    def __init__(self, db_path: Optional[str] = None):
        self.agent_name = "Workflow Agent"
        self.db_path = db_path
        self.exception_service = ExceptionIntelligenceService(db_path=db_path)

    def evaluate_and_route(
        self,
        invoice_id: int,
        extraction: InvoiceExtractionResult,
        verification: VerificationResult,
        fin_intel: FinancialIntelligenceResult,
    ) -> Tuple[str, List[dict]]:
        """
        Determines the next workflow state:
        Returns (next_status, list_of_exceptions_created).
        Next status is either 'PENDING_APPROVAL' (clean) or 'EXCEPTION' (issues found).
        Classifies exceptions into LOW, MEDIUM, HIGH, CRITICAL with AI explanation & recommended actions.
        """
        detected_exceptions = []

        # 1. Check for Duplicate Exception
        if fin_intel.is_duplicate:
            detected_exceptions.append({
                "type": "DUPLICATE",
                "severity": "CRITICAL",
                "description": f"Duplicate invoice detected matching record #{fin_intel.duplicate_invoice_id}.",
                "details": {"duplicate_id": fin_intel.duplicate_invoice_id},
            })

        # 2. Check for Vendor Exception
        if not verification.vendor_verified:
            sev = "CRITICAL" if verification.vendor_status == "BLOCKED" else "HIGH"
            detected_exceptions.append({
                "type": "VENDOR_UNVERIFIED",
                "severity": sev,
                "description": f"Vendor '{extraction.vendor_name}' verification failed (Status: {verification.vendor_status}).",
                "details": {"vendor_status": verification.vendor_status},
            })

        # 3. Check for Amount / PO Mismatch Exception
        if verification.amount_mismatch:
            sev = classify_exception_severity("AMOUNT_MISMATCH", {
                "discrepancy": verification.discrepancy_amount,
                "po_total": verification.po_total,
            })
            detected_exceptions.append({
                "type": "AMOUNT_MISMATCH",
                "severity": sev,
                "description": f"Invoice amount variance of ${verification.discrepancy_amount:,.2f} against PO {verification.po_number}.",
                "details": {
                    "po_total": verification.po_total,
                    "inv_total": extraction.total_amount,
                    "discrepancy": verification.discrepancy_amount,
                },
            })

        # 4. Check for Math / Tax Errors
        if fin_intel.math_error or fin_intel.tax_error:
            e_type = "TAX_ERROR" if fin_intel.tax_error else "MATH_ERROR"
            sev = classify_exception_severity(e_type, {"tax_discrepancy": fin_intel.tax_discrepancy})
            detected_exceptions.append({
                "type": e_type,
                "severity": sev,
                "description": "Calculated subtotal, tax rate, or total price arithmetic discrepancy.",
                "details": {
                    "flags": fin_intel.anomaly_flags,
                    "tax_discrepancy": fin_intel.tax_discrepancy,
                },
            })

        # 5. Enrich and persist into SQLite using ExceptionIntelligenceService
        inv_meta = {
            "invoice_number": extraction.invoice_number,
            "vendor_name": extraction.vendor_name,
            "total_amount": extraction.total_amount,
        }
        created_exceptions = self.exception_service.record_and_enrich_exceptions(
            invoice_id=invoice_id,
            invoice_metadata=inv_meta,
            detected_exceptions=detected_exceptions,
            mock_mode=True,
        )

        # Determine target state
        if created_exceptions:
            next_status = "EXCEPTION"
        else:
            next_status = "PENDING_APPROVAL"

        # Update invoice status in DB
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE invoices SET status = ? WHERE id = ?;",
            (next_status, invoice_id),
        )
        conn.commit()
        conn.close()

        return next_status, created_exceptions
