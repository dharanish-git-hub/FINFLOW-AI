"""
FINFLOW AI Enterprise Dark Navy Theme Styles
Provides cohesive typography, badges, KPI cards, and modern financial aesthetic.
"""

NAVY_CSS = """
<style>
/* Import clean sans font */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Background gradient styling */
.stApp {
    background-color: #0B1120;
    color: #F8FAFC;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: #080D1A !important;
    border-right: 1px solid #1E293B;
}

/* Top Navbar / Header banner */
.finflow-header {
    background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 18px 24px;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);
}

.finflow-title {
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.5px;
    background: linear-gradient(90deg, #38BDF8 0%, #818CF8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
}

.finflow-subtitle {
    color: #94A3B8;
    font-size: 13px;
    font-weight: 400;
    margin: 3px 0 0 0;
}

/* Metric / KPI Cards */
.kpi-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}

.kpi-card {
    background: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 12px;
    padding: 16px 20px;
    transition: all 0.2s ease-in-out;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}

.kpi-card:hover {
    border-color: #38BDF8;
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(56, 189, 248, 0.15);
}

.kpi-title {
    color: #94A3B8;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 6px;
}

.kpi-value {
    color: #F8FAFC;
    font-size: 24px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 4px;
}

.kpi-subtitle {
    font-size: 11px;
    color: #64748B;
}

/* Badges */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 9999px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.badge-received { background-color: rgba(59, 130, 246, 0.15); color: #60A5FA; border: 1px solid #3B82F6; }
.badge-extracted { background-color: rgba(147, 51, 234, 0.15); color: #C084FC; border: 1px solid #9333EA; }
.badge-pending { background-color: rgba(245, 158, 11, 0.15); color: #FBBF24; border: 1px solid #F59E0B; }
.badge-approved { background-color: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid #10B981; }
.badge-paid { background-color: rgba(6, 182, 212, 0.15); color: #22D3EE; border: 1px solid #06B6D4; }
.badge-exception { background-color: rgba(239, 68, 68, 0.15); color: #F87171; border: 1px solid #EF4444; }
.badge-rejected { background-color: rgba(100, 116, 139, 0.15); color: #94A3B8; border: 1px solid #64748B; }

/* Agent Timeline / Terminal View */
.agent-feed-card {
    background: #090E17;
    border: 1px solid #1E293B;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
}
.agent-tag {
    font-weight: 600;
    color: #38BDF8;
    margin-right: 8px;
}
.agent-time {
    color: #64748B;
    font-size: 11px;
}

/* Glass panel */
.glass-panel {
    background: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
}
</style>
"""


def get_status_badge_html(status: str) -> str:
    status_upper = (status or "").upper()
    css_class = {
        "RECEIVED": "badge-received",
        "EXTRACTED": "badge-extracted",
        "PENDING_APPROVAL": "badge-pending",
        "APPROVED": "badge-approved",
        "PAID": "badge-paid",
        "EXCEPTION": "badge-exception",
        "REJECTED": "badge-rejected",
    }.get(status_upper, "badge-pending")

    return f'<span class="badge {css_class}">{status_upper}</span>'
