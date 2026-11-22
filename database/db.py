"""
FINFLOW AI Database Layer
Handles SQLite connection, schema definition, and migration.
"""

import os
import sqlite3
from typing import Optional

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(DB_DIR, "finflow.db")


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Returns a SQLite connection with row_factory set to sqlite3.Row."""
    target_path = db_path or os.getenv("DB_PATH", DEFAULT_DB_PATH)
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[str] = None):
    """Initializes tables for vendors, purchase orders, invoices, exceptions, approvals and audits."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
    -- Vendors table
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        tax_id TEXT,
        address TEXT,
        contact_email TEXT,
        bank_account TEXT,
        status TEXT DEFAULT 'ACTIVE', -- ACTIVE, SUSPENDED, BLOCKED
        risk_score REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Purchase Orders table
    CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        po_number TEXT UNIQUE NOT NULL,
        vendor_id TEXT NOT NULL,
        total_amount REAL NOT NULL,
        tax_amount REAL DEFAULT 0.0,
        status TEXT DEFAULT 'OPEN', -- OPEN, PARTIALLY_FULFILLED, CLOSED, CANCELLED
        currency TEXT DEFAULT 'USD',
        issue_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id)
    );

    -- Purchase Order Line Items
    CREATE TABLE IF NOT EXISTS po_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        po_number TEXT NOT NULL,
        item_description TEXT NOT NULL,
        quantity REAL NOT NULL,
        unit_price REAL NOT NULL,
        total_price REAL NOT NULL,
        FOREIGN KEY (po_number) REFERENCES purchase_orders(po_number)
    );

    -- Invoices table
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number TEXT NOT NULL,
        vendor_id TEXT,
        vendor_name TEXT,
        po_number TEXT,
        file_name TEXT,
        file_hash TEXT, -- SHA-256 for duplicate detection
        invoice_date DATE,
        due_date DATE,
        subtotal REAL DEFAULT 0.0,
        tax_amount REAL DEFAULT 0.0,
        total_amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        status TEXT DEFAULT 'RECEIVED', 
        -- Status flow: RECEIVED -> EXTRACTED -> VERIFYING -> EXCEPTION -> PENDING_APPROVAL -> APPROVED -> REJECTED -> PAID
        payment_terms TEXT,
        extraction_raw_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Invoice Line Items
    CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        item_description TEXT NOT NULL,
        quantity REAL NOT NULL,
        unit_price REAL NOT NULL,
        total_price REAL NOT NULL,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
    );

    -- Exceptions table
    CREATE TABLE IF NOT EXISTS exceptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        exception_type TEXT NOT NULL, -- DUPLICATE, AMOUNT_MISMATCH, VENDOR_UNVERIFIED, TAX_ERROR, SUSPICIOUS_ANOMALY
        severity TEXT NOT NULL,       -- CRITICAL, HIGH, MEDIUM, LOW
        description TEXT NOT NULL,
        ai_summary TEXT,              -- AI investigation summary
        recommended_action TEXT,      -- Action recommended by investigation engine
        details_json TEXT,
        status TEXT DEFAULT 'OPEN',   -- OPEN, UNDER_INVESTIGATION, RESOLVED, REOPENED, REJECTED
        investigation_notes TEXT,     -- Auditor notes while under investigation
        resolution_notes TEXT,        -- Justification when resolved
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
    );

    -- Human Approvals and Payments
    CREATE TABLE IF NOT EXISTS approvals_and_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        decision TEXT NOT NULL, -- APPROVED, REJECTED, CORRECTION_REQUESTED, ON_HOLD
        decision_by TEXT NOT NULL, -- Human approver name or email
        comments TEXT,
        override_reason TEXT,
        correction_reason TEXT,
        payment_method TEXT, -- ACH, WIRE, VIRTUAL_CARD
        simulated_payment_id TEXT,
        payment_status TEXT DEFAULT 'PENDING', -- PENDING, PREPARED, EXECUTED, FAILED
        payment_date TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id)
    );

    -- Payment Transactions Table (Simulated disbursement transactions)
    CREATE TABLE IF NOT EXISTS payment_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_ref TEXT UNIQUE NOT NULL, -- e.g. TXN-ACH-XXXXXXXX
        invoice_id INTEGER NOT NULL,
        approval_id INTEGER,
        vendor_name TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        payment_rail TEXT NOT NULL,           -- ACH Corporate Credit, Fedwire High-Value, Single-Use Virtual Card
        bank_account TEXT,
        status TEXT NOT NULL,                 -- PREPARED, EXECUTED, FAILED
        failure_reason TEXT,
        simulated_by TEXT NOT NULL,           -- Operator identity
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        settled_at TIMESTAMP,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id),
        FOREIGN KEY (approval_id) REFERENCES approvals_and_payments(id)
    );
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        agent_name TEXT NOT NULL, -- IntakeAgent, VerificationAgent, FinIntelAgent, WorkflowAgent, ReportingAgent, HumanUser
        action TEXT NOT NULL,
        level TEXT DEFAULT 'INFO', -- INFO, WARNING, ERROR, SUCCESS
        message TEXT NOT NULL,
        payload_json TEXT,
        actor TEXT,               -- Operator or Agent identifier (e.g., HumanReviewer, Orchestrator)
        previous_status TEXT,     -- Status before the transition
        new_status TEXT,          -- Status after the transition
        category TEXT DEFAULT 'SYSTEM', -- INTAKE, VERIFICATION, EXCEPTION, APPROVAL, PAYMENT, SYSTEM
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Invoice Verification History
    CREATE TABLE IF NOT EXISTS verification_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        invoice_number TEXT,
        verification_status TEXT NOT NULL, -- VERIFIED, NEEDS_REVIEW, BLOCKED
        vendor_status TEXT NOT NULL,       -- VERIFIED, UNCERTAIN, UNKNOWN, BLOCKED, INACTIVE
        po_status TEXT NOT NULL,           -- MATCHED, MISMATCH, MISSING, INVALID
        amount_status TEXT NOT NULL,       -- MATCHED, OVERBILLED, MATH_ERROR, DISCREPANCY
        detected_exceptions TEXT,          -- JSON list of strings/exceptions
        explanation TEXT,
        details_json TEXT,
        verification_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
    );

    -- Orchestrator Agent Execution Runs
    CREATE TABLE IF NOT EXISTS orchestrator_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT UNIQUE NOT NULL,
        invoice_id INTEGER,
        invoice_number TEXT,
        file_name TEXT,
        file_hash TEXT,
        workflow_status TEXT NOT NULL, -- COMPLETED, NEEDS_REVIEW, BLOCKED, FAILED
        stage TEXT NOT NULL,           -- INTAKE, VERIFICATION, FIN_INTEL, WORKFLOW, REPORTING, DONE
        context_json TEXT,
        error_message TEXT,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
    );
    """)

    conn.commit()

    # Apply idempotent schema migrations for existing SQLite databases
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(audit_logs);")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    if "actor" not in existing_cols:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN actor TEXT;")
    if "previous_status" not in existing_cols:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN previous_status TEXT;")
    if "new_status" not in existing_cols:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN new_status TEXT;")
    if "category" not in existing_cols:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN category TEXT DEFAULT 'SYSTEM';")
    conn.commit()

    conn.close()
