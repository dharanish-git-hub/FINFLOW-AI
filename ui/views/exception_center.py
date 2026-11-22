"""
Exception Management & AI Investigation Center View
Provides comprehensive exception metrics, severity breakdown (LOW, MEDIUM, HIGH, CRITICAL),
AI root-cause investigation, and interactive human resolution, notes, and reopening workflows.
"""

import json
import streamlit as st
import pandas as pd
from database.db import get_db_connection
from services.exception_intelligence_service import ExceptionIntelligenceService


def render_exception_center_view(db_path: str = None, gemini_service=None):
    st.markdown("### ⚠️ Exception Intelligence & AI Investigation Center")
    st.caption("Investigate flagged financial anomalies, inspect evidence-based AI root cause explanations, and manage human audit resolutions.")

    exc_service = ExceptionIntelligenceService(db_path=db_path, gemini_service=gemini_service)
    metrics = exc_service.get_exception_dashboard_metrics()

    # 1. KPI Cards across Status & Severities
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Exceptions", metrics["total"], f"{metrics['open']} Open")
    with col2:
        st.metric("Critical (Immediate Block)", metrics["critical"], delta="Blocked" if metrics["critical"] > 0 else "0", delta_color="inverse")
    with col3:
        st.metric("High Severity", metrics["high"], delta="Review Req" if metrics["high"] > 0 else "0", delta_color="inverse")
    with col4:
        st.metric("Medium Severity", metrics["medium"], delta="Review Req" if metrics["medium"] > 0 else "0", delta_color="inverse")
    with col5:
        st.metric("Low / Minor", metrics["low"], delta=f"{metrics['resolved']} Resolved", delta_color="normal")

    st.markdown("---")

    # 2. Filter & Query Exceptions from SQLite
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        status_filter = st.selectbox(
            "Filter by Status:",
            ["ALL", "OPEN", "UNDER_INVESTIGATION", "RESOLVED", "REOPENED"],
            index=0,
        )

    where_clause = ""
    params = []
    if status_filter != "ALL":
        where_clause = "WHERE e.status = ?"
        params.append(status_filter)

    cursor.execute(
        f"""
        SELECT e.id as exception_id, e.invoice_id, e.exception_type, e.severity, e.description, 
               e.ai_summary, e.recommended_action, e.investigation_notes, e.resolution_notes,
               e.status as exception_status, e.created_at, e.resolved_at,
               i.invoice_number, i.vendor_name, i.total_amount, i.po_number
        FROM exceptions e
        JOIN invoices i ON e.invoice_id = i.id
        {where_clause}
        ORDER BY CASE e.severity 
            WHEN 'CRITICAL' THEN 1 
            WHEN 'HIGH' THEN 2 
            WHEN 'MEDIUM' THEN 3 
            ELSE 4 END, e.id DESC;
        """,
        params,
    )
    rows = [dict(r) for r in cursor.fetchall()]

    if not rows:
        st.success(f"🎉 No exceptions currently matching status: **{status_filter}**.")
        conn.close()
        return

    # Overview table
    df = pd.DataFrame(rows)
    df["total_amount"] = df["total_amount"].apply(lambda v: f"${v:,.2f}")
    df_display = df[["exception_id", "invoice_number", "vendor_name", "exception_type", "severity", "total_amount", "exception_status", "description"]]
    df_display.columns = ["Ex ID", "Invoice #", "Vendor", "Type", "Severity", "Amount", "Status", "Description"]
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # 3. Interactive Investigation & Action Center
    st.markdown("---")
    st.markdown("##### 🔬 AI Root-Cause Investigation & Action Console")

    exc_options = {
        f"Ex #{r['exception_id']} - {r['invoice_number']} ({r['vendor_name']}) [{r['severity']}: {r['exception_type']}] - Status: {r['exception_status']}": r
        for r in rows
    }
    chosen_label = st.selectbox("Select an exception to investigate / take action:", list(exc_options.keys()))
    selected_exc = exc_options[chosen_label]

    c_left, c_right = st.columns([1.2, 1])

    with c_left:
        sev = selected_exc["severity"]
        sev_color = "#F87171" if sev in ["CRITICAL", "HIGH"] else ("#FBBF24" if sev == "MEDIUM" else "#38BDF8")
        st.markdown(
            f"""
            <div class="glass-panel" style="border-left: 4px solid {sev_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <h5 style="margin: 0; color: #F8FAFC;">[{sev}] {selected_exc['exception_type']}</h5>
                    <span class="badge {'badge-exception' if sev in ['CRITICAL', 'HIGH'] else 'badge-pending'}">{selected_exc['exception_status']}</span>
                </div>
                <p><b>Invoice #:</b> {selected_exc['invoice_number']} | <b>Vendor:</b> {selected_exc['vendor_name']}</p>
                <p><b>Referenced PO:</b> {selected_exc['po_number'] or 'None'} | <b>Amount:</b> {selected_exc['total_amount']}</p>
                <hr style="border-color: #334155;"/>
                <p><b>Detected Discrepancy:</b> {selected_exc['description']}</p>
                <div style="background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 12px; margin-top: 10px;">
                    <span style="font-weight: 700; color: #38BDF8; font-size: 12px;">🧠 AI Investigation Summary:</span>
                    <p style="font-size: 12px; color: #CBD5E1; margin: 4px 0 8px 0;">{selected_exc['ai_summary'] or 'Objective evidence analysis completed.'}</p>
                    <span style="font-weight: 700; color: #34D399; font-size: 12px;">💡 Recommended Practical Action:</span>
                    <p style="font-size: 12px; color: #CBD5E1; margin: 4px 0 0 0;">{selected_exc['recommended_action'] or 'Review discrepancies against purchase order contract.'}</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Investigation audit log
        if selected_exc["investigation_notes"]:
            st.markdown("###### 📝 Ongoing Investigation Audit Notes:")
            st.text_area("Audit Notes Trail", value=selected_exc["investigation_notes"], height=100, disabled=True)
        if selected_exc["resolution_notes"]:
            st.markdown("###### ✅ Resolution Justification:")
            st.info(selected_exc["resolution_notes"])

    with c_right:
        st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
        st.markdown("###### ✍️ Human Investigator Action")

        auditor_name = st.text_input("Investigator Identity (Name / Email):", value="auditor@enterprise.com", key="auditor_input")
        audit_note = st.text_area("Investigation Finding / Note:", placeholder="e.g. Spoke with vendor account manager; fuel surcharge was agreed via PO amendment.", key="audit_note_input")

        col_act1, col_act2 = st.columns(2)

        with col_act1:
            under_inv_btn = st.button("🔍 Mark Under Investigation", use_container_width=True)
        with col_act2:
            reopen_btn = st.button("🔄 Reopen Exception", use_container_width=True)

        st.markdown("---")
        resolution_input = st.text_input("Resolution Justification (Mandatory for High/Critical):", placeholder="e.g. Approved price variance authorized by VP Procurement.", key="res_input")
        resolve_btn = st.button("✅ Resolve & Release to Approval", type="primary", use_container_width=True)

        if under_inv_btn:
            if not audit_note.strip():
                st.warning("Please record an investigation finding before changing status.")
            else:
                exc_service.update_exception_status(
                    exception_id=selected_exc["exception_id"],
                    new_status="UNDER_INVESTIGATION",
                    investigator=auditor_name,
                    notes=audit_note,
                )
                st.success("Exception marked as 'UNDER_INVESTIGATION'.")
                st.rerun()

        if reopen_btn:
            exc_service.update_exception_status(
                exception_id=selected_exc["exception_id"],
                new_status="REOPENED",
                investigator=auditor_name,
                notes=audit_note or "Reopened for re-audit.",
            )
            st.warning("Exception reopened.")
            st.rerun()

        if resolve_btn:
            try:
                exc_service.update_exception_status(
                    exception_id=selected_exc["exception_id"],
                    new_status="RESOLVED",
                    investigator=auditor_name,
                    notes=audit_note,
                    resolution_notes=resolution_input,
                )
                st.success("Exception resolved successfully! If all exceptions are resolved, invoice advances to Approval.")
                st.rerun()
            except ValueError as ve:
                st.error(f"🛑 Policy Guardrail: {str(ve)}")

        st.markdown('</div>', unsafe_allow_html=True)

    conn.close()
