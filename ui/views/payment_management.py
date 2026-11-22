"""
Payment Management UI View (Task 08)
Provides interactive control for simulated invoice payment preparation and execution.
Enforces:
- Purely simulated transactions (no real money or external APIs)
- Human confirmation requirement (AI strictly prohibited)
- Pre-flight eligibility validation (Approved, zero critical exceptions, non-duplicate)
- Multiple payment rails (ACH Corporate Credit, Fedwire High-Value, Single-Use Virtual Card)
- Real-time simulation of successful and failed transaction flows
- Complete transaction history and audit trail
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from services.payment_service import PaymentService, PAYMENT_RAILS
from ui.styles import get_status_badge_html


def render_payment_management_view(db_path: str = None):
    """Renders the Payment Preparation and Simulation dashboard."""
    payment_service = PaymentService(db_path=db_path)

    st.markdown("### 💳 Payment Preparation & Simulation Engine")
    st.caption("Controlled, human-authorized simulated disbursement execution across supported payment rails.")

    # 1. Top Metrics Bar
    metrics = payment_service.get_payment_metrics()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">ELIGIBLE IN QUEUE</div>
                <div class="kpi-value" style="color: #60a5fa;">{metrics["pending_count"]}</div>
                <div class="kpi-subtitle">Vol: ${metrics["pending_volume"]:,.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">EXECUTED PAYMENTS</div>
                <div class="kpi-value" style="color: #34d399;">{metrics["executed_count"]}</div>
                <div class="kpi-subtitle">Vol: ${metrics["executed_volume"]:,.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">SIMULATED FAILURES</div>
                <div class="kpi-value" style="color: #f87171;">{metrics["failed_count"]}</div>
                <div class="kpi-subtitle">Requires Retry</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">TOTAL VOLUME SETTLED</div>
                <div class="kpi-value" style="color: #a78bfa;">${metrics["executed_volume"]:,.2f}</div>
                <div class="kpi-subtitle">Simulated Rails</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # Simulation Safety Banner
    st.info(
        "🛡️ **SIMULATION SANDBOX ACTIVE**: All transactions are simulated internally. "
        "No real financial institutions, banking APIs, or live currency transfers are involved. "
        "AI agents are architecturally prohibited from invoking disbursement."
    )

    # 2. Tabs: Payment Queue vs Transaction History
    tab_queue, tab_history = st.tabs(["💳 Payment Queue (Eligible Invoices)", "📜 Transaction History & Audit Trail"])

    with tab_queue:
        queue_invoices = payment_service.get_payment_queue(status_filter="ELIGIBLE")

        if not queue_invoices:
            st.success("🎉 All approved invoices have been processed! No pending payments in the queue.")
        else:
            st.markdown(f"#### Invoices Eligible for Disbursement ({len(queue_invoices)})")

            # Selection Box
            options = {
                f"#{inv['invoice_number']} — {inv['vendor_name']} (${inv['total_amount']:,.2f})": inv["id"]
                for inv in queue_invoices
            }
            selected_label = st.selectbox("Select Invoice to Prepare & Disburse:", list(options.keys()))
            selected_inv_id = options[selected_label]
            selected_invoice = next(inv for inv in queue_invoices if inv["id"] == selected_inv_id)

            # Verification Pre-Flight Check
            eligibility = payment_service.verify_payment_eligibility(selected_inv_id)

            col_detail, col_execute = st.columns([1.2, 1])

            with col_detail:
                st.markdown(
                    f"""
                    <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 16px;">
                        <h4 style="margin-top: 0; color: #f8fafc;">Invoice & Approval Details</h4>
                        <table style="width: 100%; border-collapse: collapse; font-size: 0.88rem;">
                            <tr><td style="color: #94a3b8; padding: 4px 0;">Invoice Number:</td><td style="font-weight: 600; color: #f8fafc;">#{selected_invoice['invoice_number']}</td></tr>
                            <tr><td style="color: #94a3b8; padding: 4px 0;">Vendor:</td><td style="font-weight: 600; color: #f8fafc;">{selected_invoice['vendor_name']}</td></tr>
                            <tr><td style="color: #94a3b8; padding: 4px 0;">Amount:</td><td style="font-weight: 700; color: #34d399; font-size: 1.1rem;">${selected_invoice['total_amount']:,.2f} {selected_invoice['currency']}</td></tr>
                            <tr><td style="color: #94a3b8; padding: 4px 0;">Approval Date:</td><td style="color: #cbd5e1;">{selected_invoice['approval_date']}</td></tr>
                            <tr><td style="color: #94a3b8; padding: 4px 0;">Approved By:</td><td style="color: #cbd5e1;">{selected_invoice['approved_by']}</td></tr>
                            <tr><td style="color: #94a3b8; padding: 4px 0;">Status:</td><td>{get_status_badge_html(selected_invoice['invoice_status'])}</td></tr>
                        </table>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if eligibility["eligible"]:
                    st.success("✅ **Pre-Flight Validation Passed**: Invoice is human-approved and clear of critical exceptions.")
                else:
                    st.error(f"❌ **Disbursement Blocked**: {eligibility['reason']}")

            with col_execute:
                st.markdown(
                    """
                    <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                        <h4 style="margin: 0; color: #f8fafc;">Execute Disbursement</h4>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.form(key=f"pay_form_{selected_inv_id}"):
                    payment_rail = st.selectbox(
                        "Select Payment Rail:",
                        [
                            "ACH Corporate Credit",
                            "Fedwire High-Value",
                            "Single-Use Virtual Card",
                        ],
                        index=0 if selected_invoice["total_amount"] < 10000 else 1,
                    )

                    operator_name = st.text_input("Disbursing Operator (Treasury User):", value="Finance_Officer")

                    st.markdown("##### Simulation Scenarios")
                    simulate_failure = st.checkbox("Simulate Processing Failure (Test Exception Handling)", value=False)
                    failure_reason = ""
                    if simulate_failure:
                        failure_reason = st.selectbox(
                            "Failure Reason to Simulate:",
                            [
                                "Invalid Bank Routing Transit Number",
                                "Simulated ACH Network Timeout",
                                "Simulated Card Processor Decline: Insufficient Sandbox Limit",
                                "OFAC Secondary Compliance Verification Hold",
                            ],
                        )

                    st.markdown("---")
                    human_confirm = st.checkbox(
                        f"I confirm disbursement of ${selected_invoice['total_amount']:,.2f} to {selected_invoice['vendor_name']} via {payment_rail}.",
                        value=False,
                    )

                    submit_pay = st.form_submit_button("🚀 Execute Simulated Payment", use_container_width=True)

                    if submit_pay:
                        if not human_confirm:
                            st.error("⚠️ Mandatory confirmation checkbox must be checked prior to executing disbursement.")
                        elif not operator_name.strip():
                            st.error("⚠️ Disbursing operator identity is required for the audit trail.")
                        elif not eligibility["eligible"]:
                            st.error(f"Disbursement blocked: {eligibility['reason']}")
                        else:
                            try:
                                result = payment_service.execute_simulated_payment(
                                    invoice_id=selected_inv_id,
                                    payment_rail=payment_rail,
                                    simulated_by=operator_name.strip(),
                                    simulate_failure=simulate_failure,
                                    failure_reason=failure_reason or "Simulated processing error",
                                )

                                if result["success"]:
                                    st.success(
                                        f"✅ **Payment Executed Successfully!**\n\n"
                                        f"- **Reference**: `{result['transaction_ref']}`\n"
                                        f"- **Rail**: {result['payment_rail']}\n"
                                        f"- **Settled At**: {result['settled_at']}\n"
                                        f"- **Invoice Status**: Marked as `PAID`."
                                    )
                                    st.rerun()
                                else:
                                    st.warning(
                                        f"⚠️ **Payment Failed (Simulated)**\n\n"
                                        f"- **Reference**: `{result['transaction_ref']}`\n"
                                        f"- **Reason**: {result['failure_reason']}\n"
                                        f"- **Invoice Status**: Remained `APPROVED` for retry."
                                    )
                                    st.rerun()

                            except Exception as e:
                                st.error(f"Execution Error: {str(e)}")

    with tab_history:
        st.markdown("#### Transaction Audit Trail")
        history = payment_service.get_transaction_history(limit=50)

        if not history:
            st.info("No payment transactions recorded yet.")
        else:
            table_data = []
            for item in history:
                table_data.append(
                    {
                        "Ref ID": item["transaction_ref"],
                        "Invoice #": f"#{item['invoice_number']}" if item["invoice_number"] else f"ID: {item['invoice_id']}",
                        "Vendor": item["vendor_name"],
                        "Amount": f"${item['amount']:,.2f} {item['currency']}",
                        "Payment Rail": item["payment_rail"],
                        "Status": item["status"],
                        "Failure Reason": item["failure_reason"] or "N/A",
                        "Operator": item["simulated_by"],
                        "Timestamp": item["settled_at"] or item["created_at"],
                    }
                )

            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
