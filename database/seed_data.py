"""
Seed reference vendors and purchase orders for realistic testing and matching.
"""

from database.db import get_db_connection, init_db


def seed_database(db_path=None):
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Check if vendors already seeded
    cursor.execute("SELECT COUNT(*) FROM vendors;")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # Seed Sample Vendors
    vendors = [
        (
            "VND-001",
            "Apex Cloud Services Inc.",
            "US-EIN-94-3829101",
            "100 Silicon Way, San Jose, CA 95113",
            "billing@apexcloud.com",
            "US-ACH-121000358-992384",
            "ACTIVE",
            0.02,
        ),
        (
            "VND-002",
            "Global Logistics & Freight LLC",
            "US-EIN-12-8849102",
            "450 Cargo Blvd, Chicago, IL 60601",
            "ar@globallogistics.com",
            "US-ACH-071000013-448192",
            "ACTIVE",
            0.05,
        ),
        (
            "VND-003",
            "CyberShield Security Corp",
            "US-EIN-88-2940192",
            "700 Defense Pkwy, Arlington, VA 22202",
            "invoicing@cybershield.io",
            "US-ACH-051400549-332910",
            "ACTIVE",
            0.01,
        ),
        (
            "VND-004",
            "Modern Office Interiors",
            "US-EIN-54-1928472",
            "120 Design Ave, Austin, TX 78701",
            "accounts@modernoffice.design",
            "US-ACH-111000025-110293",
            "ACTIVE",
            0.12,
        ),
        (
            "VND-005",
            "Blacklisted Shell Corp",
            "US-EIN-99-9999999",
            "PO Box 102, Tortola, BVI",
            "fraud@blacklistshell.fake",
            "KY-WIRE-009923-00192",
            "BLOCKED",
            0.99,
        ),
    ]

    cursor.executemany(
        """
        INSERT INTO vendors (vendor_id, name, tax_id, address, contact_email, bank_account, status, risk_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        vendors,
    )

    # Seed Sample Purchase Orders
    purchase_orders = [
        ("PO-2026-001", "VND-001", 12500.00, 1000.00, "OPEN", "USD", "2026-11-01"),
        ("PO-2026-002", "VND-002", 4800.00, 384.00, "OPEN", "USD", "2026-11-05"),
        ("PO-2026-003", "VND-003", 24000.00, 1920.00, "OPEN", "USD", "2026-11-10"),
        ("PO-2026-004", "VND-004", 6500.00, 520.00, "OPEN", "USD", "2026-11-12"),
    ]

    cursor.executemany(
        """
        INSERT INTO purchase_orders (po_number, vendor_id, total_amount, tax_amount, status, currency, issue_date)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        purchase_orders,
    )

    # Seed PO Items
    po_items = [
        # PO-2026-001: Apex Cloud
        ("PO-2026-001", "Cloud Compute Enterprise Tier (Monthly)", 1, 8000.00, 8000.00),
        ("PO-2026-001", "Dedicated High-Speed Interconnect", 1, 3500.00, 3500.00),
        ("PO-2026-001", "Priority Support SLA", 1, 1000.00, 1000.00),
        # PO-2026-002: Global Logistics
        ("PO-2026-002", "Interstate Freight - 4 Containers", 4, 1200.00, 4800.00),
        # PO-2026-003: CyberShield
        ("PO-2026-003", "SOC 2 Type II Continuous Audit Tool License (Annual)", 1, 20000.00, 20000.00),
        ("PO-2026-003", "Penetration Testing & Red Teaming Pack", 1, 4000.00, 4000.00),
        # PO-2026-004: Modern Office
        ("PO-2026-004", "Ergonomic Task Chairs (Model Elite)", 10, 450.00, 4500.00),
        ("PO-2026-004", "Motorized Standing Desks", 4, 500.00, 2000.00),
    ]

    cursor.executemany(
        """
        INSERT INTO po_items (po_number, item_description, quantity, unit_price, total_price)
        VALUES (?, ?, ?, ?, ?);
        """,
        po_items,
    )

    conn.commit()
    conn.close()
    print("Database successfully seeded with reference vendors and POs.")


if __name__ == "__main__":
    seed_database()
