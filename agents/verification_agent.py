"""
Verification Agent
Verifies vendor authenticity in SQLite and performs 2-way/3-way PO line item matching.
"""

from typing import Optional
from database.db import get_db_connection
from agents.base_agent import InvoiceExtractionResult, VerificationResult
from services.verification_service import VerificationService


class VerificationAgent:
    def __init__(self, db_path: Optional[str] = None):
        self.agent_name = "Verification Agent"
        self.db_path = db_path
        self.service = VerificationService(db_path=db_path)

    def verify(self, extraction: InvoiceExtractionResult) -> VerificationResult:
        res = self.service.verify_invoice(extraction)
        vendor_verified = res["vendor_status"] == "VERIFIED"
        po_matched = res["po_status"] == "MATCHED"
        amount_mismatch = res["amount_status"] != "MATCHED"

        reasons = res["detected_exceptions"] if res["detected_exceptions"] else [res["explanation"]]

        return VerificationResult(
            vendor_verified=vendor_verified,
            vendor_id=res.get("matched_vendor_id"),
            vendor_status=res["vendor_status"],
            po_matched=po_matched,
            po_number=extraction.po_number,
            po_total=res.get("po_total"),
            amount_mismatch=amount_mismatch,
            discrepancy_amount=0.0,
            line_item_matches=res.get("line_matches", []),
            reasons=reasons,
        )
