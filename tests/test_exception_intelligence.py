"""
Tests for Exception Intelligence and AI-Powered Investigation (Task 06):
- Detection and classification across all 4 severity levels (LOW, MEDIUM, HIGH, CRITICAL)
- Multiple exceptions on a single invoice
- AI / deterministic root cause investigation generation
- Human investigation notes, status transition to UNDER_INVESTIGATION
- Resolution guardrail (cannot resolve High/Critical without justification)
- Reopening of resolved exceptions
"""

import os
import tempfile
import unittest
from database.seed_data import seed_database
from database.db import get_db_connection
from services.exception_intelligence_service import (
    ExceptionIntelligenceService,
    classify_exception_severity,
)


class TestExceptionIntelligence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_exceptions.db")
        seed_database(self.db_path)
        self.service = ExceptionIntelligenceService(db_path=self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_four_severity_levels_classification(self):
        """Test classification into LOW, MEDIUM, HIGH, and CRITICAL."""
        # 1. Critical
        self.assertEqual(classify_exception_severity("DUPLICATE_INVOICE"), "CRITICAL")
        self.assertEqual(classify_exception_severity("BLOCKED_VENDOR"), "CRITICAL")

        # 2. High
        self.assertEqual(classify_exception_severity("PO_VENDOR_MISMATCH"), "HIGH")
        self.assertEqual(classify_exception_severity("UNKNOWN_VENDOR"), "HIGH")
        self.assertEqual(classify_exception_severity("OVERBILLING", {"discrepancy": 2000, "po_total": 5000}), "HIGH")

        # 3. Medium
        self.assertEqual(classify_exception_severity("QUANTITY_MISMATCH"), "MEDIUM")
        self.assertEqual(classify_exception_severity("TAX_ERROR"), "MEDIUM")
        self.assertEqual(classify_exception_severity("OVERBILLING", {"discrepancy": 50, "po_total": 5000}), "MEDIUM")

        # 4. Low
        self.assertEqual(classify_exception_severity("PARTIAL_BILLING"), "LOW")
        self.assertEqual(classify_exception_severity("MISSING_INFO"), "LOW")

    def test_multiple_exceptions_enrichment_and_persistence(self):
        """Test recording multiple exceptions with AI investigation on one invoice."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES (?, ?, ?, 'EXCEPTION');
            """,
            ("INV-MULTI-EXC-101", "Global Logistics & Freight LLC", 7500.00),
        )
        inv_id = cursor.lastrowid
        conn.commit()
        conn.close()

        exceptions_to_record = [
            {"type": "AMOUNT_MISMATCH", "description": "Overbilled by $1,500 over PO", "details": {"discrepancy": 1500, "po_total": 6000}},
            {"type": "QUANTITY_MISMATCH", "description": "Delivered 5 units instead of 4", "details": {"qty": 5, "po_qty": 4}},
            {"type": "TAX_ERROR", "description": "Stated tax rate deviated by 3%", "details": {}},
        ]

        inv_meta = {
            "invoice_number": "INV-MULTI-EXC-101",
            "vendor_name": "Global Logistics & Freight LLC",
            "total_amount": 7500.00,
        }

        enriched = self.service.record_and_enrich_exceptions(
            invoice_id=inv_id,
            invoice_metadata=inv_meta,
            detected_exceptions=exceptions_to_record,
            mock_mode=True,
        )

        self.assertEqual(len(enriched), 3)
        for item in enriched:
            self.assertIn(item["severity"], ["HIGH", "MEDIUM", "LOW"])
            self.assertTrue(len(item["ai_summary"]) > 5)
            self.assertTrue(len(item["recommended_action"]) > 5)

    def test_investigation_notes_and_status_transitions(self):
        """Test adding investigation notes, transition to UNDER_INVESTIGATION, and reopening."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-TEST-NOTE-1', 'Apex Cloud Services Inc.', 1000.0, 'EXCEPTION');
            """
        )
        inv_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO exceptions (invoice_id, exception_type, severity, description, status)
            VALUES (?, 'PRICE_MISMATCH', 'MEDIUM', 'Unit price deviates from PO', 'OPEN');
            """,
            (inv_id,),
        )
        exc_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Step 1: Mark under investigation with notes
        res1 = self.service.update_exception_status(
            exception_id=exc_id,
            new_status="UNDER_INVESTIGATION",
            investigator="Auditor_Sarah",
            notes="Vendor account executive stated new price tier was applied.",
        )
        self.assertEqual(res1["new_status"], "UNDER_INVESTIGATION")

        # Step 2: Resolve with justification
        res2 = self.service.update_exception_status(
            exception_id=exc_id,
            new_status="RESOLVED",
            investigator="Auditor_Sarah",
            resolution_notes="Authorized price variance via procurement ticket #8812.",
        )
        self.assertEqual(res2["new_status"], "RESOLVED")

        # Step 3: Reopen exception
        res3 = self.service.update_exception_status(
            exception_id=exc_id,
            new_status="REOPENED",
            investigator="Supervisor_Bob",
            notes="Need copy of signed contract addendum.",
        )
        self.assertEqual(res3["new_status"], "REOPENED")

    def test_high_critical_resolution_guardrail(self):
        """High and Critical exceptions MUST require a resolution note."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_name, total_amount, status)
            VALUES ('INV-TEST-GUARD-1', 'Apex Cloud Services Inc.', 2000.0, 'EXCEPTION');
            """
        )
        inv_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO exceptions (invoice_id, exception_type, severity, description, status)
            VALUES (?, 'BLOCKED_VENDOR', 'CRITICAL', 'Restricted entity', 'OPEN');
            """,
            (inv_id,),
        )
        exc_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Attempt to resolve without justification
        with self.assertRaises(ValueError):
            self.service.update_exception_status(
                exception_id=exc_id,
                new_status="RESOLVED",
                investigator="Rogue_User",
                resolution_notes="",  # Empty note must fail
            )


if __name__ == "__main__":
    unittest.main()
