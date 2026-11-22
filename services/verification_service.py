"""
Verification Service for FINFLOW AI.
Provides deterministic, multi-point verification across:
1. Vendor authenticity & normalized name matching
2. Purchase Order line-item & vendor consistency matching
3. Financial validation (subtotal, tax, overbilling, math discrepancy with tolerances)
4. Overall verification status (VERIFIED, NEEDS_REVIEW, BLOCKED)
5. Audit persistence into SQLite verification_history
"""

import re
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
from database.db import get_db_connection
from agents.base_agent import InvoiceExtractionResult


def normalize_vendor_name(name: str) -> str:
    """
    Normalizes vendor name by removing common legal suffixes (Inc, LLC, Corp, Ltd, Co),
    punctuation, and normalizing whitespace and case.
    """
    if not name:
        return ""
    text = name.lower().strip()
    # Remove punctuation
    text = re.sub(r"[^\w\s]", "", text)
    # Remove common business entity suffixes
    suffixes = [r"\binc\b", r"\bllc\b", r"\bcorp\b", r"\bcorporation\b", r"\bltd\b", r"\bcompany\b", r"\bco\b", r"\bservices\b"]
    for s in suffixes:
        text = re.sub(s, "", text)
    # Normalize multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


class VerificationService:
    def __init__(
        self,
        db_path: Optional[str] = None,
        amount_tolerance_pct: float = 0.01,  # 1% variance threshold
        amount_tolerance_abs: float = 0.50,  # $0.50 absolute rounding tolerance
    ):
        self.db_path = db_path
        self.amount_tolerance_pct = amount_tolerance_pct
        self.amount_tolerance_abs = amount_tolerance_abs

    def verify_invoice(
        self,
        invoice_data: Union[InvoiceExtractionResult, Dict[str, Any]],
        invoice_id: Optional[int] = None,
        file_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes deterministic multi-point verification.
        Returns a structured dictionary with:
        - verification_status: "VERIFIED" | "NEEDS_REVIEW" | "BLOCKED"
        - vendor_status: "VERIFIED" | "UNCERTAIN" | "UNKNOWN" | "BLOCKED" | "INACTIVE"
        - po_status: "MATCHED" | "MISMATCH" | "MISSING" | "INVALID"
        - amount_status: "MATCHED" | "OVERBILLED" | "MATH_ERROR" | "DISCREPANCY"
        - detected_exceptions: List of exception strings
        - explanation: Clear human explanation
        - verification_timestamp: ISO timestamp
        - details: Detailed breakdown dict
        """
        # Convert Pydantic model to dict if needed
        if isinstance(invoice_data, InvoiceExtractionResult):
            inv = invoice_data.model_dump()
            inv_items = [item.model_dump() for item in invoice_data.line_items]
        else:
            inv = dict(invoice_data)
            inv_items = inv.get("line_items", [])

        inv_num = (inv.get("invoice_number") or "").strip()
        vendor_name = (inv.get("vendor_name") or "").strip()
        vendor_tax_id = (inv.get("vendor_tax_id") or "").strip()
        po_num = (inv.get("purchase_order_number") or inv.get("po_number") or "").strip()
        subtotal = float(inv.get("subtotal") or 0.0)
        tax_amount = float(inv.get("tax_amount") or 0.0)
        total_amount = float(inv.get("total_amount") or 0.0)

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        detected_exceptions: List[str] = []
        is_blocked = False
        needs_review = False

        # ---------------------------------------------------------
        # 1. DUPLICATE INVOICE CHECK
        # ---------------------------------------------------------
        if inv_num and vendor_name:
            cursor.execute(
                """
                SELECT id, invoice_number, vendor_name, total_amount, created_at 
                FROM invoices 
                WHERE (invoice_number = ? AND LOWER(vendor_name) = ?)
                  AND (? IS NULL OR id != ?);
                """,
                (inv_num, vendor_name.lower(), invoice_id, invoice_id),
            )
            dup = cursor.fetchone()
            if dup:
                is_blocked = True
                detected_exceptions.append(
                    f"DUPLICATE_INVOICE: Invoice #{inv_num} for vendor '{vendor_name}' already exists in ledger (ID #{dup['id']}, ${dup['total_amount']:,.2f})."
                )

        # ---------------------------------------------------------
        # 2. VENDOR VERIFICATION & MATCHING
        # ---------------------------------------------------------
        vendor_status = "UNKNOWN"
        matched_vendor_id = None
        matched_vendor_row = None

        cursor.execute("SELECT vendor_id, name, tax_id, status, risk_score FROM vendors;")
        all_vendors = cursor.fetchall()

        norm_extracted_vendor = normalize_vendor_name(vendor_name)

        # Step 2a: Exact or normalized match
        for v in all_vendors:
            v_name = v["name"]
            # Tax ID match
            if vendor_tax_id and v["tax_id"] and vendor_tax_id == v["tax_id"]:
                matched_vendor_row = v
                break
            # Exact case-insensitive match
            if v_name.lower() == vendor_name.lower():
                matched_vendor_row = v
                break
            # Normalized match
            if norm_extracted_vendor and norm_extracted_vendor == normalize_vendor_name(v_name):
                matched_vendor_row = v
                break

        # Step 2b: Partial / substring match (uncertain)
        uncertain_match = None
        if not matched_vendor_row and norm_extracted_vendor:
            for v in all_vendors:
                nv = normalize_vendor_name(v["name"])
                if (norm_extracted_vendor in nv or nv in norm_extracted_vendor) and len(norm_extracted_vendor) >= 4:
                    uncertain_match = v
                    break

        if matched_vendor_row:
            matched_vendor_id = matched_vendor_row["vendor_id"]
            db_status = (matched_vendor_row["status"] or "ACTIVE").upper()

            if db_status == "BLOCKED":
                vendor_status = "BLOCKED"
                is_blocked = True
                detected_exceptions.append(
                    f"BLOCKED_VENDOR: Vendor '{matched_vendor_row['name']}' ({matched_vendor_id}) is on the blocked/blacklisted entity registry."
                )
            elif db_status in ["INACTIVE", "SUSPENDED"]:
                vendor_status = "INACTIVE"
                is_blocked = True
                detected_exceptions.append(
                    f"INACTIVE_VENDOR: Vendor '{matched_vendor_row['name']}' ({matched_vendor_id}) is currently marked as '{db_status}'."
                )
            else:
                vendor_status = "VERIFIED"
        elif uncertain_match:
            vendor_status = "UNCERTAIN"
            matched_vendor_id = uncertain_match["vendor_id"]
            needs_review = True
            detected_exceptions.append(
                f"UNCERTAIN_VENDOR_MATCH: Extracted vendor '{vendor_name}' partially matches registered vendor '{uncertain_match['name']}' ({matched_vendor_id}). Requires manual verification."
            )
        else:
            vendor_status = "UNKNOWN"
            needs_review = True
            detected_exceptions.append(
                f"UNKNOWN_VENDOR: Vendor '{vendor_name}' could not be identified in the approved vendor registry."
            )

        # ---------------------------------------------------------
        # 3. PURCHASE ORDER MATCHING
        # ---------------------------------------------------------
        po_status = "MISSING"
        po_total = None
        po_vendor_id = None
        po_line_matches: List[Dict[str, Any]] = []

        if not po_num:
            po_status = "MISSING"
            needs_review = True
            detected_exceptions.append("MISSING_PO: Invoice does not reference a Purchase Order (Non-PO expenditure).")
        else:
            cursor.execute(
                """
                SELECT po_number, vendor_id, total_amount, tax_amount, status 
                FROM purchase_orders 
                WHERE po_number = ?;
                """,
                (po_num,),
            )
            po_row = cursor.fetchone()

            if not po_row:
                po_status = "INVALID"
                is_blocked = True
                detected_exceptions.append(f"INVALID_PO: Referenced Purchase Order '{po_num}' does not exist in the ERP database.")
            else:
                po_vendor_id = po_row["vendor_id"]
                po_total = float(po_row["total_amount"]) + float(po_row["tax_amount"])

                # Check Vendor Consistency between PO and Invoice
                if matched_vendor_id and po_vendor_id != matched_vendor_id:
                    po_status = "MISMATCH"
                    is_blocked = True
                    detected_exceptions.append(
                        f"PO_VENDOR_MISMATCH: Purchase Order {po_num} was issued to vendor {po_vendor_id}, but invoice belongs to {matched_vendor_id} ('{vendor_name}')."
                    )
                else:
                    po_status = "MATCHED"

                # PO Line Item Matching
                cursor.execute(
                    "SELECT item_description, quantity, unit_price, total_price FROM po_items WHERE po_number = ?;",
                    (po_num,),
                )
                po_items = [dict(r) for r in cursor.fetchall()]

                for inv_item in inv_items:
                    desc = (inv_item.get("description") or "").strip()
                    qty = float(inv_item.get("quantity") or 1.0)
                    price = float(inv_item.get("unit_price") or 0.0)
                    amt = float(inv_item.get("amount") or inv_item.get("total_price") or (qty * price))

                    # Find best match in PO items
                    best_match = None
                    for pi in po_items:
                        pi_desc = pi["item_description"].lower()
                        # Word overlap matching
                        words = [w.lower() for w in re.split(r"\W+", desc) if len(w) > 3]
                        if any(w in pi_desc for w in words):
                            best_match = pi
                            break

                    line_match_info = {
                        "invoice_item": desc,
                        "invoice_qty": qty,
                        "invoice_unit_price": price,
                        "invoice_amount": amt,
                        "po_item": best_match["item_description"] if best_match else None,
                        "po_qty": best_match["quantity"] if best_match else None,
                        "po_unit_price": best_match["unit_price"] if best_match else None,
                        "po_amount": best_match["total_price"] if best_match else None,
                        "matched": best_match is not None,
                        "qty_mismatch": False,
                        "price_mismatch": False,
                    }

                    if best_match:
                        # Quantity discrepancy check
                        if abs(qty - float(best_match["quantity"])) > 0.01:
                            line_match_info["qty_mismatch"] = True
                            needs_review = True
                            detected_exceptions.append(
                                f"QUANTITY_MISMATCH: Item '{desc}' billed qty ({qty}) differs from PO authorized qty ({best_match['quantity']})."
                            )
                        # Unit price discrepancy check
                        if abs(price - float(best_match["unit_price"])) > 0.05:
                            line_match_info["price_mismatch"] = True
                            needs_review = True
                            detected_exceptions.append(
                                f"PRICE_MISMATCH: Item '{desc}' unit price (${price:,.2f}) differs from PO authorized price (${best_match['unit_price']:,.2f})."
                            )
                    else:
                        line_match_info["unmatched"] = True
                        if len(po_items) > 0:
                            needs_review = True
                            detected_exceptions.append(f"UNLISTED_ITEM: Item '{desc}' does not match any authorized line item on PO {po_num}.")

                    po_line_matches.append(line_match_info)

        # ---------------------------------------------------------
        # 4. FINANCIAL VALIDATION (Calculations & Overbilling)
        # ---------------------------------------------------------
        amount_status = "MATCHED"

        # Math Check: Subtotal + Tax == Total
        expected_total = round(subtotal + tax_amount, 2)
        diff_math = abs(expected_total - total_amount)
        if diff_math > (self.amount_tolerance_abs + 0.05):
            amount_status = "MATH_ERROR"
            needs_review = True
            detected_exceptions.append(
                f"ARITHMETIC_ERROR: Subtotal (${subtotal:,.2f}) + Tax (${tax_amount:,.2f}) = ${expected_total:,.2f}, differing from Stated Total (${total_amount:,.2f}) by ${diff_math:,.2f}."
            )

        # Line items sum check
        if inv_items:
            items_sum = sum(
                float(i.get("amount") or i.get("total_price") or (float(i.get("quantity", 1)) * float(i.get("unit_price", 0))))
                for i in inv_items
            )
            if subtotal > 0 and abs(items_sum - subtotal) > (self.amount_tolerance_abs + 0.05):
                amount_status = "MATH_ERROR"
                needs_review = True
                detected_exceptions.append(
                    f"LINE_ITEMS_SUM_MISMATCH: Sum of line items (${items_sum:,.2f}) does not match subtotal (${subtotal:,.2f})."
                )

        # Overbilling against PO Total
        if po_total is not None:
            variance = total_amount - po_total
            allowed_threshold = max(po_total * self.amount_tolerance_pct, self.amount_tolerance_abs)
            if variance > allowed_threshold:
                amount_status = "OVERBILLED"
                needs_review = True
                detected_exceptions.append(
                    f"OVERBILLING_DETECTED: Total billed (${total_amount:,.2f}) exceeds PO budget (${po_total:,.2f}) by ${variance:+,.2f} (exceeds allowed tolerance of ${allowed_threshold:,.2f})."
                )
            elif variance < -allowed_threshold:
                # Underbilled (partial billing)
                detected_exceptions.append(
                    f"PARTIAL_BILLING: Invoice total (${total_amount:,.2f}) is lower than PO total (${po_total:,.2f}) by ${abs(variance):,.2f}."
                )

        # ---------------------------------------------------------
        # 5. OVERALL VERIFICATION STATUS SYNTHESIS
        # ---------------------------------------------------------
        if is_blocked:
            overall_status = "BLOCKED"
        elif needs_review or len(detected_exceptions) > 0:
            overall_status = "NEEDS_REVIEW"
        else:
            overall_status = "VERIFIED"

        # Construct concise human explanation
        if overall_status == "VERIFIED":
            explanation = f"All checks passed cleanly: Vendor '{vendor_name}' ({matched_vendor_id}) verified, matched PO {po_num}, line items and financial totals match exactly."
        elif overall_status == "BLOCKED":
            explanation = f"BLOCKED: Critical compliance or policy violations detected ({len(detected_exceptions)} issue(s)). Cannot proceed without formal investigation."
        else:
            explanation = f"NEEDS REVIEW: {len(detected_exceptions)} discrepancy or uncertainty detected. Routing to Accounts Payable specialist for review."

        timestamp = datetime.now(timezone.utc).isoformat()

        # ---------------------------------------------------------
        # 6. PERSIST TO SQLite VERIFICATION_HISTORY
        # ---------------------------------------------------------
        details_dict = {
            "vendor_id": matched_vendor_id,
            "vendor_name": vendor_name,
            "po_number": po_num,
            "po_total": po_total,
            "invoice_total": total_amount,
            "line_matches": po_line_matches,
            "tolerance_pct": self.amount_tolerance_pct,
        }

        cursor.execute(
            """
            INSERT INTO verification_history (
                invoice_id, invoice_number, verification_status, vendor_status,
                po_status, amount_status, detected_exceptions, explanation,
                details_json, verification_timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                invoice_id,
                inv_num,
                overall_status,
                vendor_status,
                po_status,
                amount_status,
                json.dumps(detected_exceptions),
                explanation,
                json.dumps(details_dict),
                timestamp,
            ),
        )
        conn.commit()
        conn.close()

        return {
            "verification_status": overall_status,
            "vendor_status": vendor_status,
            "po_status": po_status,
            "amount_status": amount_status,
            "detected_exceptions": detected_exceptions,
            "explanation": explanation,
            "verification_timestamp": timestamp,
            "matched_vendor_id": matched_vendor_id,
            "po_total": po_total,
            "line_matches": po_line_matches,
        }

    def get_verification_history(self, invoice_id: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves historical verification records from SQLite."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        if invoice_id is not None:
            cursor.execute(
                """
                SELECT id, invoice_id, invoice_number, verification_status, vendor_status,
                       po_status, amount_status, detected_exceptions, explanation,
                       details_json, verification_timestamp
                FROM verification_history
                WHERE invoice_id = ?
                ORDER BY id DESC LIMIT ?;
                """,
                (invoice_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT id, invoice_id, invoice_number, verification_status, vendor_status,
                       po_status, amount_status, detected_exceptions, explanation,
                       details_json, verification_timestamp
                FROM verification_history
                ORDER BY id DESC LIMIT ?;
                """,
                (limit,),
            )

        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # Parse JSON fields
        for r in rows:
            try:
                r["detected_exceptions"] = json.loads(r["detected_exceptions"])
            except Exception:
                pass
            try:
                r["details_json"] = json.loads(r["details_json"])
            except Exception:
                pass

        return rows
