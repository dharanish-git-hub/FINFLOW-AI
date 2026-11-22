"""
Human Approval & Workflow Management View
Provides complete human-in-the-loop invoice review, 3-way match validation inspection,
exception visibility, high-value dual confirmation, rejection justifications,
correction requests, and immutable payment simulation records.
"""

import streamlit as st
import pandas as pd
from services.approval_workflow_service import ApprovalWorkflowService, HIGH_VALUE_THRESHOLD


def render_approval_view(db_path: str = None):
    st.markdown("### ✍️ Human Authorization & Workflow Management Gate")
    st.caption("Zero-trust security policy: AI agents cannot authorize payments. Human reviewer sign-off is mandatory.")

    service = ApprovalWorkflowService(db_path=db_path)

    # 1. Filter selection
    col_filter, col_auth = st.columns([1.2, 1])
    with col_filter:
        status_filter = st.selectbox(
            "Filter Approval Queue:",
            ["PENDING_APPROVAL", "APPROVED", "REJECTED", "CORRECTION_REQUESTED", "ALL"],
            index=0,
            key="approval_status_filter",
        )
    with col_auth:
        st.caption("Simulated Reviewer Persona (Role-Based Access)")
        reviewer_name = st.text_input("Reviewer Identity:", value="cfo@enterprise.com", key="reviewer_persona_input")

    queue = service.get_approval_queue(status_filter=status_filter)

    if not queue:
        st.info(f"No invoices currently matching queue filter: **{status_filter}**.")
        return

    # Queue overview table
    df_queue = pd.DataFrame(queue)
    df_queue["formatted_amount"] = df_queue["total_amount"].apply(lambda v: f"${v:,.2f}")
    df_display = df_queue[["id", "invoice_number", "vendor_name", "po_number", "formatted_amount", "status", "open_exceptions_count", "critical_exceptions_count", "created_at"]]
    df_display.columns = ["ID", "Invoice #", "Vendor", "PO #", "Amount", "Status", "Open Exceptions", "Critical", "Received At"]
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("##### 🔍 Deep Invoice Review & Decision Console")

    inv_options = {
        f"#{r['id']} - {r['invoice_number']} | {r['vendor_name']} ({r['formatted_amount']}) - [{r['status']}]": r["id"]
        for r in queue
    }
    selected_label = st.selectbox("Select Invoice to Review:", list(inv_options.keys()), key="select_inv_to_review")
    chosen_id = inv_options[selected_label]

    # Load complete review bundle
    bundle = service.get_invoice_full_review_bundle(chosen_id)
    inv = bundle["invoice"]
    exceptions = bundle["exceptions"]
    line_items = bundle["line_items"]
    approval_history = bundle["approval_history"]

    # Main review panel layout
    c_left, c_right = st.columns([1.2, 1])

    with c_left:
        # High-value badge warning
        is_high_value = float(inv.get("total_amount", 0.0)) >= HIGH_VALUE_THRESHOLD

        st.markdown(
            f"""
            <div class="glass-panel" style="border-left: 4px solid {'#FBBF24' if is_high_value else '#38BDF8'};">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h5 style="margin: 0; color: #F8FAFC;">Voucher #{inv['invoice_number']}</h5>
                    <span class="badge {'badge-pending' if inv['status'] == 'PENDING_APPROVAL' else 'badge-approved'}">{inv['status']}</span>
                </div>
                <p style="margin: 4px 0 8px 0; color: #94A3B8;">Vendor: <b>{inv['vendor_name']}</b> (ID: {inv.get('vendor_id') or 'N/A'})</p>
                <p style="margin: 0 0 8px 0;">Referenced PO: <b>{inv.get('po_number') or 'None'}</b> | Terms: <b>{inv.get('payment_terms') or 'Net 30'}</b></p>
                <p style="margin: 0;">Total Due: <span style="font-size: 22px; font-weight: 700; color: #34D399;">${float(inv['total_amount']):,.2f}</span> {inv.get('currency', 'USD')}</p>
                {'<div style="margin-top: 8px; color: #FBBF24; font-size: 11px; font-weight: 600;">⚠️ HIGH-VALUE INVOICE: Greater than $10,000 threshold. Secondary confirmation mandatory.</div>' if is_high_value else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Tabbed Inspection: Exceptions vs Line Items vs Audit History
        t_exc, t_items, t_history = st.tabs(["1. Flagged Exceptions", "2. Line Items", "3. Decision History"])

        with t_exc:
            if exceptions:
                for exc in exceptions:
                    sev = exc["severity"]
                    sev_color = "#F87171" if sev in ["CRITICAL", "HIGH"] else "#FBBF24"
                    st.markdown(
                        f"""
                        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid {sev_color}; border-radius: 8px; padding: 10px; margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: {sev_color}; font-weight: 700; font-size: 11px;">[{sev}] {exc['exception_type']}</span>
                                <span style="color: #94A3B8; font-size: 11px;">Status: {exc['status']}</span>
                            </div>
                            <div style="color: #F8FAFC; font-size: 12px; margin: 4px 0;">{exc['description']}</div>
                            <div style="color: #38BDF8; font-size: 11px;"><b>AI Summary:</b> {exc.get('ai_summary') or 'N/A'}</div>
                            <div style="color: #34D399; font-size: 11px;"><b>Recommended:</b> {exc.get('recommended_action') or 'N/A'}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.success("🎉 No active exceptions. Clean 3-way match verified.")

        with t_items:
            if line_items:
                st.dataframe(pd.DataFrame(line_items)[["item_description", "quantity", "unit_price", "total_price"]], use_container_width=True, hide_index=True)
            else:
                st.caption("No line items itemized.")

        with t_history:
            if approval_history:
                st.dataframe(pd.DataFrame(approval_history)[["decision", "decision_by", "comments", "payment_status", "created_at"]], use_container_width=True, hide_index=True)
            else:
                st.caption("No prior approval actions on this invoice.")

    with c_right:
        st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
        st.markdown("###### ✍️ Human Decision & Sign-off Action")

        # Action Selector
        decision_action = st.radio(
            "Select Human Decision:",
            ["APPROVE", "REJECT", "REQUEST_CORRECTION"],
            index=0,
            horizontal=True,
            key="approval_action_radio",
        )

        approval_comments = st.text_input("Reviewer Notes / Voucher Remarks:", value="Verified 3-way match, cleared for release.", key="review_notes_input")

        # Dynamic inputs based on decision
        if decision_action == "APPROVE":
            payment_rail = st.selectbox("Simulated Disbursement Rail:", ["ACH Corporate Credit", "Fedwire High-Value", "Single-Use Virtual Card"], key="disburse_rail_select")

            high_value_check = False
            if is_high_value:
                high_value_check = st.checkbox("✅ High-Value Confirmation: I confirm this payment exceeds $10,000 and is authorized.", value=False, key="high_val_chk")

            st.caption("🔒 Backend guardrail: Approval will fail if any unresolved CRITICAL exceptions exist.")
            submit_btn = st.button("🚀 Authorize & Disburse Payment", type="primary", use_container_width=True, key="exec_approve_btn")

            if submit_btn:
                try:
                    res = service.process_approval_decision(
                        invoice_id=chosen_id,
                        action="APPROVE",
                        reviewer_name=reviewer_name,
                        comments=approval_comments,
                        payment_method=payment_rail,
                        high_value_confirmed=high_value_check,
                    )
                    st.success(f"🎉 Payment Authorized! Disbursement Ref: **{res['simulated_payment_ref']}** via {payment_rail}.")
                    st.rerun()
                except ValueError as ve:
                    st.error(f"🛑 Security Guardrail: {str(ve)}")

        elif decision_action == "REJECT":
            rejection_reason = st.text_area("Mandatory Rejection Justification *", placeholder="e.g. Unverified offshore entity / duplicate invoice billing.", key="reject_reason_input")
            reject_btn = st.button("🛑 Permanently Reject & Void Invoice", use_container_width=True, key="exec_reject_btn")

            if reject_btn:
                try:
                    res = service.process_approval_decision(
                        invoice_id=chosen_id,
                        action="REJECT",
                        reviewer_name=reviewer_name,
                        comments=approval_comments,
                        rejection_reason=rejection_reason,
                    )
                    st.error(f"Invoice #{inv['invoice_number']} permanently rejected and voided from disbursement.")
                    st.rerun()
                except ValueError as ve:
                    st.error(f"🛑 Security Guardrail: {str(ve)}")

        elif decision_action == "REQUEST_CORRECTION":
            correction_reason = st.text_area("Correction / Missing Information Request *", placeholder="e.g. Please provide revised invoice reflecting contracted discount or attach proof of delivery.", key="correction_reason_input")
            correct_btn = st.button("📤 Send Correction Request to Vendor", use_container_width=True, key="exec_correct_btn")

            if correct_btn:
                try:
                    res = service.process_approval_decision(
                        invoice_id=chosen_id,
                        action="REQUEST_CORRECTION",
                        reviewer_name=reviewer_name,
                        comments=approval_comments,
                        correction_reason=correction_reason,
                    )
                    st.warning(f"Invoice #{inv['invoice_number']} moved to 'CORRECTION_REQUESTED' status.")
                    st.rerun()
                except ValueError as ve:
                    st.error(f"🛑 Security Guardrail: {str(ve)}")

        st.markdown('</div>', unsafe_allow_html=True)
