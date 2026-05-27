"""
AgentLedger — Credit Analysis Dashboard

Demo mode: uses synthetic transactions (no Plaid required).
Each persona matches a scenario from evals/scenarios/.

Run:
    cd agentledger/
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import plotly.graph_objects as go

from agentledger.analysis.cash_flow import compute_metrics
from agentledger.schemas.models import CategorizedTransaction, WorkflowState
from agentledger.workflow.nodes import (
    analyze_node,
    hitl_check_node,
    ingest_node,
    profile_node,
    report_node,
    risk_assess_node,
    validate_node,
)

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AgentLedger — Credit Analysis",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────

st.markdown("""
<style>
#MainMenu, footer { visibility: hidden; }

.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* KPI cards */
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 18px 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    min-height: 96px;
}
.kpi-label {
    font-size: 11px; font-weight: 700; color: #64748b;
    text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 6px;
}
.kpi-value { font-size: 24px; font-weight: 700; color: #0f172a; line-height: 1.15; }
.kpi-signal { font-size: 12px; font-weight: 600; margin-top: 4px; }
.sig-ok   { color: #16a34a; }
.sig-warn { color: #d97706; }
.sig-bad  { color: #dc2626; }
.sig-neu  { color: #64748b; }

/* Hero decision banner */
.hero-banner {
    border-radius: 12px;
    padding: 22px 28px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 20px;
}
.hero-left { flex: 1; }
.hero-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px; opacity: 0.7; }
.hero-decision { font-size: 28px; font-weight: 800; letter-spacing: -0.5px; line-height: 1.15; }
.hero-summary { font-size: 13.5px; color: #334155; margin-top: 10px; line-height: 1.6; max-width: 560px; }
.hero-right { text-align: right; white-space: nowrap; }
.hero-score { font-size: 42px; font-weight: 800; line-height: 1; }
.hero-score-label { font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 2px; }
.hero-meta { font-size: 11.5px; color: #64748b; margin-top: 8px; line-height: 1.8; }

/* Section header */
.section-label {
    font-size: 11px; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #f1f5f9;
}

/* Factor cards */
.factor-card {
    background: #fafafa;
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 8px;
    border-left: 4px solid #e2e8f0;
}
.factor-card.high     { border-left-color: #dc2626; background: #fff5f5; }
.factor-card.medium   { border-left-color: #d97706; background: #fffbeb; }
.factor-card.low      { border-left-color: #16a34a; background: #f0fdf4; }
.factor-card.strength { border-left-color: #2563eb; background: #eff6ff; }

.sev-badge {
    display: inline-block; font-size: 9.5px; font-weight: 700;
    padding: 2px 7px; border-radius: 4px; color: white;
    margin-bottom: 5px; text-transform: uppercase; letter-spacing: 0.05em;
}
.badge-high     { background: #dc2626; }
.badge-medium   { background: #d97706; }
.badge-low      { background: #16a34a; }
.badge-strength { background: #2563eb; }

.factor-desc  { font-size: 13px; color: #1e293b; line-height: 1.5; }
.factor-cites { font-size: 11px; color: #94a3b8; margin-top: 5px; font-style: italic; }

/* Escalation */
.esc-box {
    background: #fef3c7; border: 1px solid #fbbf24; border-radius: 8px;
    padding: 12px 16px; font-size: 13px; color: #78350f; margin-bottom: 16px;
    line-height: 1.6;
}

/* Validity pills */
.pill-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.pill {
    background: #f1f5f9; border-radius: 20px;
    padding: 4px 12px; font-size: 12px; font-weight: 600; color: #475569;
}
.pill-green { background: #dcfce7; color: #166534; }
.pill-red   { background: #fee2e2; color: #991b1b; }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────

PERSONAS = {
    "Stable W-2 Employee": {
        "description": "Salaried employee, consistent income, no overdrafts",
        "monthly_income": 5500, "income_source": "W2", "rent": 1800, "nsf_count": 0,
    },
    "Gig / Freelance Worker": {
        "description": "Freelancer with moderate income variability, clean record",
        "monthly_income": 4200, "income_source": "gig", "rent": 1400, "nsf_count": 0,
    },
    "W-2 with NSF Event": {
        "description": "Stable salary but one overdraft event on record",
        "monthly_income": 5500, "income_source": "W2", "rent": 1600, "nsf_count": 1,
    },
    "High Rent Burden": {
        "description": "Rent consumes 60% of income — expenses exceed income monthly",
        "monthly_income": 4500, "income_source": "W2", "rent": 2700, "nsf_count": 0,
    },
    "High-Income Gig Worker": {
        "description": "Strong earning gig worker, low rent-to-income ratio",
        "monthly_income": 7500, "income_source": "gig", "rent": 1200, "nsf_count": 0,
    },
    "Gig Worker + NSF": {
        "description": "Volatile income compounded by one overdraft — dual risk signal",
        "monthly_income": 4500, "income_source": "gig", "rent": 1500, "nsf_count": 1,
    },
    "Very Tight Budget": {
        "description": "Low income, high fixed costs — negative monthly cash buffer",
        "monthly_income": 2800, "income_source": "W2", "rent": 1600, "nsf_count": 0,
    },
    "Borderline Gig": {
        "description": "Moderate gig income, moderate rent — genuine edge case",
        "monthly_income": 5000, "income_source": "gig", "rent": 1800, "nsf_count": 0,
    },
}

REC_META = {
    "approve":                 ("#16a34a", "#dcfce7", "Approve"),
    "approve_with_conditions": ("#d97706", "#fef9ee", "Approve with Conditions"),
    "decline":                 ("#dc2626", "#fff5f5", "Decline"),
    "manual_review":           ("#7c3aed", "#faf5ff", "Manual Review"),
}

CATEGORY_COLORS = {
    "income_salary":        "#16a34a",
    "income_freelance":     "#22c55e",
    "income_government":    "#4ade80",
    "income_other":         "#86efac",
    "rent_mortgage":        "#dc2626",
    "utilities":            "#f97316",
    "groceries":            "#eab308",
    "debt_payment":         "#ef4444",
    "subscription":         "#a855f7",
    "dining_entertainment": "#ec4899",
    "transportation":       "#06b6d4",
    "nsf_fee":              "#111827",
    "other":                "#94a3b8",
}

CATEGORY_LABELS = {
    "income_salary":        "Salary",
    "income_freelance":     "Freelance",
    "income_government":    "Gov Benefits",
    "income_other":         "Other Income",
    "rent_mortgage":        "Rent / Mortgage",
    "utilities":            "Utilities",
    "groceries":            "Groceries",
    "debt_payment":         "Debt Payment",
    "subscription":         "Subscriptions",
    "dining_entertainment": "Dining & Entertainment",
    "transportation":       "Transportation",
    "nsf_fee":              "NSF Fee",
    "other":                "Other",
}

# ── Cached demo assessments ────────────────────────────────────────────────────

from agentledger.schemas.models import RiskAssessment, RiskFactor

_DEMO_ASSESSMENTS: dict[str, RiskAssessment] = {
    "Stable W-2 Employee": RiskAssessment(
        risk_score=28, recommendation="approve", confidence=0.92,
        reasoning_summary="Borrower shows consistent salaried income with zero overdraft events and a manageable debt-to-income ratio. Cash buffer is positive across all 6 months reviewed.",
        risk_factors=[RiskFactor(severity="low", description="Rent-to-income ratio of 33% is slightly above the 30% guideline but within acceptable range.", citations=["tx:demo_0002"])],
        strengths=[
            RiskFactor(severity="low", description="Perfect income stability — zero coefficient of variation across 6 months of payroll deposits.", citations=["tx:demo_0001"]),
            RiskFactor(severity="low", description="No NSF or overdraft events on record.", citations=["tx:demo_0001"]),
        ],
    ),
    "Gig / Freelance Worker": RiskAssessment(
        risk_score=45, recommendation="approve_with_conditions", confidence=0.78,
        reasoning_summary="Freelance income shows moderate variability (CV ~0.28) but net cash flow remains positive each month. Recommend approval with quarterly income verification condition.",
        risk_factors=[RiskFactor(severity="medium", description="Income variability is elevated — monthly deposits range from $3,100 to $5,200.", citations=["tx:demo_0001"])],
        strengths=[RiskFactor(severity="low", description="No overdraft history despite income volatility.", citations=["tx:demo_0001"])],
    ),
    "W-2 with NSF Event": RiskAssessment(
        risk_score=52, recommendation="approve_with_conditions", confidence=0.74,
        reasoning_summary="Stable employment income is a positive signal, but the single NSF event requires explanation. Recommend approval contingent on borrower providing written explanation.",
        risk_factors=[RiskFactor(severity="medium", description="One NSF fee recorded in month 2 — indicates a cash flow gap.", citations=["tx:demo_nsf_01"])],
        strengths=[RiskFactor(severity="low", description="W-2 income is consistent across all 6 months with zero variability.", citations=["tx:demo_0001"])],
    ),
    "High Rent Burden": RiskAssessment(
        risk_score=78, recommendation="decline", confidence=0.88,
        reasoning_summary="Rent consumes 60% of gross income, leaving insufficient margin for an additional loan obligation. Monthly expenses consistently exceed net income.",
        risk_factors=[
            RiskFactor(severity="high", description="Rent-to-income ratio of 60% far exceeds the 40% maximum threshold.", citations=["tx:demo_0002"]),
            RiskFactor(severity="high", description="Negative cash buffer — expenses exceed income in 4 of 6 months.", citations=["tx:demo_0001"]),
        ],
        strengths=[RiskFactor(severity="low", description="Income source is stable W-2 employment.", citations=["tx:demo_0001"])],
    ),
    "High-Income Gig Worker": RiskAssessment(
        risk_score=32, recommendation="approve", confidence=0.85,
        reasoning_summary="High earning capacity with a low rent burden creates strong repayment capacity. Cash buffer remains healthy even in low-income months.",
        risk_factors=[RiskFactor(severity="low", description="Gig income variability introduces some uncertainty in month-to-month repayment.", citations=["tx:demo_0001"])],
        strengths=[
            RiskFactor(severity="low", description="Rent-to-income ratio of 16% is well below threshold.", citations=["tx:demo_0002"]),
            RiskFactor(severity="low", description="Zero NSF events across 6 months despite income variability.", citations=["tx:demo_0001"]),
        ],
    ),
    "Gig Worker + NSF": RiskAssessment(
        risk_score=64, recommendation="manual_review", confidence=0.65,
        reasoning_summary="Combination of income variability and an NSF event creates compounded risk. Neither factor alone would trigger decline, but together they warrant human analyst review.",
        risk_factors=[
            RiskFactor(severity="medium", description="Income variability combined with NSF event suggests cash management stress.", citations=["tx:demo_0001"]),
            RiskFactor(severity="medium", description="NSF fee coincides with a low-income month — suggests liquidity gap.", citations=["tx:demo_nsf_01"]),
        ],
        strengths=[RiskFactor(severity="low", description="Rent-to-income ratio is within acceptable range.", citations=["tx:demo_0002"])],
    ),
    "Very Tight Budget": RiskAssessment(
        risk_score=82, recommendation="decline", confidence=0.91,
        reasoning_summary="Fixed costs consume nearly all available income. Cash buffer is negative and adding a loan obligation would create immediate payment stress.",
        risk_factors=[
            RiskFactor(severity="high", description="Cash buffer is negative — monthly expenses exceed income.", citations=["tx:demo_0001"]),
            RiskFactor(severity="high", description="Rent-to-income ratio of 57% leaves the borrower structurally cash-negative.", citations=["tx:demo_0002"]),
        ],
        strengths=[RiskFactor(severity="low", description="No NSF events on record.", citations=["tx:demo_0001"])],
    ),
    "Borderline Gig": RiskAssessment(
        risk_score=50, recommendation="approve_with_conditions", confidence=0.70,
        reasoning_summary="Moderate gig income with moderate rent places this borrower at the boundary of approval criteria. Metrics are within range but not comfortably so.",
        risk_factors=[
            RiskFactor(severity="medium", description="Income variability means repayment capacity fluctuates by ~$2,400/month.", citations=["tx:demo_0001"]),
            RiskFactor(severity="low", description="Rent-to-income ratio of 36% is at the upper edge of the acceptable band.", citations=["tx:demo_0002"]),
        ],
        strengths=[RiskFactor(severity="low", description="Zero NSF events across 6 months of data.", citations=["tx:demo_0001"])],
    ),
}

# ── Synthetic transaction generator ───────────────────────────────────────────

def _make_transactions(user_id: str, persona: dict, months: int = 6) -> list[CategorizedTransaction]:
    income_source  = persona["income_source"]
    monthly_income = float(persona["monthly_income"])
    rent           = float(persona["rent"])
    nsf_count      = int(persona.get("nsf_count", 0))

    today = date.today()
    txns: list[CategorizedTransaction] = []
    counter = 0

    def txn(txn_date, amount, merchant, category, is_income, is_recurring, is_essential):
        nonlocal counter
        counter += 1
        return CategorizedTransaction(
            transaction_id=f"demo_{user_id}_{counter:04d}",
            account_id=f"acc_{user_id}",
            user_id=user_id,
            transaction_date=txn_date,
            amount=amount,
            merchant_name=merchant,
            description=merchant,
            plaid_category=[],
            pending=False,
            our_category=category,
            confidence_score=0.95,
            is_income=is_income,
            is_recurring=is_recurring,
            is_essential=is_essential,
            categorization_source="ml_model",
        )

    def month_date(months_ago: int, day: int) -> date:
        import calendar
        m = today.month - months_ago
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        return date(y, m, min(day, calendar.monthrange(y, m)[1]))

    if income_source == "W2":
        incomes = [monthly_income] * months
        income_cat, income_merchant = "income_salary", "EMPLOYER PAYROLL"
    else:
        raw = [5200.0, 3100.0, 4800.0, 2900.0, 5500.0, 3600.0]
        raw = [raw[i % len(raw)] for i in range(months)]
        scale = monthly_income / (sum([5200.0, 3100.0, 4800.0, 2900.0, 5500.0, 3600.0]) / 6)
        incomes = [round(v * scale, 2) for v in raw]
        income_cat, income_merchant = "income_freelance", "STRIPE PAYOUT"

    debt_payment = round(monthly_income * (0.28 if income_source == "W2" else 0.31), 2)
    nsf_months = set(range(1, min(nsf_count + 1, months)))

    for i in range(months):
        txns.append(txn(month_date(i, 5),  incomes[i],   income_merchant,    income_cat,             True,  income_source == "W2", False))
        txns.append(txn(month_date(i, 1),  -rent,         "PROPERTY MGMT",    "rent_mortgage",        False, True,  True))
        txns.append(txn(month_date(i, 8),  -300.0,        "WHOLE FOODS",      "groceries",            False, True,  True))
        txns.append(txn(month_date(i, 10), -120.0,        "ELECTRIC CO",      "utilities",            False, True,  True))
        txns.append(txn(month_date(i, 15), -debt_payment, "VISA CREDIT CARD", "debt_payment",         False, True,  False))
        txns.append(txn(month_date(i, 18), -200.0,        "RESTAURANTS",      "dining_entertainment", False, False, False))
        txns.append(txn(month_date(i, 22), -80.0,         "UBER",             "transportation",       False, False, False))
        if i in nsf_months:
            txns.append(txn(month_date(i, 25), -35.0, "NSF FEE", "nsf_fee", False, False, False))

    return txns

# ── Chart builders ─────────────────────────────────────────────────────────────

def _risk_gauge(score: int) -> go.Figure:
    color = "#16a34a" if score <= 35 else "#d97706" if score <= 60 else "#dc2626"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#94a3b8", "tickfont": {"size": 10}},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": "white",
            "borderwidth": 0,
            "steps": [
                {"range": [0,  35], "color": "#dcfce7"},
                {"range": [35, 65], "color": "#fef3c7"},
                {"range": [65,100], "color": "#fee2e2"},
            ],
            "threshold": {"line": {"color": "#1e293b", "width": 3}, "thickness": 0.75, "value": score},
        },
        number={"suffix": " / 100", "font": {"size": 28, "color": "#0f172a"}},
    ))
    fig.update_layout(
        height=200, margin=dict(t=20, b=0, l=20, r=20),
        paper_bgcolor="white", font=dict(color="#1e293b"),
    )
    return fig


def _monthly_income_chart(transactions: list) -> go.Figure:
    monthly: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.is_income:
            key = t.transaction_date.strftime("%b '%y")
            monthly[key] += t.amount

    months = sorted(monthly.keys(), key=lambda x: datetime.strptime(x, "%b '%y"))
    values = [monthly[m] for m in months]
    avg = sum(values) / len(values) if values else 0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=months, y=values,
        marker_color=["#16a34a" if v >= avg * 0.9 else "#f59e0b" for v in values],
        marker_line_width=0,
        text=[f"${v:,.0f}" for v in values],
        textposition="outside",
        textfont=dict(size=10, color="#475569"),
        hovertemplate="<b>%{x}</b><br>$%{y:,.0f}<extra></extra>",
    ))
    fig.add_hline(
        y=avg, line_dash="dot", line_color="#94a3b8", line_width=1.5,
        annotation_text=f"Avg ${avg:,.0f}",
        annotation_position="top right",
        annotation_font=dict(size=10, color="#64748b"),
    )
    fig.update_layout(
        title=dict(text="Monthly Income", font=dict(size=12, color="#64748b", weight=700), x=0),
        height=220,
        margin=dict(t=36, b=10, l=10, r=10),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(showgrid=True, gridcolor="#f1f5f9", tickprefix="$", showticklabels=False, zeroline=False),
        xaxis=dict(showgrid=False),
        showlegend=False,
    )
    return fig


def _expense_donut(transactions: list) -> go.Figure:
    by_cat: dict[str, float] = defaultdict(float)
    for t in transactions:
        if not t.is_income and t.our_category != "nsf_fee":
            by_cat[t.our_category] += abs(t.amount)

    cats = sorted(by_cat.keys(), key=lambda c: by_cat[c], reverse=True)
    values = [by_cat[c] for c in cats]
    labels = [CATEGORY_LABELS.get(c, c.replace("_", " ").title()) for c in cats]
    colors = [CATEGORY_COLORS.get(c, "#94a3b8") for c in cats]

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.6,
        marker=dict(colors=colors, line=dict(color="white", width=2)),
        textinfo="percent",
        textfont=dict(size=10),
        hovertemplate="<b>%{label}</b><br>$%{value:,.0f}  (%{percent})<extra></extra>",
    ))
    total = sum(values)
    fig.add_annotation(
        text=f"<b>${total:,.0f}</b><br><span style='color:#64748b;font-size:10px'>total spend</span>",
        x=0.5, y=0.5, showarrow=False, font=dict(size=13, color="#0f172a"),
        align="center",
    )
    fig.update_layout(
        title=dict(text="Expense Breakdown", font=dict(size=12, color="#64748b", weight=700), x=0),
        height=220,
        margin=dict(t=36, b=10, l=10, r=120),
        paper_bgcolor="white",
        legend=dict(font=dict(size=10), x=1.02, y=0.5, xanchor="left", yanchor="middle"),
    )
    return fig


def _transaction_scatter(transactions: list) -> go.Figure:
    fig = go.Figure()

    by_cat: dict[str, list] = defaultdict(list)
    for t in transactions:
        by_cat[t.our_category].append(t)

    for cat, txns in by_cat.items():
        color = CATEGORY_COLORS.get(cat, "#94a3b8")
        label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
        fig.add_trace(go.Scatter(
            x=[t.transaction_date for t in txns],
            y=[t.amount for t in txns],
            mode="markers",
            name=label,
            marker=dict(color=color, size=9, opacity=0.85, line=dict(color="white", width=1)),
            customdata=[t.merchant_name or t.description for t in txns],
            hovertemplate="<b>%{customdata}</b><br>$%{y:,.0f}  —  %{x}<extra></extra>",
        ))

    fig.add_hline(y=0, line_color="#e2e8f0", line_width=1)
    fig.update_layout(
        title=dict(text="Transaction History", font=dict(size=12, color="#64748b", weight=700), x=0),
        height=340,
        margin=dict(t=36, b=10, l=10, r=10),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(showgrid=True, gridcolor="#f1f5f9", tickprefix="$", zeroline=False),
        xaxis=dict(showgrid=False, tickformat="%b '%y"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="left", x=0, font=dict(size=10)),
    )
    return fig


# ── UI helpers ─────────────────────────────────────────────────────────────────

def _kpi_card(label: str, value: str, signal: str = "", signal_class: str = "sig-neu") -> str:
    signal_html = f'<div class="kpi-signal {signal_class}">{signal}</div>' if signal else ""
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {signal_html}
    </div>"""


def _factor_card(factor_type: str, severity: str, description: str, citations: list[str]) -> str:
    badge_class = "badge-strength" if factor_type == "strength" else f"badge-{severity}"
    badge_label = "Strength" if factor_type == "strength" else severity.upper()
    card_class  = "strength" if factor_type == "strength" else severity
    cites = ", ".join(citations[:4]) if citations else "—"
    return f"""
    <div class="factor-card {card_class}">
        <div><span class="sev-badge {badge_class}">{badge_label}</span></div>
        <div class="factor-desc">{description}</div>
        <div class="factor-cites">refs: {cites}</div>
    </div>"""


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### AgentLedger")
        st.caption("AI-augmented credit analysis")
        st.divider()

        data_source = st.radio("Data Source", ["Synthetic (Demo)", "Live (Plaid)"])
        live_mode = data_source == "Live (Plaid)"
        st.divider()

        if live_mode:
            st.caption("**Plaid Configuration**")
            plaid_token = st.text_input("Access Token", value=os.environ.get("PLAID_ACCESS_TOKEN", ""), type="password")
            borrower_id = st.text_input("Borrower ID", value="borrower_001")
            months = st.slider("Months of history", 3, 12, 6)
            persona_name, persona, fast_demo = None, None, False
        else:
            persona_name = st.selectbox("Borrower Persona", list(PERSONAS.keys()))
            persona = PERSONAS[persona_name]
            st.caption(f"_{persona['description']}_")
            months = st.slider("Months of history", 3, 12, 6)
            plaid_token, borrower_id = None, None

        st.divider()
        loan_amount  = st.number_input("Loan Amount ($)", 1_000, 500_000, 25_000, 1_000, "%d")
        loan_purpose = st.selectbox("Loan Purpose", [
            "Debt consolidation", "Home improvement", "Auto purchase",
            "Business expense", "Medical expense", "Education", "Other",
        ])

        st.divider()
        run_btn = st.button("Run Analysis", type="primary", use_container_width=True)
        if not live_mode:
            fast_demo = st.toggle("Fast Demo Mode", value=False,
                help="Pre-computed responses — instant results, no LLM call.")

    # ── Landing page ───────────────────────────────────────────────────────────
    if not run_btn:
        st.markdown("## Credit Analysis Pipeline")
        st.caption("Select a borrower persona in the sidebar and click **Run Analysis**.")
        st.divider()

        st.markdown('<div class="section-label">Available Personas</div>', unsafe_allow_html=True)
        rows = [
            {
                "Persona": name,
                "Monthly Income": f"${p['monthly_income']:,}",
                "Income Type": "W-2 Salary" if p["income_source"] == "W2" else "Gig / Freelance",
                "Rent": f"${p['rent']:,}",
                "NSF Events": p["nsf_count"],
                "Rent-to-Income": f"{p['rent']/p['monthly_income']:.0%}",
            }
            for name, p in PERSONAS.items()
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        return

    # ── Pipeline execution ─────────────────────────────────────────────────────
    user_id = (borrower_id or "borrower_001").strip() if live_mode else \
              f"demo_{persona_name.lower().replace(' ', '_').replace('/', '_')}"
    run_id  = str(uuid.uuid4())[:8]

    progress = st.progress(0, text="Starting pipeline...")
    t_start  = time.perf_counter()

    state = WorkflowState(
        user_id=user_id, loan_amount=float(loan_amount),
        loan_purpose=loan_purpose, run_id=run_id,
    )

    if live_mode:
        if not plaid_token:
            progress.empty()
            st.error("Enter a Plaid access token in the sidebar.")
            return
        progress.progress(10, text="Fetching transactions from Plaid...")
        try:
            state = ingest_node(state, {"access_token": plaid_token})
        except Exception as e:
            progress.empty(); st.error(f"Plaid error: {e}"); return

        progress.progress(25, text="Data quality checks...")
        state = profile_node(state)
        progress.progress(40, text="Categorizing transactions...")
        try:
            from agentledger.workflow.nodes import categorize_node
            state = categorize_node(state)
        except RuntimeError as e:
            progress.empty()
            st.error("ML categorizer not trained. Run: `python scripts/train_categorizer.py`")
            return
        progress.progress(55, text="Computing metrics...")
        state = analyze_node(state)
        metrics = state.metrics
    else:
        progress.progress(20, text="Generating synthetic transactions...")
        transactions = _make_transactions(user_id, persona, months)
        progress.progress(35, text="Computing cash flow metrics...")
        metrics = compute_metrics(user_id, transactions)
        state.transactions = transactions
        state.metrics      = metrics

    from agentledger.schemas.models import ValidationResult

    used_cache = False
    progress.progress(50, text="Running LLM risk assessment...")

    if not live_mode and fast_demo and persona_name in _DEMO_ASSESSMENTS:
        state.risk_assessment = _DEMO_ASSESSMENTS[persona_name]
        used_cache = True
    else:
        try:
            state = risk_assess_node(state, {})
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower() or "quota" in err.lower():
                state.risk_assessment = _DEMO_ASSESSMENTS.get(persona_name)
                used_cache = True
                if not state.risk_assessment:
                    progress.empty()
                    st.error("Rate limit hit and no cached response for this persona.")
                    return
                st.warning("OpenRouter rate limit hit — showing cached response. Enable Fast Demo Mode to avoid this.")
            else:
                progress.empty(); st.error(f"Pipeline error: {e}"); return

    progress.progress(75, text="Validating citations...")
    if used_cache:
        state.validation_result = ValidationResult(
            overall_validity=1.0, citation_checks=[], hallucinated_claims=[], passed=True,
        )
    else:
        state = validate_node(state, {})

    progress.progress(85, text="Checking escalation rules...")
    state = hitl_check_node(state, {})

    progress.progress(95, text="Generating credit memo...")
    state = report_node(state, {})

    progress.progress(100, text="Done.")
    elapsed = time.perf_counter() - t_start
    progress.empty()

    ra = state.risk_assessment
    vr = state.validation_result
    m  = metrics

    if not ra:
        st.error("Risk assessment failed — check OPENROUTER_API_KEY in .env")
        return

    # ── Hero banner ────────────────────────────────────────────────────────────
    fg, bg, rec_label = REC_META.get(ra.recommendation, ("#374151", "#f9fafb", ra.recommendation))
    icon = {"approve": "✓", "approve_with_conditions": "⚠", "decline": "✗", "manual_review": "⊙"}.get(ra.recommendation, "•")

    st.markdown(f"""
    <div class="hero-banner" style="background:{bg}; border:1.5px solid {fg}30; border-left:6px solid {fg};">
        <div class="hero-left">
            <div class="hero-label" style="color:{fg};">Credit Decision</div>
            <div class="hero-decision" style="color:{fg};">{icon}&nbsp; {rec_label}</div>
            <div class="hero-summary">{ra.reasoning_summary}</div>
        </div>
        <div class="hero-right">
            <div class="hero-score" style="color:{fg};">{ra.risk_score}</div>
            <div class="hero-score-label">Risk Score / 100</div>
            <div class="hero-meta">
                Confidence: <strong>{ra.confidence:.0%}</strong><br>
                Completed in {elapsed:.1f}s &nbsp;·&nbsp; Run {run_id}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Escalation notice ──────────────────────────────────────────────────────
    if state.escalate_to_human and state.escalation_reasons:
        reasons = " &nbsp;·&nbsp; ".join(state.escalation_reasons)
        st.markdown(f'<div class="esc-box">⚠ <strong>Escalated for Human Review</strong> &nbsp;—&nbsp; {reasons}</div>',
                    unsafe_allow_html=True)

    # ── KPI strip ─────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)

    dti_sig   = ("✓ Healthy",   "sig-ok")   if m.dti_ratio < 0.36  else ("⚠ Elevated", "sig-warn") if m.dti_ratio < 0.50 else ("✗ High",    "sig-bad")
    buf_sig   = ("✓ Healthy",   "sig-ok")   if m.cash_buffer_days > 15 else ("⚠ Thin",   "sig-warn") if m.cash_buffer_days > 0 else ("✗ Negative","sig-bad")
    cv_sig    = ("✓ Stable",    "sig-ok")   if m.income_cv < 0.15  else ("⚠ Variable", "sig-warn") if m.income_cv < 0.30 else ("✗ Volatile","sig-bad")
    nsf_sig   = ("✓ Clean",     "sig-ok")   if m.total_nsf_events == 0 else ("⚠ Present","sig-warn") if m.total_nsf_events <= 2 else ("✗ Multiple","sig-bad")
    rent_sig  = ("✓ Low",       "sig-ok")   if m.rent_to_income_ratio < 0.30 else ("⚠ Moderate","sig-warn") if m.rent_to_income_ratio < 0.40 else ("✗ High","sig-bad")

    with c1: st.markdown(_kpi_card("Avg Monthly Income", f"${m.avg_monthly_income:,.0f}", "", "sig-neu"), unsafe_allow_html=True)
    with c2: st.markdown(_kpi_card("Debt-to-Income",     f"{m.dti_ratio:.1%}",          *dti_sig),       unsafe_allow_html=True)
    with c3: st.markdown(_kpi_card("Cash Buffer",        f"{m.cash_buffer_days:.0f} days", *buf_sig),     unsafe_allow_html=True)
    with c4: st.markdown(_kpi_card("Income Stability",   f"CV {m.income_cv:.3f}",        *cv_sig),        unsafe_allow_html=True)
    with c5: st.markdown(_kpi_card("NSF Events",         str(m.total_nsf_events),        *nsf_sig),       unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ── Charts row ─────────────────────────────────────────────────────────────
    col_gauge, col_income, col_expense = st.columns([1, 1.6, 1.6])

    with col_gauge:
        st.markdown('<div class="section-label">Risk Score</div>', unsafe_allow_html=True)
        st.plotly_chart(_risk_gauge(ra.risk_score), use_container_width=True)
        st.markdown(
            f'<div style="text-align:center;font-size:11px;color:#64748b;margin-top:-10px;">'
            f'Rent-to-income: <strong>{m.rent_to_income_ratio:.0%}</strong> '
            f'<span class="{rent_sig[1]}">{rent_sig[0]}</span></div>',
            unsafe_allow_html=True,
        )

    with col_income:
        st.markdown('<div class="section-label">Income Trend</div>', unsafe_allow_html=True)
        st.plotly_chart(_monthly_income_chart(state.transactions), use_container_width=True)

    with col_expense:
        st.markdown('<div class="section-label">Spending Mix</div>', unsafe_allow_html=True)
        st.plotly_chart(_expense_donut(state.transactions), use_container_width=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Tabs ───────────────────────────────────────────────────────────────────
    tab_risk, tab_txn, tab_valid, tab_report = st.tabs([
        "Risk Analysis", "Transactions", "Validation", "Full Report"
    ])

    # ── Tab: Risk Analysis ─────────────────────────────────────────────────────
    with tab_risk:
        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown('<div class="section-label">Risk Factors</div>', unsafe_allow_html=True)
            if ra.risk_factors:
                for f in ra.risk_factors:
                    st.markdown(_factor_card("risk", f.severity, f.description, f.citations), unsafe_allow_html=True)
            else:
                st.caption("No significant risk factors identified.")

        with col_r:
            st.markdown('<div class="section-label">Strengths</div>', unsafe_allow_html=True)
            if ra.strengths:
                for f in ra.strengths:
                    st.markdown(_factor_card("strength", f.severity, f.description, f.citations), unsafe_allow_html=True)
            else:
                st.caption("No notable strengths identified.")

    # ── Tab: Transactions ──────────────────────────────────────────────────────
    with tab_txn:
        st.plotly_chart(_transaction_scatter(state.transactions), use_container_width=True)

        st.markdown('<div class="section-label">Category Summary</div>', unsafe_allow_html=True)
        by_cat: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": 0.0})
        for t in state.transactions:
            by_cat[t.our_category]["count"]  += 1
            by_cat[t.our_category]["total"]  += t.amount

        summary = [
            {
                "Category":   CATEGORY_LABELS.get(cat, cat.replace("_", " ").title()),
                "Transactions": data["count"],
                "Net Amount": f"${data['total']:+,.0f}",
            }
            for cat, data in sorted(by_cat.items(), key=lambda x: abs(x[1]["total"]), reverse=True)
        ]
        st.dataframe(summary, use_container_width=True, hide_index=True)

    # ── Tab: Validation ────────────────────────────────────────────────────────
    with tab_valid:
        v1, v2, v3 = st.columns(3)
        validity_pct = vr.overall_validity if vr else 0.0

        v1.metric("Citation Validity",  f"{validity_pct:.0%}",
                  help="% of LLM claims that cite a real transaction ID.")
        v2.metric("LLM Confidence",     f"{ra.confidence:.0%}",
                  help="Model's self-reported confidence in the recommendation.")
        v3.metric("Human Review",       "Required" if state.escalate_to_human else "Not Required")

        if vr and vr.hallucinated_claims:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div class="section-label">Hallucinated Citations</div>', unsafe_allow_html=True)
            for claim in vr.hallucinated_claims:
                st.error(f"Referenced transaction not found in source data: `{claim}`")

        if used_cache:
            st.info("Fast Demo Mode — validation skipped for pre-computed responses.")

    # ── Tab: Full Report ───────────────────────────────────────────────────────
    with tab_report:
        if state.final_report_path and Path(state.final_report_path).exists():
            memo_text = Path(state.final_report_path).read_text(encoding="utf-8")
            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button("Download Markdown", data=memo_text,
                    file_name=f"credit_memo_{user_id}_{run_id}.md", mime="text/markdown",
                    use_container_width=True)
            with dl2:
                pdf_path = state.final_report_pdf_path
                if pdf_path and Path(pdf_path).exists():
                    st.download_button("Download PDF", data=Path(pdf_path).read_bytes(),
                        file_name=f"credit_memo_{user_id}_{run_id}.pdf", mime="application/pdf",
                        use_container_width=True)
                else:
                    st.info("PDF unavailable — install reportlab to enable.")
            st.divider()
            st.markdown(memo_text)
        else:
            st.caption("Report not found — check the reports/ directory.")


if __name__ == "__main__":
    main()
