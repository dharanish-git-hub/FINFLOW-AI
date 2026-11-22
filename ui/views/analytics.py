"""
Financial Analytics & Compliance Reporting View (Task 09)
Provides real-time interactive business intelligence dashboards and exportable financial reports:
- Executive KPIs derived directly from SQLite database queries (never hardcoded)
- Plotly visual charts:
  1. Monthly invoice value vs settled payments
  2. Invoice status distribution
  3. Payment success vs failure ratio
  4. Exception severity distribution
  5. Top vendors by total billed amount
- Report generation & download center:
  - Invoice Summary Report (CSV)
  - Payment Transactions Report (CSV)
  - Exception Management Report (CSV)
  - Full SOX Audit Trail (CSV)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from services.audit_analytics_service import AuditAnalyticsService


def render_analytics_view(db_path: str = None):
    st.markdown("### 📈 Financial Analytics & Intelligence Suite")
    st.caption("Real-time accounts payable metrics, liquidity tracking, risk distributions, and compliance reporting.")

    service = AuditAnalyticsService(db_path=db_path)
    analytics = service.get_financial_analytics()
    kpis = analytics["kpis"]

    # 1. Executive KPI Summary Cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">TOTAL INVOICES PROCESSED</div>
                <div class="kpi-value" style="color: #60a5fa;">{kpis["total_invoices"]}</div>
                <div class="kpi-subtitle">Total Value: ${kpis["total_invoice_value"]:,.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">SETTLED PAYMENTS</div>
                <div class="kpi-value" style="color: #34d399;">{kpis["total_executed_payments"]}</div>
                <div class="kpi-subtitle">Settled: ${kpis["total_settled_value"]:,.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">PENDING APPROVALS</div>
                <div class="kpi-value" style="color: #facc15;">{kpis["pending_approvals"]}</div>
                <div class="kpi-subtitle">Awaiting Sign-Off</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">OPEN EXCEPTIONS / FAILED</div>
                <div class="kpi-value" style="color: #f87171;">{kpis["open_exceptions"]} / {kpis["failed_payments"]}</div>
                <div class="kpi-subtitle">Exceptions / Failed Txns</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # 2. Interactive Charts Section
    row1_c1, row1_c2 = st.columns(2)

    with row1_c1:
        st.markdown("##### 🏢 Top Vendors by Invoice Value")
        top_v = analytics["top_vendors"]
        if top_v:
            df_v = pd.DataFrame(top_v)
            fig_v = px.bar(
                df_v,
                x="vendor_name",
                y="total_value",
                text="total_value",
                labels={"vendor_name": "Vendor", "total_value": "Total Billed ($)"},
                color="total_value",
                color_continuous_scale="Blues",
            )
            fig_v.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
            fig_v.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94A3B8"),
                margin=dict(l=20, r=20, t=20, b=20),
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig_v, use_container_width=True)
        else:
            st.info("No vendor invoice data available yet.")

    with row1_c2:
        st.markdown("##### 📊 Invoice Status Distribution")
        stat_dist = analytics["status_distribution"]
        if stat_dist:
            df_stat = pd.DataFrame(stat_dist)
            fig_stat = px.pie(
                df_stat,
                names="status",
                values="count",
                hole=0.45,
                color_discrete_sequence=["#38BDF8", "#34D399", "#FBBF24", "#F87171", "#C084FC", "#94A3B8"],
            )
            fig_stat.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94A3B8"),
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig_stat, use_container_width=True)
        else:
            st.info("No invoice records found.")

    row2_c1, row2_c2 = st.columns(2)

    with row2_c1:
        st.markdown("##### 🚨 Exception Severity Distribution")
        sev_dist = analytics["severity_distribution"]
        if sev_dist:
            df_sev = pd.DataFrame(sev_dist)
            fig_sev = px.pie(
                df_sev,
                names="severity",
                values="count",
                hole=0.45,
                color="severity",
                color_discrete_map={
                    "CRITICAL": "#EF4444",
                    "HIGH": "#F97316",
                    "MEDIUM": "#FBBF24",
                    "LOW": "#38BDF8",
                },
            )
            fig_sev.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94A3B8"),
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig_sev, use_container_width=True)
        else:
            st.info("No exceptions detected.")

    with row2_c2:
        st.markdown("##### 💳 Payment Success vs Failure")
        pay_dist = analytics["payment_distribution"]
        if pay_dist:
            df_pay = pd.DataFrame(pay_dist)
            fig_pay = px.bar(
                df_pay,
                x="status",
                y="count",
                color="status",
                labels={"status": "Transaction Status", "count": "Transactions"},
                color_discrete_map={"EXECUTED": "#34D399", "FAILED": "#EF4444", "PREPARED": "#FBBF24"},
            )
            fig_pay.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94A3B8"),
                margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False,
            )
            st.plotly_chart(fig_pay, use_container_width=True)
        else:
            st.info("No simulated payment transactions recorded yet.")

    # 3. Monthly Spend & Settlement Trends (if data available)
    if analytics["monthly_invoices"] or analytics["monthly_payments"]:
        st.markdown("##### 📅 Monthly Invoiced vs Settled Volume")
        df_inv_m = pd.DataFrame(analytics["monthly_invoices"]) if analytics["monthly_invoices"] else pd.DataFrame(columns=["month", "total_value"])
        df_pay_m = pd.DataFrame(analytics["monthly_payments"]) if analytics["monthly_payments"] else pd.DataFrame(columns=["month", "settled_value"])

        if not df_inv_m.empty:
            df_inv_m["Type"] = "Invoiced Amount"
            df_inv_m.rename(columns={"total_value": "Amount"}, inplace=True)
        if not df_pay_m.empty:
            df_pay_m["Type"] = "Settled Amount"
            df_pay_m.rename(columns={"settled_value": "Amount"}, inplace=True)

        combined_monthly = pd.concat([df_inv_m[["month", "Amount", "Type"]], df_pay_m[["month", "Amount", "Type"]]])
        if not combined_monthly.empty:
            fig_monthly = px.bar(
                combined_monthly,
                x="month",
                y="Amount",
                color="Type",
                barmode="group",
                color_discrete_map={"Invoiced Amount": "#38BDF8", "Settled Amount": "#34D399"},
                labels={"month": "Month (YYYY-MM)", "Amount": "USD ($)"},
            )
            fig_monthly.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94A3B8"),
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig_monthly, use_container_width=True)

    # 4. Report Generation & Export Center
    st.markdown("---")
    st.markdown("##### 📥 Compliance & Financial Report Generation Center")
    st.caption("Export authoritative, unmanipulated corporate finance records in standard CSV format.")

    r_col1, r_col2, r_col3, r_col4 = st.columns(4)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    with r_col1:
        st.markdown(
            """
            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 12px; height: 130px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="font-weight: 600; color: #f8fafc; font-size: 0.9rem;">Invoice Summary</div>
                    <div style="color: #94a3b8; font-size: 0.78rem;">All extracted AP invoices, vendors, amounts, and statuses.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        inv_csv = service.generate_invoice_summary_csv()
        st.download_button(
            label="📄 Download Invoices CSV",
            data=inv_csv.encode("utf-8"),
            file_name=f"finflow_invoices_{timestamp_str}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with r_col2:
        st.markdown(
            """
            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 12px; height: 130px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="font-weight: 600; color: #f8fafc; font-size: 0.9rem;">Disbursement Report</div>
                    <div style="color: #94a3b8; font-size: 0.78rem;">Simulated payments, rail details, refs, and failures.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        pay_csv = service.generate_payment_transactions_csv()
        st.download_button(
            label="💳 Download Payments CSV",
            data=pay_csv.encode("utf-8"),
            file_name=f"finflow_payments_{timestamp_str}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with r_col3:
        st.markdown(
            """
            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 12px; height: 130px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="font-weight: 600; color: #f8fafc; font-size: 0.9rem;">Exceptions & Risk</div>
                    <div style="color: #94a3b8; font-size: 0.78rem;">Policy exceptions, severities, and auditor resolutions.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        exc_csv = service.generate_exceptions_csv()
        st.download_button(
            label="🚨 Download Exceptions CSV",
            data=exc_csv.encode("utf-8"),
            file_name=f"finflow_exceptions_{timestamp_str}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with r_col4:
        st.markdown(
            """
            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 12px; height: 130px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="font-weight: 600; color: #f8fafc; font-size: 0.9rem;">SOX Audit Log</div>
                    <div style="color: #94a3b8; font-size: 0.78rem;">Full event trail, state transitions, and actor identities.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        audit_csv = service.generate_audit_logs_csv()
        st.download_button(
            label="📜 Download Audit Logs CSV",
            data=audit_csv.encode("utf-8"),
            file_name=f"finflow_audit_trail_{timestamp_str}.csv",
            mime="text/csv",
            use_container_width=True,
        )
