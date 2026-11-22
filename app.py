"""
FINFLOW AI - Modern Autonomous Finance Operations Platform
Main Streamlit Application Entrypoint.
"""

import os
import streamlit as st
from dotenv import load_dotenv

# Load environment configuration
load_dotenv()

from database.db import init_db
from database.seed_data import seed_database
from agents.reporting_agent import ReportingAgent
from services.gemini_service import GeminiService, DEFAULT_GEMINI_MODEL
from ui.styles import NAVY_CSS
from ui.components import render_header, render_kpi_cards
from ui.views.overview import render_overview_view
from ui.views.invoice_intake import render_intake_view
from ui.views.invoice_processing import render_invoice_processing_view
from ui.views.exception_center import render_exception_center_view
from ui.views.approvals import render_approval_view
from ui.views.payment_management import render_payment_management_view
from ui.views.audit_logs import render_audit_logs_view
from ui.views.analytics import render_analytics_view

# Streamlit Page Config
st.set_page_config(
    page_title="FINFLOW AI | Autonomous AP Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply Dark Navy enterprise theme CSS
st.markdown(NAVY_CSS, unsafe_allow_html=True)

# Database Setup
DB_PATH = os.getenv("DB_PATH", "database/finflow.db")
init_db(DB_PATH)
seed_database(DB_PATH)

# Environment & Settings
api_key_env = os.getenv("GEMINI_API_KEY", "")
default_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
mock_mode_default = os.getenv("MOCK_MODE", "True").lower() == "true" or not bool(api_key_env)

# Sidebar Navigation & Settings
with st.sidebar:
    st.markdown("### ⚡ **FINFLOW AI**")
    st.caption("v1.0 • Autonomous AP Engine")
    st.markdown("---")

    nav_selection = st.radio(
        "Navigation Menu",
        [
            "📊 Executive Overview",
            "📄 Invoice Processing (AI)",
            "📥 Autonomous AP Pipeline",
            "⚠️ Exception Center",
            "✍️ Human Approval Gate",
            "💳 Payment Management",
            "📜 Audit Logs",
            "📈 Financial Analytics",
        ],
        index=0,
    )

    st.markdown("---")
    st.markdown("##### ⚙️ AI Engine Settings")
    
    mock_mode = st.toggle("Mock AI Mode (Offline)", value=mock_mode_default)

    # Configurable Gemini Model Selection
    AVAILABLE_MODELS = [
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-3.8-flash",
    ]
    model_index = AVAILABLE_MODELS.index(default_model) if default_model in AVAILABLE_MODELS else 0
    selected_model = st.selectbox(
        "Gemini Model:",
        options=AVAILABLE_MODELS,
        index=model_index,
        help="Select the Gemini model for invoice extraction and intelligence.",
    )
    
    user_api_key = st.text_input(
        "Gemini API Key:",
        value=api_key_env,
        type="password",
        help="Securely stored in session memory. Never logged or exposed.",
    )

    # Gemini Connection Status & Health Check
    st.markdown("##### 🔌 Gemini Status")
    gemini_service = GeminiService(api_key=user_api_key, model=selected_model)
    masked_key = gemini_service.get_masked_key()
    st.caption(f"**Key:** `{masked_key}` | **Model:** `{selected_model}`")

    if not gemini_service.has_api_key():
        st.info("ℹ️ No API key set. Running in Demo / Mock Mode.")
        connection_status_badge = "DEMO"
    elif mock_mode:
        st.info("ℹ️ Mock Mode toggled ON. Gemini calls bypassed.")
        connection_status_badge = "DEMO"
    else:
        connection_status_badge = "CONNECTED"

    # Test Connection Button
    if st.button("🔍 Test Gemini API Connection", use_container_width=True):
        with st.spinner("Pinging Google Gemini API..."):
            test_res = gemini_service.test_connection()
        if test_res["status"] == "SUCCESS":
            st.success(f"✅ {test_res['message']}\n\n*Response:* `{test_res['response']}`")
        elif test_res["status"] == "MISSING_KEY":
            st.warning(f"⚠️ {test_res['message']}")
        elif test_res["status"] == "INVALID_KEY":
            st.error(f"❌ {test_res['message']}")
        elif test_res["status"] == "QUOTA_EXHAUSTED":
            st.error(f"🛑 {test_res['message']}")
        elif test_res["status"] == "NETWORK_ERROR":
            st.error(f"🌐 {test_res['message']}")
        elif test_res["status"] == "MODEL_NOT_FOUND":
            st.warning(f"⚠️ {test_res['message']}")
        elif test_res["status"] == "SERVICE_UNAVAILABLE":
            st.warning(f"⏳ {test_res['message']}")
        else:
            st.error(f"❌ {test_res['message']}")

    st.markdown("---")
    st.markdown("##### 🛡️ Security Posture")
    st.markdown(
        """
        <div style="font-size: 11px; color: #94A3B8; line-height: 1.4;">
        • <b>Zero Autonomous Disbursement:</b> Payments require manual human credentials.<br/>
        • <b>API Key Security:</b> Key is read from .env / password input; never exposed.<br/>
        • <b>SOX Compliance:</b> Immutable SQLite audit trail on all agent decisions.
        </div>
        """,
        unsafe_allow_html=True,
    )

# Top Bar Header & Metrics
render_header(mock_mode=mock_mode, model_name=selected_model, connection_status=connection_status_badge)

reporting_agent = ReportingAgent(db_path=DB_PATH)
kpis = reporting_agent.get_kpi_summary()
render_kpi_cards(kpis)

# Route to active view
if nav_selection == "📊 Executive Overview":
    render_overview_view(db_path=DB_PATH)
elif nav_selection == "📄 Invoice Processing (AI)":
    render_invoice_processing_view(db_path=DB_PATH, api_key=user_api_key, model=selected_model, mock_mode=mock_mode)
elif nav_selection == "📥 Autonomous AP Pipeline":
    render_intake_view(db_path=DB_PATH, api_key=user_api_key, model=selected_model, mock_mode=mock_mode)
elif nav_selection == "⚠️ Exception Center":
    render_exception_center_view(db_path=DB_PATH, gemini_service=gemini_service)
elif nav_selection == "✍️ Human Approval Gate":
    render_approval_view(db_path=DB_PATH)
elif nav_selection == "💳 Payment Management":
    render_payment_management_view(db_path=DB_PATH)
elif nav_selection == "📜 Audit Logs":
    render_audit_logs_view(db_path=DB_PATH)
elif nav_selection == "📈 Financial Analytics":
    render_analytics_view(db_path=DB_PATH)
