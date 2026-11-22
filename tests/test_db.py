"""
Unit tests for database initialization, schema integrity, and seeding.
"""

import os
import tempfile
import unittest
from database.db import get_db_connection, init_db
from database.seed_data import seed_database


class TestDatabaseLayer(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_schema_creation_and_seeding(self):
        # Initialize and seed
        seed_database(self.db_path)

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Verify vendors seeded
        cursor.execute("SELECT COUNT(*) FROM vendors;")
        vendor_count = cursor.fetchone()[0]
        self.assertGreaterEqual(vendor_count, 5)

        # Verify purchase orders seeded
        cursor.execute("SELECT COUNT(*) FROM purchase_orders;")
        po_count = cursor.fetchone()[0]
        self.assertGreaterEqual(po_count, 4)

        # Verify line items
        cursor.execute("SELECT COUNT(*) FROM po_items WHERE po_number = 'PO-2026-001';")
        po_items_count = cursor.fetchone()[0]
        self.assertEqual(po_items_count, 3)

        # Test inserting an invoice and audit log
        cursor.execute(
            """
            INSERT INTO invoices (invoice_number, vendor_id, vendor_name, total_amount, status)
            VALUES (?, ?, ?, ?, ?);
            """,
            ("INV-TEST-001", "VND-001", "Apex Cloud Services Inc.", 12500.00, "RECEIVED"),
        )
        invoice_id = cursor.lastrowid
        self.assertIsNotNone(invoice_id)

        cursor.execute(
            """
            INSERT INTO audit_logs (invoice_id, agent_name, action, level, message)
            VALUES (?, ?, ?, ?, ?);
            """,
            (invoice_id, "TestAgent", "TEST_ACTION", "INFO", "Sample audit record"),
        )
        cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE invoice_id = ?;", (invoice_id,))
        self.assertEqual(cursor.fetchone()[0], 1)

        conn.close()


if __name__ == "__main__":
    unittest.main()
