"""
Tests for VerificationService across all Task 04 synthetic scenarios:
- Valid vendor and matching PO (VERIFIED)
- Unknown vendor (NEEDS_REVIEW)
- Inactive / Blocked vendor (BLOCKED)
- Missing PO (NEEDS_REVIEW)
- Incorrect PO vendor mismatch (BLOCKED)
- Invoice amount exceeding PO amount (NEEDS_REVIEW - OVERBILLED)
- Quantity mismatch (NEEDS_REVIEW)
- Duplicate invoice number (BLOCKED)
"""

import os
import tempfile
import unittest
from database.seed_data import seed_database
from database.db import get_db_connection
from services.verification_service import VerificationService, normalize_vendor_name


class TestVerificationService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_verification.db")
        seed_database(cls.db_path)
        cls.service = VerificationService(db_path=cls.db_path)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_vendor_name_normalization(self):
        """Test normalization handles case, punctuation and suffixes."""
        self.assertEqual(normalize_vendor_name("Apex Cloud Services Inc."), "apex cloud")
        self.assertEqual(normalize_vendor_name("GLOBAL LOGISTICS & FREIGHT LLC"), "global logistics freight")
        self.assertEqual(normalize_vendor_name("Modern Office Interiors Co."), "modern office interiors")

    def test_scenario_1_valid_vendor_and_matching_po(self):
        """Scenario 1: Valid registered vendor and perfectly matching PO -> VERIFIED."""
        inv = {
            "invoice_number": "INV-TEST-V1",
            "vendor_name": "Apex Cloud Services Inc.",
            "vendor_tax_id": "US-EIN-94-3829101",
            "purchase_order_number": "PO-2026-001",
            "subtotal": 12500.00,
            "tax_amount": 1000.00,
            "total_amount": 13500.00,
            "line_items": [
                {"description": "Cloud Compute Enterprise Tier (Monthly)", "quantity": 1, "unit_price": 8000.00, "amount": 8000.00},
                {"description": "Dedicated High-Speed Interconnect", "quantity": 1, "unit_price": 3500.00, "amount": 3500.00},
                {"description": "Priority Support SLA", "quantity": 1, "unit_price": 1000.00, "amount": 1000.00},
            ],
        }
        res = self.service.verify_invoice(inv)
        self.assertEqual(res["verification_status"], "VERIFIED")
        self.assertEqual(res["vendor_status"], "VERIFIED")
        self.assertEqual(res["po_status"], "MATCHED")
        self.assertEqual(res["amount_status"], "MATCHED")
        self.assertEqual(len(res["detected_exceptions"]), 0)

    def test_scenario_2_unknown_vendor(self):
        """Scenario 2: Unregistered vendor not in database -> NEEDS_REVIEW."""
        inv = {
            "invoice_number": "INV-TEST-UNKNOWN",
            "vendor_name": "Unregistered Shadow Technologies",
            "purchase_order_number": "PO-2026-001",
            "subtotal": 5000.00,
            "tax_amount": 400.00,
            "total_amount": 5400.00,
            "line_items": [{"description": "Tech support", "quantity": 1, "unit_price": 5000.00, "amount": 5000.00}],
        }
        res = self.service.verify_invoice(inv)
        self.assertEqual(res["verification_status"], "NEEDS_REVIEW")
        self.assertEqual(res["vendor_status"], "UNKNOWN")
        self.assertTrue(any("UNKNOWN_VENDOR" in e for e in res["detected_exceptions"]))

    def test_scenario_3_inactive_or_blocked_vendor(self):
        """Scenario 3: Blacklisted / Blocked vendor -> BLOCKED."""
        inv = {
            "invoice_number": "INV-TEST-BLOCKED",
            "vendor_name": "Blacklisted Shell Corp",
            "vendor_tax_id": "US-EIN-99-9999999",
            "purchase_order_number": "",
            "subtotal": 10000.00,
            "tax_amount": 0.00,
            "total_amount": 10000.00,
            "line_items": [],
        }
        res = self.service.verify_invoice(inv)
        self.assertEqual(res["verification_status"], "BLOCKED")
        self.assertEqual(res["vendor_status"], "BLOCKED")
        self.assertTrue(any("BLOCKED_VENDOR" in e for e in res["detected_exceptions"]))

    def test_scenario_4_missing_po(self):
        """Scenario 4: Valid vendor but missing Purchase Order -> NEEDS_REVIEW."""
        inv = {
            "invoice_number": "INV-TEST-NOPO",
            "vendor_name": "Apex Cloud Services Inc.",
            "purchase_order_number": "",
            "subtotal": 2000.00,
            "tax_amount": 160.00,
            "total_amount": 2160.00,
            "line_items": [],
        }
        res = self.service.verify_invoice(inv)
        self.assertEqual(res["verification_status"], "NEEDS_REVIEW")
        self.assertEqual(res["po_status"], "MISSING")
        self.assertTrue(any("MISSING_PO" in e for e in res["detected_exceptions"]))

    def test_scenario_5_incorrect_po_vendor(self):
        """Scenario 5: PO exists but was issued to a different vendor -> BLOCKED."""
        # PO-2026-001 belongs to VND-001 (Apex Cloud), but invoice claims VND-002 (Global Logistics)
        inv = {
            "invoice_number": "INV-TEST-PO-MISMATCH",
            "vendor_name": "Global Logistics & Freight LLC",
            "purchase_order_number": "PO-2026-001",
            "subtotal": 12500.00,
            "tax_amount": 1000.00,
            "total_amount": 13500.00,
            "line_items": [],
        }
        res = self.service.verify_invoice(inv)
        self.assertEqual(res["verification_status"], "BLOCKED")
        self.assertEqual(res["po_status"], "MISMATCH")
        self.assertTrue(any("PO_VENDOR_MISMATCH" in e for e in res["detected_exceptions"]))

    def test_scenario_6_invoice_amount_exceeding_po(self):
        """Scenario 6: Amount exceeds PO total budget -> NEEDS_REVIEW (OVERBILLED)."""
        # PO-2026-002 budget is $4,800 + $384 = $5,184. Here billed is $7,000.
        inv = {
            "invoice_number": "INV-TEST-OVERBILL",
            "vendor_name": "Global Logistics & Freight LLC",
            "purchase_order_number": "PO-2026-002",
            "subtotal": 6500.00,
            "tax_amount": 500.00,
            "total_amount": 7000.00,
            "line_items": [{"description": "Interstate Freight - 4 Containers", "quantity": 4, "unit_price": 1625.00, "amount": 6500.00}],
        }
        res = self.service.verify_invoice(inv)
        self.assertEqual(res["verification_status"], "NEEDS_REVIEW")
        self.assertEqual(res["amount_status"], "OVERBILLED")
        self.assertTrue(any("OVERBILLING_DETECTED" in e for e in res["detected_exceptions"]))

    def test_scenario_7_quantity_mismatch(self):
        """Scenario 7: Line item quantity differs from PO line item -> NEEDS_REVIEW."""
        # PO-2026-002 specifies quantity=4
        inv = {
            "invoice_number": "INV-TEST-QTY",
            "vendor_name": "Global Logistics & Freight LLC",
            "purchase_order_number": "PO-2026-002",
            "subtotal": 4800.00,
            "tax_amount": 384.00,
            "total_amount": 5184.00,
            "line_items": [
                {"description": "Interstate Freight - 4 Containers", "quantity": 6, "unit_price": 800.00, "amount": 4800.00}
            ],
        }
        res = self.service.verify_invoice(inv)
        self.assertEqual(res["verification_status"], "NEEDS_REVIEW")
        self.assertTrue(any("QUANTITY_MISMATCH" in e for e in res["detected_exceptions"]))

    def test_scenario_8_duplicate_invoice(self):
        """Scenario 8: Duplicate invoice number and vendor -> BLOCKED."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES (?, ?, ?, ?);
            """,
            ("INV-EXISTING-99", "Apex Cloud Services Inc.", 5000.00, "RECEIVED"),
        )
        conn.commit()
        conn.close()

        inv = {
            "invoice_number": "INV-EXISTING-99",
            "vendor_name": "Apex Cloud Services Inc.",
            "purchase_order_number": "PO-2026-001",
            "subtotal": 5000.00,
            "tax_amount": 0.00,
            "total_amount": 5000.00,
            "line_items": [],
        }
        res = self.service.verify_invoice(inv)
        self.assertEqual(res["verification_status"], "BLOCKED")
        self.assertTrue(any("DUPLICATE_INVOICE" in e for e in res["detected_exceptions"]))


if __name__ == "__main__":
    unittest.main()
