"""
Invoice Intake & Document Processing View
Supports drag-and-drop PDF upload, one-click pre-loaded sample tests, PDF rendering,
and real-time 5-agent pipeline execution with live Agent Activity Monitor.
"""

import os
import streamlit as st
import pandas as pd
from ui.components import render_pdf_preview
from services.orchestrator import Orchestrator
from services.pdf_service import generate_all_sample_invoices


def render_intake_view(db_path: str = None, api_key: str = None, model: str = None, mock_mode: bool = True):
    st.markdown("### 📥 Autonomous Multi-Agent Invoice Orchestration")
    st.caption("Coordinates 5 specialized AI agents: Intake -> Verification -> Financial Intelligence -> Workflow -> Reporting.")

    orchestrator = Orchestrator(db_path=db_path, api_key=api_key, model=model, mock_mode=mock_mode)

    col_up, col_preview = st.columns([1.1, 0.9])

    with col_up:
        st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
        st.markdown("##### 1. Upload Invoice Document (PDF)")
        uploaded_file = st.file_uploader(
            "Drag & drop invoice PDF",
            type=["pdf"],
            help="Supports standard enterprise invoices with line items and PO references."
        )

        st.markdown("---")
        st.markdown("##### 💡 Or Select Pre-configured Test Invoice Scenario")
        sample_dir = "sample_data"
        generate_all_sample_invoices(sample_dir)
        samples = {
            "Select a sample scenario...": None,
            "1. Clean Valid Invoice (Apex Cloud -> PO-2026-001) [PASS]": os.path.join(sample_dir, "invoice_valid_apex.pdf"),
            "2. Amount Variance / PO Mismatch (Global Logistics -> PO-2026-002) [OVERBILLED]": os.path.join(sample_dir, "invoice_mismatch_logistics.pdf"),
            "3. Tax Math Discrepancy (CyberShield Security) [MATH_ANOMALY]": os.path.join(sample_dir, "invoice_tax_error_cybershield.pdf"),
            "4. Unknown Suspicious Entity (Offshore Shell Corp) [BLOCKED]": os.path.join(sample_dir, "invoice_unknown_shell.pdf"),
        }
        selected_sample = st.selectbox("Load Sample Document:", list(samples.keys()))

        allow_reprocessing = st.checkbox("Allow Reprocessing (Force process even if previously ingested)", value=False)

        pdf_bytes = None
        doc_name = None

        if uploaded_file is not None:
            pdf_bytes = uploaded_file.read()
            doc_name = uploaded_file.name
        elif selected_sample and samples[selected_sample]:
            file_path = samples[selected_sample]
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()
            doc_name = os.path.basename(file_path)

        run_btn = st.button("🚀 Ingest & Run Autonomous AP Pipeline", type="primary", disabled=(pdf_bytes is None))
        st.markdown('</div>', unsafe_allow_html=True)

    with col_preview:
        st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
        st.markdown("##### 📄 PDF Document Visualizer (PyMuPDF)")
        if pdf_bytes:
            render_pdf_preview(pdf_bytes)
        else:
            st.info("Upload or select a PDF to preview document.")
        st.markdown('</div>', unsafe_allow_html=True)

    # Multi-Agent Execution section
    if run_btn and pdf_bytes:
        with st.spinner("🤖 Autonomous Orchestrator executing 5-agent sequence: Intake -> Verification -> Fin Intel -> Workflow -> Reporting..."):
            ctx = orchestrator.process_invoice_document(pdf_bytes, doc_name, allow_reprocessing=allow_reprocessing)
            st.session_state["latest_orchestration_context"] = ctx

    # Display Active Context Results
    if "latest_orchestration_context" in st.session_state:
        ctx = st.session_state["latest_orchestration_context"]

        st.markdown("---")
        st.markdown("### 🤖 Multi-Agent Orchestration Activity & Context")

        # Top Pipeline Status Banner
        status = ctx.workflow_status
        status_color = "#34D399" if status == "COMPLETED" else ("#FBBF24" if status == "NEEDS_REVIEW" else "#F87171")
        badge_class = "badge-approved" if status == "COMPLETED" else ("badge-pending" if status == "NEEDS_REVIEW" else "badge-exception")

        st.markdown(
            f"""
            <div class="glass-panel" style="border-left: 4px solid {status_color};">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h4 style="margin: 0; color: #F8FAFC;">Run ID: <code style="color: #38BDF8;">{ctx.run_id}</code></h4>
                        <p style="color: #94A3B8; margin: 4px 0 0 0; font-size: 13px;">Document: <b>{ctx.file_name}</b> | Invoice #: <b>{ctx.invoice_number or 'N/A'}</b> | Stage: <b>{ctx.current_stage}</b></p>
                    </div>
                    <div>
                        <span class="badge {badge_class}" style="font-size: 13px;">{status}</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 5-Agent Execution Timeline Grid
        st.markdown("##### ⏱️ Agent Execution Trace & Latency Breakdown")
        col_agents = st.columns(len(ctx.agent_execution_history) if ctx.agent_execution_history else 1)

        for idx, step in enumerate(ctx.agent_execution_history):
            with col_agents[idx]:
                step_color = "#34D399" if step.status == "COMPLETED" else ("#FBBF24" if step.status == "NEEDS_REVIEW" else "#F87171")
                st.markdown(
                    f"""
                    <div class="agent-feed-card" style="border-top: 3px solid {step_color}; min-height: 120px;">
                        <div style="font-weight: 700; color: #F8FAFC; margin-bottom: 4px;">{step.agent_name}</div>
                        <div style="color: {step_color}; font-size: 11px; font-weight: 600;">{step.status}</div>
                        <div style="color: #64748B; font-size: 10px; margin-top: 4px;">⚡ {step.duration_ms:.1f} ms</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Detailed Tabs for Agent Outputs
        t1, t2, t3, t4, t5 = st.tabs([
            "1. Intake Extraction",
            "2. Vendor & PO Verification",
            "3. Financial Intelligence",
            "4. Exceptions & Routing",
            "5. Consolidated Audit Report"
        ])

        with t1:
            if ctx.invoice_data:
                data = ctx.invoice_data
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Invoice #", data.get("invoice_number", "N/A"))
                c2.metric("Vendor", data.get("vendor_name", "N/A"))
                c3.metric("Total Amount", f"${float(data.get('total_amount', 0)):,.2f}")
                c4.metric("Extraction Status", ctx.extraction_status)

                items = data.get("line_items", [])
                if items:
                    st.markdown("###### Itemized Line Items")
                    st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
            elif ctx.error_detail:
                st.error(f"Intake extraction failed: {ctx.error_detail}")
            else:
                st.info("Extraction pending.")

        with t2:
            if ctx.verification_results:
                ver = ctx.verification_results
                col_v1, col_v2 = st.columns(2)
                with col_v1:
                    st.write(f"**Vendor Verified:** {'✅ Yes' if ver.get('vendor_verified') else '❌ No'}")
                    st.write(f"**Vendor Status:** `{ver.get('vendor_status')}`")
                    st.write(f"**Matched Vendor ID:** `{ver.get('vendor_id') or 'N/A'}`")
                with col_v2:
                    st.write(f"**PO Matched:** {'✅ Matched' if ver.get('po_matched') else '⚠️ Unmatched / Missing'}")
                    st.write(f"**PO Number:** `{ver.get('po_number') or 'N/A'}`")
                    po_tot = ver.get("po_total")
                    st.write(f"**PO Authorized Total:** `{f'${po_tot:,.2f}' if po_tot else 'N/A'}`")

                if ver.get("reasons"):
                    st.markdown("###### Verification Findings")
                    for r in ver["reasons"]:
                        st.caption(f"• {r}")
            else:
                st.info("Verification step was not reached.")

        with t3:
            if ctx.financial_risk_results:
                fi = ctx.financial_risk_results
                r_score = fi.get("risk_score", 0.0)
                st.metric("Risk Score", f"{r_score * 100:.0f}%", delta="Normal" if r_score < 0.4 else "High Risk", delta_color="inverse")
                st.write(f"**Duplicate Invoice:** {'🚨 YES' if fi.get('is_duplicate') else '✅ NO'}")
                st.write(f"**Math / Tax Anomaly:** {'⚠️ YES' if (fi.get('tax_error') or fi.get('math_error')) else '✅ CLEAN'}")
                if fi.get("anomaly_flags"):
                    st.warning("Flagged Financial Anomalies:")
                    for fl in fi["anomaly_flags"]:
                        st.write(f"- {fl}")
            else:
                st.info("Financial intelligence analysis was not reached.")

        with t4:
            if ctx.exceptions:
                st.error(f"{len(ctx.exceptions)} Policy Exception(s) Registered:")
                for exc in ctx.exceptions:
                    st.markdown(f"• **{exc}**")
            else:
                st.success("🎉 No exceptions detected! Invoice eligible for straight-through approval.")

        with t5:
            st.markdown("##### 📜 Orchestrator Run Execution Log")
            log_entries = []
            for s in ctx.agent_execution_history:
                log_entries.append({
                    "Agent": s.agent_name,
                    "Stage": s.stage,
                    "Status": s.status,
                    "Latency (ms)": s.duration_ms,
                    "Summary": s.summary,
                    "Error": s.error_message or "None",
                })
            st.dataframe(pd.DataFrame(log_entries), use_container_width=True, hide_index=True)

    # 6. Recent Orchestrator Runs Table
    st.markdown("---")
    st.markdown("##### 🔄 Recent Orchestrator Execution History")
    recent_runs = orchestrator.get_recent_runs(limit=6)
    if recent_runs:
        st.dataframe(pd.DataFrame(recent_runs), use_container_width=True, hide_index=True)
    else:
        st.caption("No orchestrator runs recorded yet.")
