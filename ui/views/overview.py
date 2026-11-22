"""
Overview & Command Center View
Displays enterprise AP KPI metrics, high-level workflow diagrams, and recent agent activity feed.
"""

import streamlit as st
import pandas as pd
from database.db import get_db_connection
from agents.reporting_agent import ReportingAgent
from ui.styles import get_status_badge_html


def render_overview_view(db_path: str = None):
    st.markdown("### 📊 Executive AP Operations Summary")

    reporting_agent = ReportingAgent(db_path=db_path)
    metrics = reporting_agent.get_kpi_summary()

    # 1. Pipeline Status Breakdown Cards
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status, COUNT(*) as count, COALESCE(SUM(total_amount), 0) as total_val 
        FROM invoices 
        GROUP BY status;
    """)
    status_rows = cursor.fetchall()

    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    st.markdown("##### 🔄 Autonomous Pipeline Velocity")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    status_map = {r["status"]: r for r in status_rows}

    with col1:
        c = status_map.get("EXTRACTED", {"count": 0, "total_val": 0})
        st.metric("1. Extracted", f"{c['count']}", f"${c['total_val']:,.0f}")
    with col2:
        c = status_map.get("EXCEPTION", {"count": 0, "total_val": 0})
        st.metric("2. Exceptions", f"{c['count']}", f"${c['total_val']:,.0f}", delta_color="inverse")
    with col3:
        c = status_map.get("PENDING_APPROVAL", {"count": 0, "total_val": 0})
        st.metric("3. Pending Sign-off", f"{c['count']}", f"${c['total_val']:,.0f}")
    with col4:
        c = status_map.get("APPROVED", {"count": 0, "total_val": 0})
        st.metric("4. Approved", f"{c['count']}", f"${c['total_val']:,.0f}")
    with col5:
        c = status_map.get("PAID", {"count": 0, "total_val": 0})
        st.metric("5. Disbursed", f"{c['count']}", f"${c['total_val']:,.0f}")

    st.markdown('</div>', unsafe_allow_html=True)

    # 2. Main content split: Invoices table vs Agent Live Log
    c_left, c_right = st.columns([1.5, 1])

    with c_left:
        st.markdown("##### 📑 Ingested Invoices Ledger")
        cursor.execute("""
            SELECT id, invoice_number, vendor_name, po_number, total_amount, currency, status, created_at 
            FROM invoices 
            ORDER BY id DESC LIMIT 10;
        """)
        inv_rows = [dict(r) for r in cursor.fetchall()]

        if inv_rows:
            df = pd.DataFrame(inv_rows)
            df["total_amount"] = df["total_amount"].apply(lambda v: f"${v:,.2f}")
            df.columns = ["ID", "Invoice #", "Vendor", "PO #", "Amount", "Curr", "Status", "Timestamp"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No invoices processed yet. Navigate to 'Invoice Intake' to upload documents.")

    with c_right:
        st.markdown("##### 🤖 Agent Activity Monitor (Immutable Trail)")
        logs = reporting_agent.get_recent_audit_logs(limit=8)
        if logs:
            for l in logs:
                agent = l["agent_name"]
                action = l["action"]
                level_color = "#34D399" if l["level"] == "SUCCESS" else ("#F87171" if l["level"] == "WARNING" else "#38BDF8")
                st.markdown(
                    f"""
                    <div class="agent-feed-card">
                        <div>
                            <span class="agent-tag">[{agent}]</span>
                            <span style="color: {level_color}; font-weight: 600;">{action}</span>
                            <span class="agent-time float-right">{l["timestamp"]}</span>
                        </div>
                        <div style="color: #CBD5E1; margin-top: 4px; font-size: 11px;">
                            {l["message"]}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No agent activity logs yet.")

    conn.close()
