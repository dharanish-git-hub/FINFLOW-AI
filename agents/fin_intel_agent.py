"""
Financial Intelligence Agent
Detects duplicate invoices, arithmetic errors, sales tax discrepancies, and suspicious fraud patterns.
"""

from typing import Optional
from database.db import get_db_connection
from agents.base_agent import InvoiceExtractionResult, FinancialIntelligenceResult, VerificationResult


class FinancialIntelligenceAgent:
    def __init__(self, db_path: Optional[str] = None):
        self.agent_name = "Financial Intelligence Agent"
        self.db_path = db_path

    def analyze(
        self,
        extraction: InvoiceExtractionResult,
        file_hash: str,
        verification: VerificationResult,
        current_invoice_id: Optional[int] = None
    ) -> FinancialIntelligenceResult:
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        flags = []
        risk_score = 0.0
        is_duplicate = False
        duplicate_id = None

        # 1. Duplicate Detection by File SHA-256 or Invoice# + Vendor (excluding current invoice if already inserted)
        cursor.execute(
            """
            SELECT id, invoice_number, vendor_name, total_amount, file_hash 
            FROM invoices 
            WHERE (file_hash = ? OR (invoice_number = ? AND vendor_name = ?))
              AND (? IS NULL OR id != ?);
            """,
            (file_hash, extraction.invoice_number, extraction.vendor_name, current_invoice_id, current_invoice_id),
        )
        dup_row = cursor.fetchone()
        if dup_row:
            is_duplicate = True
            duplicate_id = dup_row["id"]
            flags.append(f"DUPLICATE DETECTED: Matches previously ingested invoice #{dup_row['invoice_number']} (DB ID: {duplicate_id}).")
            risk_score += 0.85

        # 2. Arithmetic & Tax Discrepancy Checks
        sum_of_lines = sum(item.total_price for item in extraction.line_items)
        math_error = False

        if extraction.line_items and abs(sum_of_lines - extraction.subtotal) > 0.05:
            math_error = True
            diff = abs(sum_of_lines - extraction.subtotal)
            flags.append(f"ARITHMETIC ERROR: Line items sum to ${sum_of_lines:,.2f}, but subtotal states ${extraction.subtotal:,.2f} (diff: ${diff:,.2f}).")
            risk_score += 0.40

        # Subtotal + Tax vs Total
        expected_total = extraction.subtotal + extraction.tax_amount
        if abs(expected_total - extraction.total_amount) > 0.05:
            math_error = True
            diff = abs(expected_total - extraction.total_amount)
            flags.append(f"SUM MISMATCH: Subtotal (${extraction.subtotal:,.2f}) + Tax (${extraction.tax_amount:,.2f}) = ${expected_total:,.2f}, which does not equal stated Total (${extraction.total_amount:,.2f}).")
            risk_score += 0.50

        # Standard Tax Rate Validation (assumed ~8% standard benchmark)
        tax_error = False
        standard_tax_estimate = round(extraction.subtotal * 0.08, 2)
        tax_discrepancy = abs(extraction.tax_amount - standard_tax_estimate)
        if extraction.tax_amount > 0 and tax_discrepancy > (extraction.subtotal * 0.03):
            tax_error = True
            flags.append(f"TAX ANOMALY: Stated tax of ${extraction.tax_amount:,.2f} deviates from expected 8% benchmark (${standard_tax_estimate:,.2f}).")
            risk_score += 0.25

        # 3. Vendor / Risk Correlation
        if not verification.vendor_verified:
            flags.append("UNVERIFIED ENTITY: Invoice originated from an unconfirmed vendor entity.")
            risk_score += 0.60

        if verification.vendor_status == "BLOCKED":
            flags.append("SECURITY ALERT: Blacklisted entity attempted submission.")
            risk_score = 1.0

        if verification.amount_mismatch:
            flags.append(f"AMOUNT VARIANCE: Exceeds authorized purchase order budget by ${verification.discrepancy_amount:,.2f}.")
            risk_score += 0.35

        # 4. Immediate Due Date Anomaly
        if extraction.invoice_date and extraction.due_date and extraction.invoice_date == extraction.due_date:
            flags.append("POLICY EXCEPTION: Immediate due date without standard payment term (Net 30/60).")
            risk_score += 0.15

        conn.close()

        normalized_risk = min(1.0, round(risk_score, 2))
        is_suspicious = normalized_risk >= 0.40 or len(flags) > 0

        return FinancialIntelligenceResult(
            is_duplicate=is_duplicate,
            duplicate_invoice_id=duplicate_id,
            tax_error=tax_error,
            calculated_tax=standard_tax_estimate,
            tax_discrepancy=tax_discrepancy,
            math_error=math_error,
            is_suspicious=is_suspicious,
            anomaly_flags=flags,
            risk_score=normalized_risk,
        )
