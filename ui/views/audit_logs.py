"""
Audit Logs UI View (Task 09)
Dedicated SOX-compliant immutable audit log browser and investigation tool.
Features:
- Chronological retrieval of all system, agent, and human events
- Full-text search by action, message, actor, or invoice ID
- Category, level (severity), and date range filtering
- Color-coded badges for SUCCESS, INFO, WARNING, ERROR
- Detailed JSON payload inspection drawer/modal
- CSV download preserving original event details
"""

import json
import streamlit as st
import pandas as pd
from datetime import datetime
from services.audit_analytics_service import AuditAnalyticsService
from ui.styles import get_status_badge_html


def render_audit_logs_view(db_path: str = None):
    """Renders the dedicated Audit Logs Explorer."""
    st.markdown("### 📜 Immutable System & AP Audit Trail")
    st.caption("Chronological, tamper-evident record of all intake, verification, approval, payment, and exception events.")

    audit_service = AuditAnalyticsService(db_path=db_path)

    # 1. Filters & Search Bar
    with st.expander("🔍 Search & Filter Audit Logs", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1, 1, 1])

        with f_col1:
            search_query = st.text_input(
                "Search logs (action, operator, keyword, or invoice #):",
                placeholder="e.g. INVOICE_EXTRACTED, CFO_Jane, PAY-...",
            )

        with f_col2:
            category_filter = st.selectbox(
                "Category:",
                ["ALL", "INTAKE", "VERIFICATION", "WORKFLOW", "EXCEPTION", "APPROVAL", "PAYMENT", "SYSTEM"],
                index=0,
            )

        with f_col3:
            level_filter = st.selectbox(
                "Severity / Level:",
                ["ALL", "INFO", "SUCCESS", "WARNING", "ERROR"],
                index=0,
            )

        with f_col4:
            limit_records = st.selectbox(
                "Max Records:",
                [50, 100, 250, 500],
                index=1,
            )

    # 2. Fetch Audit Logs
    logs = audit_service.get_audit_logs(
        search_query=search_query,
        category=category_filter,
        level=level_filter,
        limit=limit_records,
    )

    # Export Button & Summary Bar
    c_sum, c_btn = st.columns([3, 1])
    with c_sum:
        st.markdown(f"**Displaying {len(logs)} audit record(s)** in reverse chronological order.")
    with c_btn:
        csv_data = audit_service.generate_audit_logs_csv(
            category=category_filter,
            level=level_filter,
            search_query=search_query,
        )
        st.download_button(
            label="📥 Export Filtered Audit CSV",
            data=csv_data.encode("utf-8"),
            file_name=f"finflow_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    if not logs:
        st.info("No audit records matching your current filter criteria.")
        return

    # 3. Formatted Table View
    table_rows = []
    for log in logs:
        # Style badge color
        lvl = log["level"].upper()
        if lvl == "SUCCESS":
            lvl_display = "🟢 SUCCESS"
        elif lvl == "ERROR":
            lvl_display = "🔴 ERROR"
        elif lvl == "WARNING":
            lvl_display = "🟡 WARNING"
        else:
            lvl_display = "🔵 INFO"

        table_rows.append(
            {
                "ID": log["id"],
                "Timestamp": log["timestamp"][:19].replace("T", " ") if log["timestamp"] else "N/A",
                "Level": lvl_display,
                "Category": log["category"] or "SYSTEM",
                "Action": log["action"],
                "Actor / Agent": log["actor"] or log["agent_name"],
                "Invoice": f"#{log['invoice_number']}" if log.get("invoice_number") else (f"ID: {log['invoice_id']}" if log.get("invoice_id") else "-"),
                "Prev Status": log["previous_status"] or "-",
                "New Status": log["new_status"] or "-",
                "Message": log["message"],
            }
        )

    df_display = pd.DataFrame(table_rows)
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # 4. Detailed Event Inspector Drawer
    st.markdown("---")
    st.markdown("##### 🔬 Audit Event Deep Inspector")
    log_map = {f"#{l['id']} — [{l['level']}] {l['action']} ({l['timestamp'][:19].replace('T', ' ') if l['timestamp'] else ''})": l for l in logs}
    selected_log_label = st.selectbox("Select an event to inspect full metadata & payload:", list(log_map.keys()))

    if selected_log_label:
        sel = log_map[selected_log_label]
        col_meta, col_payload = st.columns([1, 1.2])

        with col_meta:
            st.markdown(
                f"""
                <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 14px; font-size: 0.88rem;">
                    <div style="font-weight: 700; color: #f8fafc; margin-bottom: 8px;">Audit Metadata (Event #{sel['id']})</div>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr><td style="color: #94a3b8; padding: 3px 0;">Timestamp:</td><td style="color: #cbd5e1;">{sel['timestamp']}</td></tr>
                        <tr><td style="color: #94a3b8; padding: 3px 0;">Category:</td><td style="color: #38bdf8; font-weight: 600;">{sel['category']}</td></tr>
                        <tr><td style="color: #94a3b8; padding: 3px 0;">Action:</td><td style="color: #f8fafc; font-weight: 600;">{sel['action']}</td></tr>
                        <tr><td style="color: #94a3b8; padding: 3px 0;">Actor / Signatory:</td><td style="color: #cbd5e1;">{sel['actor']}</td></tr>
                        <tr><td style="color: #94a3b8; padding: 3px 0;">Agent Subsystem:</td><td style="color: #cbd5e1;">{sel['agent_name']}</td></tr>
                        <tr><td style="color: #94a3b8; padding: 3px 0;">Invoice ID:</td><td style="color: #cbd5e1;">{sel['invoice_id'] or 'N/A'}</td></tr>
                        <tr><td style="color: #94a3b8; padding: 3px 0;">Status Transition:</td><td style="color: #facc15;">{sel['previous_status'] or 'None'} &rarr; {sel['new_status'] or 'None'}</td></tr>
                    </table>
                    <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); color: #e2e8f0;">
                        <b>Log Message:</b><br/>{sel['message']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_payload:
            st.markdown(
                """
                <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 14px;">
                    <div style="font-weight: 700; color: #f8fafc; margin-bottom: 8px;">Event Payload (JSON)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            payload_str = sel.get("payload_json") or "{}"
            try:
                parsed_json = json.loads(payload_str)
                st.json(parsed_json)
            except Exception:
                st.code(payload_str, language="json")
