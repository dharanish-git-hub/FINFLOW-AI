"""
Reusable UI Components for FinFlow AI.
"""

import streamlit as st
import fitz  # PyMuPDF
from ui.styles import get_status_badge_html


def render_header(mock_mode: bool = True, model_name: str = "gemini-3.5-flash", connection_status: str = "OFFLINE"):
    badge_class = "badge-pending" if mock_mode else "badge-approved"
    if connection_status == "CONNECTED":
        status_text = f"GEMINI ONLINE ({model_name})"
        badge_class = "badge-approved"
    elif connection_status == "DEMO":
        status_text = "DEMO / MOCK MODE"
        badge_class = "badge-pending"
    elif connection_status == "ERROR":
        status_text = "GEMINI ERROR (FALLBACK ACTIVE)"
        badge_class = "badge-exception"
    else:
        status_text = "MOCK AI ENGINE (OFFLINE READY)" if mock_mode else f"GEMINI ({model_name})"

    st.markdown(
        f"""
        <div class="finflow-header">
            <div>
                <h1 class="finflow-title">⚡ FINFLOW AI</h1>
                <p class="finflow-subtitle">Autonomous Accounts Payable & Enterprise Finance Operations</p>
            </div>
            <div>
                <span class="badge {badge_class}">
                    {status_text}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_cards(metrics: dict):
    st.markdown(
        f"""
        <div class="kpi-container">
            <div class="kpi-card">
                <div class="kpi-title">Total Invoices</div>
                <div class="kpi-value">{metrics.get('total_invoices', 0)}</div>
                <div class="kpi-subtitle">Ingested through Intake Agent</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Awaiting Approval</div>
                <div class="kpi-value" style="color: #FBBF24;">{metrics.get('pending_approval', 0)}</div>
                <div class="kpi-subtitle">Passed 3-way verification</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Active Exceptions</div>
                <div class="kpi-value" style="color: #F87171;">{metrics.get('exceptions', 0)}</div>
                <div class="kpi-subtitle">Flagged by Financial Intel</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Disbursed Volume</div>
                <div class="kpi-value" style="color: #34D399;">${metrics.get('paid_volume', 0.0):,.2f}</div>
                <div class="kpi-subtitle">Prepared & settled payments</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pdf_preview(pdf_bytes: bytes, page_number: int = 0):
    """Renders a PDF page to an image using PyMuPDF and displays it in Streamlit."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) > page_number:
            page = doc[page_number]
            pix = page.get_pixmap(dpi=150)
            img_data = pix.tobytes("png")
            st.image(img_data, caption=f"Page {page_number + 1} of {len(doc)}", use_container_width=True)
        doc.close()
    except Exception as e:
        st.warning(f"Could not render PDF preview: {e}")
