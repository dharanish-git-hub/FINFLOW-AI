"""
Invoice Processing & AI Extraction View
Provides full manual or AI-assisted invoice PDF extraction, PyMuPDF parsing with diagnostic checks,
automated vendor verification and PO matching, structured review & edit interface,
and non-duplicate SQLite persistence with complete verification history.
"""

import os
import json
import hashlib
import streamlit as st
import pandas as pd
from database.db import get_db_connection
from services.gemini_service import GeminiService
from services.pdf_service import extract_text_with_diagnostics, generate_all_sample_invoices
from services.verification_service import VerificationService
from ui.components import render_pdf_preview
from agents.base_agent import InvoiceExtractionResult, InvoiceItemSchema
from agents.intake_agent import IntakeAgent


def render_invoice_processing_view(db_path: str = None, api_key: str = None, model: str = None, mock_mode: bool = True):
    st.markdown("### 📄 AI-Powered Invoice PDF Extraction & Verification")
    st.caption("Upload invoice PDFs, extract structured metadata with Gemini, execute automated 3-way vendor & PO verification, and commit to SQLite.")

    verification_service = VerificationService(db_path=db_path)

    # 1. File Upload and Document Selector
    col_upload, col_preview = st.columns([1.1, 0.9])

    with col_upload:
        st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
        st.markdown("##### 1. Upload Invoice PDF")
        uploaded_file = st.file_uploader(
            "Select Invoice Document (PDF)",
            type=["pdf"],
            key="invoice_processing_uploader",
            help="Max size 20MB. Supports native digital PDFs.",
        )

        st.markdown("---")
        st.markdown("##### 💡 Or Select Synthetic Sample PDF")
        sample_dir = "sample_data"
        generate_all_sample_invoices(sample_dir)
        samples = {
            "Choose a test scenario...": None,
            "1. Standard Cloud Services (Apex Cloud -> PO-2026-001) [VERIFIED]": os.path.join(sample_dir, "invoice_valid_apex.pdf"),
            "2. Freight & Logistics (Global Logistics -> PO-2026-002) [OVERBILLED / NEEDS_REVIEW]": os.path.join(sample_dir, "invoice_mismatch_logistics.pdf"),
            "3. Security Audit Retainer (CyberShield Security) [MATH_ERROR / NEEDS_REVIEW]": os.path.join(sample_dir, "invoice_tax_error_cybershield.pdf"),
            "4. Unknown Offshore Advisory (Advisory Shell Corp) [UNKNOWN / BLOCKED]": os.path.join(sample_dir, "invoice_unknown_shell.pdf"),
        }
        selected_sample_key = st.selectbox("Pre-configured Synthetic Test Documents:", list(samples.keys()))

        pdf_bytes = None
        orig_filename = None

        if uploaded_file is not None:
            pdf_bytes = uploaded_file.read()
            orig_filename = uploaded_file.name
        elif selected_sample_key and samples[selected_sample_key]:
            filepath = samples[selected_sample_key]
            with open(filepath, "rb") as f:
                pdf_bytes = f.read()
            orig_filename = os.path.basename(filepath)

        extract_btn = st.button("⚡ Extract & Verify Invoice with AI", type="primary", disabled=(pdf_bytes is None))
        st.markdown('</div>', unsafe_allow_html=True)

    with col_preview:
        st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
        st.markdown("##### 📑 PDF Visual Document Inspector")
        if pdf_bytes:
            render_pdf_preview(pdf_bytes)
        else:
            st.info("Upload or select a PDF to preview pages.")
        st.markdown('</div>', unsafe_allow_html=True)

    # 2. Text Extraction & Diagnostic Validation
    if extract_btn and pdf_bytes:
        with st.spinner("🔍 Running PyMuPDF text diagnostics, Gemini extraction, and verification checks..."):
            diag = extract_text_with_diagnostics(pdf_bytes, orig_filename)

            if not diag["success"]:
                if diag["error_type"] == "SCANNED_DOCUMENT":
                    st.error(f"🛑 **{diag['message']}**")
                    st.info("💡 **Scanned Document Handling**: This PDF consists of raster images with no text streams. FinFlow AI operates transparently and requires OCR preprocessing before extraction.")
                elif diag["error_type"] == "PASSWORD_PROTECTED":
                    st.error(f"🔒 **{diag['message']}**")
                elif diag["error_type"] == "EMPTY_FILE":
                    st.error(f"⚠️ **{diag['message']}**")
                else:
                    st.error(f"❌ **Extraction Error**: {diag['message']}")
                return

            # Proceed to Gemini / Mock Extraction
            intake_agent = IntakeAgent(api_key=api_key, model=model, mock_mode=mock_mode)
            try:
                extraction, file_hash, raw_text = intake_agent.process(pdf_bytes, orig_filename)
                st.session_state["extracted_invoice_data"] = extraction.model_dump()
                st.session_state["extracted_file_hash"] = file_hash
                st.session_state["extracted_file_name"] = orig_filename
                st.session_state["extracted_raw_text"] = raw_text
                st.session_state["extraction_source"] = "MOCK_AI" if intake_agent.mock_mode else f"GEMINI ({model or 'default'})"

                # Run Deterministic Verification Service
                v_res = verification_service.verify_invoice(extraction, file_hash=file_hash)
                st.session_state["verification_result"] = v_res

                st.success(f"Invoice extracted and verified via {st.session_state['extraction_source']}!")
            except Exception as e:
                st.error(f"❌ Extraction or Verification Error: {str(e)}")
                return

    # 3. Verification Engine Results Display
    if "verification_result" in st.session_state and "extracted_invoice_data" in st.session_state:
        v_res = st.session_state["verification_result"]
        data = st.session_state["extracted_invoice_data"]

        st.markdown("---")
        st.markdown("### 🛡️ Automated Verification & 3-Way Match Results")

        v_status = v_res["verification_status"]
        status_color = "#34D399" if v_status == "VERIFIED" else ("#FBBF24" if v_status == "NEEDS_REVIEW" else "#F87171")
        badge_class = "badge-approved" if v_status == "VERIFIED" else ("badge-pending" if v_status == "NEEDS_REVIEW" else "badge-exception")

        st.markdown(
            f"""
            <div class="glass-panel" style="border-left: 4px solid {status_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h4 style="margin: 0; color: #F8FAFC;">Overall Status: <span style="color: {status_color}; font-weight: 800;">{v_status}</span></h4>
                    <span class="badge {badge_class}">{v_status}</span>
                </div>
                <p style="color: #CBD5E1; margin: 0 0 8px 0; font-size: 13px;">{v_res['explanation']}</p>
                <span style="font-size: 11px; color: #64748B;">Verified at: {v_res['verification_timestamp']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c_v1, c_v2, c_v3 = st.columns(3)
        with c_v1:
            st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
            st.markdown("###### 1. Vendor Verification")
            st.write(f"**Vendor Status:** `{v_res['vendor_status']}`")
            st.write(f"**Registered ID:** `{v_res.get('matched_vendor_id') or 'Unmatched'}`")
            st.write(f"**Extracted Name:** `{data.get('vendor_name')}`")
            st.markdown('</div>', unsafe_allow_html=True)

        with c_v2:
            st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
            st.markdown("###### 2. Purchase Order Match")
            st.write(f"**PO Status:** `{v_res['po_status']}`")
            st.write(f"**PO Number:** `{data.get('purchase_order_number') or data.get('po_number') or 'N/A'}`")
            po_tot = v_res.get("po_total")
            st.write(f"**PO Authorized Total:** `{f'${po_tot:,.2f}' if po_tot else 'N/A'}`")
            st.markdown('</div>', unsafe_allow_html=True)

        with c_v3:
            st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
            st.markdown("###### 3. Financial Calculation")
            st.write(f"**Amount Status:** `{v_res['amount_status']}`")
            st.write(f"**Billed Total:** `${float(data.get('total_amount', 0.0)):,.2f}`")
            sub = float(data.get('subtotal', 0.0))
            tax = float(data.get('tax_amount', 0.0))
            st.write(f"**Subtotal + Tax:** `${sub + tax:,.2f}`")
            st.markdown('</div>', unsafe_allow_html=True)

        # Discrepancies & Exceptions Details
        if v_res["detected_exceptions"]:
            st.markdown("##### ⚠️ Flagged Exceptions & Discrepancies")
            for exc in v_res["detected_exceptions"]:
                st.warning(f"• {exc}")

        # PO Line Items Match Table
        if v_res.get("line_matches"):
            st.markdown("##### 🔍 Line-Item 3-Way Match Comparison")
            matches_df = pd.DataFrame(v_res["line_matches"])
            st.dataframe(matches_df, use_container_width=True, hide_index=True)

    # 4. Review and Edit Extracted Information Interface
    if "extracted_invoice_data" in st.session_state:
        st.markdown("---")
        st.markdown("### 📝 Review & Edit Extracted Invoice Information")
        st.caption("Review extracted fields, edit any discrepancies, and commit directly to the enterprise SQLite ledger.")

        data = st.session_state["extracted_invoice_data"]
        raw_text = st.session_state.get("extracted_raw_text", "")
        file_hash = st.session_state.get("extracted_file_hash", "")
        file_name = st.session_state.get("extracted_file_name", "document.pdf")
        source = st.session_state.get("extraction_source", "AI")
        v_res = st.session_state.get("verification_result", {})

        st.info(f"Extraction Source: **{source}** | File: `{file_name}` | Verification: **{v_res.get('verification_status', 'UNVERIFIED')}**")

        with st.form("invoice_review_and_save_form"):
            col_f1, col_f2 = st.columns(2)

            with col_f1:
                st.markdown("##### 🏢 Vendor & Identity Details")
                edit_inv_num = st.text_input("Invoice Number *", value=data.get("invoice_number", ""))
                edit_vendor_name = st.text_input("Vendor Name *", value=data.get("vendor_name", ""))
                edit_vendor_address = st.text_input("Vendor Address", value=data.get("vendor_address", ""))
                edit_vendor_tax_id = st.text_input("Vendor Tax ID / EIN", value=data.get("vendor_tax_id", ""))
                edit_po_num = st.text_input("Purchase Order Number", value=data.get("purchase_order_number") or data.get("po_number") or "")

            with col_f2:
                st.markdown("##### 📅 Terms & Financial Totals")
                c_d1, c_d2 = st.columns(2)
                with c_d1:
                    edit_inv_date = st.text_input("Invoice Date (YYYY-MM-DD)", value=data.get("invoice_date", "2026-11-15"))
                with c_d2:
                    edit_due_date = st.text_input("Due Date (YYYY-MM-DD)", value=data.get("due_date", "2026-12-15"))

                edit_terms = st.text_input("Payment Terms", value=data.get("payment_terms", "Net 30"))
                edit_curr = st.text_input("Currency", value=data.get("currency", "USD"))

                col_tot1, col_tot2, col_tot3 = st.columns(3)
                with col_tot1:
                    edit_subtotal = st.number_input("Subtotal ($)", value=float(data.get("subtotal", 0.0)), step=10.0)
                with col_tot2:
                    edit_tax = st.number_input("Tax Amount ($)", value=float(data.get("tax_amount", 0.0)), step=5.0)
                with col_tot3:
                    edit_total = st.number_input("Total Due ($) *", value=float(data.get("total_amount", 0.0)), step=10.0)

            st.markdown("##### 📦 Itemized Line Items")
            line_items = data.get("line_items", [])
            if line_items:
                items_df = pd.DataFrame(line_items)
                st.dataframe(items_df, use_container_width=True, hide_index=True)
            else:
                st.caption("No individual line items parsed; single aggregate entry will be stored.")

            save_submitted = st.form_submit_button("💾 Save Verified Invoice to SQLite Ledger", type="primary")

        # Form submission handling
        if save_submitted:
            if not edit_inv_num.strip():
                st.error("Invoice number is mandatory.")
            elif not edit_vendor_name.strip():
                st.error("Vendor name is mandatory.")
            elif edit_total <= 0:
                st.error("Total amount must be greater than zero.")
            else:
                conn = get_db_connection(db_path)
                cursor = conn.cursor()

                # Re-verify edited values
                recheck_payload = {
                    "invoice_number": edit_inv_num.strip(),
                    "vendor_name": edit_vendor_name.strip(),
                    "vendor_address": edit_vendor_address.strip(),
                    "vendor_tax_id": edit_vendor_tax_id.strip(),
                    "purchase_order_number": edit_po_num.strip(),
                    "subtotal": edit_subtotal,
                    "tax_amount": edit_tax,
                    "total_amount": edit_total,
                    "line_items": line_items,
                }
                recheck_v = verification_service.verify_invoice(recheck_payload, file_hash=file_hash)

                # Check for existing duplicate record
                cursor.execute(
                    """
                    SELECT id, invoice_number, vendor_name, total_amount, created_at 
                    FROM invoices 
                    WHERE (file_hash = ? AND file_hash != '') OR (invoice_number = ? AND vendor_name = ?);
                    """,
                    (file_hash, edit_inv_num.strip(), edit_vendor_name.strip()),
                )
                existing_invoice = cursor.fetchone()

                if existing_invoice:
                    st.warning(
                        f"⚠️ Record already exists! Invoice #{existing_invoice['invoice_number']} for '{existing_invoice['vendor_name']}' "
                        f"(ID: {existing_invoice['id']}, Total: ${existing_invoice['total_amount']:,.2f}) is already stored in the SQLite ledger."
                    )
                    conn.close()
                else:
                    saved_payload = {
                        **recheck_payload,
                        "invoice_date": edit_inv_date.strip(),
                        "due_date": edit_due_date.strip(),
                        "payment_terms": edit_terms.strip(),
                        "currency": edit_curr.strip(),
                    }

                    # Determine initial status from verification
                    if recheck_v["verification_status"] == "VERIFIED":
                        initial_status = "PENDING_APPROVAL"
                    elif recheck_v["verification_status"] == "BLOCKED":
                        initial_status = "EXCEPTION"
                    else:
                        initial_status = "EXCEPTION"

                    cursor.execute(
                        """
                        INSERT INTO invoices (
                            invoice_number, vendor_name, vendor_id, po_number, file_name, file_hash,
                            invoice_date, due_date, subtotal, tax_amount, total_amount,
                            currency, status, payment_terms, extraction_raw_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            edit_inv_num.strip(),
                            edit_vendor_name.strip(),
                            recheck_v.get("matched_vendor_id"),
                            edit_po_num.strip() if edit_po_num.strip() else None,
                            file_name,
                            file_hash,
                            edit_inv_date.strip(),
                            edit_due_date.strip(),
                            edit_subtotal,
                            edit_tax,
                            edit_total,
                            edit_curr.strip(),
                            initial_status,
                            edit_terms.strip(),
                            json.dumps(saved_payload),
                        ),
                    )
                    saved_id = cursor.lastrowid

                    # Insert line items
                    for item in line_items:
                        amt = item.get("amount") or item.get("total_price") or (item.get("quantity", 1) * item.get("unit_price", 0))
                        cursor.execute(
                            """
                            INSERT INTO invoice_items (invoice_id, item_description, quantity, unit_price, total_price)
                            VALUES (?, ?, ?, ?, ?);
                            """,
                            (
                                saved_id,
                                item.get("description", "Standard Item"),
                                item.get("quantity", 1.0),
                                item.get("unit_price", 0.0),
                                amt,
                            ),
                        )

                    # Insert exceptions if any
                    for exc in recheck_v["detected_exceptions"]:
                        sev = "CRITICAL" if recheck_v["verification_status"] == "BLOCKED" else "WARNING"
                        exc_type = exc.split(":")[0] if ":" in exc else "VERIFICATION_EXCEPTION"
                        cursor.execute(
                            """
                            INSERT INTO exceptions (invoice_id, exception_type, severity, description, status)
                            VALUES (?, ?, ?, ?, 'OPEN');
                            """,
                            (saved_id, exc_type, sev, exc),
                        )

                    # Add SOX Audit Trail entry
                    cursor.execute(
                        """
                        INSERT INTO audit_logs (invoice_id, agent_name, action, level, message, payload_json)
                        VALUES (?, 'VerificationService', 'INVOICE_VERIFIED_AND_SAVED', ?, ?, ?);
                        """,
                        (
                            saved_id,
                            "SUCCESS" if recheck_v["verification_status"] == "VERIFIED" else "WARNING",
                            f"Invoice #{edit_inv_num.strip()} verified (Status: {recheck_v['verification_status']}) and saved to ledger (Total: ${edit_total:,.2f}).",
                            json.dumps(recheck_v),
                        ),
                    )

                    conn.commit()
                    conn.close()

                    st.success(f"🎉 Invoice #{edit_inv_num.strip()} saved successfully (DB Record ID: {saved_id})! Pipeline Status: **{initial_status}**.")
                    del st.session_state["extracted_invoice_data"]
                    if "verification_result" in st.session_state:
                        del st.session_state["verification_result"]
                    st.rerun()

    # 5. Historical Verification Logs Section
    st.markdown("---")
    st.markdown("##### 📜 Recent Verification History (SQLite Ledger)")
    history = verification_service.get_verification_history(limit=8)
    if history:
        h_rows = []
        for h in history:
            h_rows.append({
                "ID": h["id"],
                "Invoice #": h["invoice_number"],
                "Overall Status": h["verification_status"],
                "Vendor Check": h["vendor_status"],
                "PO Check": h["po_status"],
                "Amount Check": h["amount_status"],
                "Timestamp": h["verification_timestamp"],
            })
        st.dataframe(pd.DataFrame(h_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No historical verification runs recorded yet.")
