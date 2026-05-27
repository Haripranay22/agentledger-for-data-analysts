"""
AgentLedger — Credit Analysis Dashboard
Streamlit app for reviewing AI-generated credit analysis results.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Allow imports from src/ and dashboard/ when run directly (streamlit run dashboard/app.py)
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from dashboard.sample_data import (
    DEMO_STATE,
    DEMO_TRANSACTIONS,
    get_expense_breakdown,
    get_monthly_income_series,
)

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AgentLedger | Credit Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  .metric-card {
    background: #1e2530;
    border-radius: 10px;
    padding: 18px 22px;
    text-align: center;
  }
  .metric-label { font-size: 0.78rem; color: #8a9ab5; text-transform: uppercase; letter-spacing: 0.05em; }
  .metric-value { font-size: 2rem; font-weight: 700; color: #e8edf5; }
  .metric-sub   { font-size: 0.72rem; color: #5a6a80; margin-top: 2px; }

  .rec-badge {
    display: inline-block;
    padding: 6px 18px;
    border-radius: 20px;
    font-size: 0.9rem;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .rec-approve              { background: #14532d; color: #4ade80; }
  .rec-approve_with_conditions { background: #713f12; color: #fbbf24; }
  .rec-manual_review        { background: #1e3a5f; color: #60a5fa; }
  .rec-decline              { background: #7f1d1d; color: #f87171; }

  .severity-low    { color: #4ade80; font-weight: 600; }
  .severity-medium { color: #fbbf24; font-weight: 600; }
  .severity-high   { color: #f87171; font-weight: 600; }

  div[data-testid="stMetric"] label { color: #8a9ab5 !important; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────────

REC_LABELS = {
    "approve":                "APPROVE",
    "approve_with_conditions": "APPROVE W/ CONDITIONS",
    "manual_review":          "MANUAL REVIEW",
    "decline":                "DECLINE",
}

REC_COLORS = {
    "approve":                "#4ade80",
    "approve_with_conditions": "#fbbf24",
    "manual_review":          "#60a5fa",
    "decline":                "#f87171",
}

SEVERITY_COLORS = {"low": "#4ade80", "medium": "#fbbf24", "high": "#f87171"}


def load_saved_analyses() -> list[Path]:
    reports_dir = ROOT / "reports"
    if not reports_dir.exists():
        return []
    return sorted(reports_dir.glob("**/state_*.json"), reverse=True)


def load_state_from_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def fmt_currency(v: float) -> str:
    return f"${v:,.0f}"


def fmt_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def fmt_days(v: float) -> str:
    return f"{v:.0f} days"


def risk_color(score: int) -> str:
    if score < 30:
        return "#4ade80"
    if score < 60:
        return "#fbbf24"
    return "#f87171"


# ── Live-pipeline helpers ──────────────────────────────────────────────────────

_MONTH_LABELS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def _iso_to_month_label(iso_month: str) -> str:
    try:
        y, m = iso_month.split("-")
        return f"{_MONTH_LABELS[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return iso_month


def _pipeline_result_to_dict(result: Any) -> dict[str, Any]:
    """Serialize pipeline output (Pydantic model or LangGraph dict) to plain dict."""
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        out: dict[str, Any] = {}
        for key, val in result.items():
            if hasattr(val, "model_dump"):
                out[key] = val.model_dump(mode="json")
            elif isinstance(val, list):
                out[key] = [
                    v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                    for v in val
                ]
            else:
                out[key] = val
        return out
    return {}


def _extract_transactions(result: Any) -> list[dict[str, Any]]:
    """Convert CategorizedTransaction objects to the format the dashboard expects."""
    raw = result.transactions if hasattr(result, "transactions") else result.get("transactions", [])
    out = []
    for t in raw:
        if hasattr(t, "transaction_id"):
            out.append({
                "id": t.transaction_id,
                "date": t.transaction_date.isoformat() if hasattr(t.transaction_date, "isoformat") else str(t.transaction_date),
                "merchant": t.merchant_name or t.description,
                "category": t.our_category,
                "amount": t.amount,
                "is_income": t.is_income,
                "is_recurring": t.is_recurring,
            })
        elif isinstance(t, dict):
            out.append({
                "id": t.get("transaction_id", ""),
                "date": str(t.get("transaction_date", "")),
                "merchant": t.get("merchant_name") or t.get("description", ""),
                "category": t.get("our_category", ""),
                "amount": t.get("amount", 0.0),
                "is_income": t.get("is_income", False),
                "is_recurring": t.get("is_recurring", False),
            })
    return out


def _compute_income_series(transactions: list[dict[str, Any]]) -> tuple[list[str], list[float]]:
    """Compute monthly income series from real transactions for the trend chart."""
    monthly: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.get("is_income") and t.get("amount", 0) > 0:
            date_str = str(t.get("date", ""))[:7]  # "YYYY-MM"
            if len(date_str) == 7:
                monthly[date_str] += t["amount"]
    months_iso = sorted(monthly.keys())
    return [_iso_to_month_label(m) for m in months_iso], [monthly[m] for m in months_iso]


def _compute_expense_breakdown(transactions: list[dict[str, Any]]) -> dict[str, float]:
    """Compute per-category expense totals (top 8) from real transactions."""
    totals: dict[str, float] = defaultdict(float)
    for t in transactions:
        if not t.get("is_income") and t.get("amount", 0) < 0:
            cat = t.get("category") or "other"
            totals[cat] += abs(t["amount"])
    return dict(sorted(totals.items(), key=lambda x: x[1], reverse=True)[:8])


def run_pipeline(
    user_id: str,
    loan_amount: float,
    loan_purpose: str | None,
    access_token: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Invoke the full LangGraph pipeline. Returns (state_dict, transactions)."""
    from dotenv import load_dotenv
    load_dotenv()

    prev_token: str | None = None
    if access_token:
        prev_token = os.environ.get("PLAID_ACCESS_TOKEN")
        os.environ["PLAID_ACCESS_TOKEN"] = access_token

    try:
        from agentledger.schemas.models import WorkflowState
        from agentledger.workflow.graph import credit_analysis_graph

        initial = WorkflowState(
            user_id=user_id,
            loan_amount=loan_amount,
            loan_purpose=loan_purpose or None,
        )
        result = credit_analysis_graph.invoke(initial)
        return _pipeline_result_to_dict(result), _extract_transactions(result)
    finally:
        if access_token:
            if prev_token is None:
                os.environ.pop("PLAID_ACCESS_TOKEN", None)
            else:
                os.environ["PLAID_ACCESS_TOKEN"] = prev_token


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## AgentLedger")
    st.markdown("AI-augmented credit analysis")
    st.divider()

    data_source = st.radio(
        "Data source",
        ["Demo borrower (no API needed)", "Load saved analysis", "Run live analysis"],
        index=0,
    )

    state: dict[str, Any] = {}
    transactions: list[dict[str, Any]] = []

    if data_source == "Demo borrower (no API needed)":
        state = DEMO_STATE
        transactions = DEMO_TRANSACTIONS
        st.info("Showing sample borrower: USER_001 — Stable W-2 employee")

    elif data_source == "Load saved analysis":
        saved = load_saved_analyses()
        if saved:
            chosen = st.selectbox(
                "Select analysis",
                saved,
                format_func=lambda p: f"{p.parent.name} / {p.stem}",
            )
            if chosen:
                state = load_state_from_json(chosen)
                transactions = []
                st.success(f"Loaded: {chosen.name}")
        else:
            st.warning(
                "No saved analyses found in `reports/`. "
                "Run the pipeline first:\n\n"
                "```\nagentledger analyze --user-id USER_001 --loan-amount 15000\n```"
            )
            st.stop()

    else:  # Run live analysis
        has_llm = bool(os.environ.get("OPENAI_API_KEY"))
        has_plaid_creds = bool(
            os.environ.get("PLAID_CLIENT_ID") and os.environ.get("PLAID_SECRET")
        )
        has_plaid_token = bool(os.environ.get("PLAID_ACCESS_TOKEN"))

        for label, ok in [("LLM API key", has_llm), ("Plaid credentials", has_plaid_creds)]:
            st.markdown(f"{'✅' if ok else '❌'} {label}")

        with st.form("live_analysis_form"):
            user_id_input = st.text_input("User ID", value="USER_001")
            loan_amount_input = st.number_input(
                "Loan Amount ($)",
                min_value=500.0,
                max_value=2_000_000.0,
                value=25_000.0,
                step=1_000.0,
            )
            loan_purpose_input = st.text_input(
                "Loan Purpose (optional)", value="Debt consolidation"
            )
            plaid_token_input = (
                st.text_input(
                    "Plaid Access Token",
                    type="password",
                    help="PLAID_ACCESS_TOKEN not found in environment",
                )
                if not has_plaid_token
                else ""
            )
            can_run = has_llm and has_plaid_creds
            submitted = st.form_submit_button(
                "▶  Run Analysis", disabled=not can_run, use_container_width=True,
            )
            if not can_run:
                st.caption("Set OPENAI_API_KEY and Plaid credentials in .env to enable")

        if submitted:
            token = plaid_token_input.strip() if not has_plaid_token else None
            with st.spinner("Running pipeline… this may take 30–60 s"):
                try:
                    result_state, result_txns = run_pipeline(
                        user_id=user_id_input.strip(),
                        loan_amount=float(loan_amount_input),
                        loan_purpose=loan_purpose_input.strip() or None,
                        access_token=token or None,
                    )
                    st.session_state["live_result"] = (result_state, result_txns)
                except Exception as exc:
                    st.error(f"Pipeline error: {exc}")
                    st.stop()

        if "live_result" not in st.session_state:
            st.info("Fill in the form above and click **▶  Run Analysis**.")
            st.stop()

        state, transactions = st.session_state["live_result"]
        st.success(
            f"Analysis ready — Run ID: `{str(state.get('run_id') or '')[:12]}`"
        )

    st.divider()
    st.markdown("**Pipeline status**")
    api_keys = {
        "LLM API": bool(os.environ.get("OPENAI_API_KEY")),
        "Plaid": bool(os.environ.get("PLAID_CLIENT_ID")),
        "Langfuse": bool(os.environ.get("LANGFUSE_PUBLIC_KEY")),
    }
    for name, ok in api_keys.items():
        icon = "✅" if ok else "⬜"
        st.markdown(f"{icon} {name}")

# ── Guard ──────────────────────────────────────────────────────────────────────

if not state:
    st.info("Select a data source in the sidebar.")
    st.stop()

metrics = state.get("metrics", {})
ra = state.get("risk_assessment", {})
vr = state.get("validation_result", {})
rec = ra.get("recommendation", "manual_review")

# ── Header ─────────────────────────────────────────────────────────────────────

col_title, col_rec = st.columns([3, 1])
with col_title:
    st.markdown(f"## Borrower: `{state['user_id']}`")
    st.markdown(
        f"Loan request: **{fmt_currency(state['loan_amount'])}**"
        + (f" — {state['loan_purpose']}" if state.get("loan_purpose") else "")
        + f"  |  Run ID: `{(state.get('run_id') or 'N/A')[:12]}`"
    )

with col_rec:
    badge_class = f"rec-{rec}"
    badge_label = REC_LABELS.get(rec, rec.upper())
    st.markdown(
        f'<div style="text-align:right; padding-top:8px">'
        f'<span class="rec-badge {badge_class}">{badge_label}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if state.get("escalate_to_human"):
        st.markdown(
            '<div style="text-align:right; color:#fbbf24; font-size:0.82rem;">'
            "⚠️ Escalated for review"
            "</div>",
            unsafe_allow_html=True,
        )

st.divider()

# ── KPI Row ────────────────────────────────────────────────────────────────────

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.metric("Avg Monthly Income", fmt_currency(metrics.get("avg_monthly_income", 0)))
with k2:
    dti = metrics.get("dti_ratio", 0)
    dti_delta = "Good (<36%)" if dti < 0.36 else "High"
    st.metric("Debt-to-Income", fmt_pct(dti), delta=dti_delta, delta_color="normal" if dti < 0.36 else "inverse")
with k3:
    nsf = metrics.get("total_nsf_events", 0)
    st.metric("NSF Events", nsf, delta="Clean" if nsf == 0 else f"{nsf} overdrafts", delta_color="normal" if nsf == 0 else "inverse")
with k4:
    buf = metrics.get("cash_buffer_days", 0)
    st.metric("Cash Buffer", fmt_days(buf), delta="Strong (>30d)" if buf >= 30 else "Thin", delta_color="normal" if buf >= 30 else "inverse")
with k5:
    conf = ra.get("confidence", 0)
    st.metric("AI Confidence", fmt_pct(conf))

st.divider()

# ── Risk Gauge + Summary ───────────────────────────────────────────────────────

col_gauge, col_summary = st.columns([1, 2])

with col_gauge:
    score = ra.get("risk_score", 50)
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": "Risk Score", "font": {"size": 16, "color": "#8a9ab5"}},
        number={"font": {"size": 42, "color": risk_color(score)}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#3a4a60"},
            "bar": {"color": risk_color(score), "thickness": 0.25},
            "bgcolor": "#1e2530",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 30],   "color": "#14532d"},
                {"range": [30, 60],  "color": "#713f12"},
                {"range": [60, 100], "color": "#7f1d1d"},
            ],
            "threshold": {
                "line": {"color": "#e8edf5", "width": 3},
                "thickness": 0.8,
                "value": score,
            },
        },
    ))
    fig_gauge.update_layout(
        height=220,
        margin=dict(l=20, r=20, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e8edf5",
    )
    st.plotly_chart(fig_gauge, use_container_width=True)
    risk_label = "LOW RISK" if score < 30 else ("MEDIUM RISK" if score < 60 else "HIGH RISK")
    st.markdown(
        f'<div style="text-align:center; color:{risk_color(score)}; font-weight:700; letter-spacing:0.08em">'
        f"{risk_label}</div>",
        unsafe_allow_html=True,
    )

with col_summary:
    st.markdown("#### AI Reasoning")
    st.info(ra.get("reasoning_summary", "No summary available."))

    st.markdown("#### Validation")
    validity = vr.get("overall_validity", 0)
    vpass = vr.get("passed", False)
    v1, v2, v3 = st.columns(3)
    v1.metric("Citation Validity", fmt_pct(validity))
    v2.metric("Status", "Passed" if vpass else "Failed")
    v3.metric("Hallucinated Claims", len(vr.get("hallucinated_claims", [])))

    if state.get("escalate_to_human"):
        st.warning("**Escalated for human review**\n\n" + "\n".join(f"- {r}" for r in state.get("escalation_reasons", [])))

st.divider()

# ── Charts: Income Trend + Expense Breakdown ───────────────────────────────────

col_trend, col_exp = st.columns(2)

with col_trend:
    st.markdown("#### Monthly Income Trend")
    if transactions and data_source == "Run live analysis":
        months, income_vals = _compute_income_series(transactions)
        if not months:
            months, income_vals = get_monthly_income_series()
    else:
        months, income_vals = get_monthly_income_series()
    avg = metrics.get("avg_monthly_income", 0)

    fig_income = go.Figure()
    fig_income.add_trace(go.Scatter(
        x=months, y=income_vals,
        mode="lines+markers",
        name="Income",
        line=dict(color="#4ade80", width=2.5),
        marker=dict(size=7),
        fill="tozeroy",
        fillcolor="rgba(74, 222, 128, 0.08)",
    ))
    fig_income.add_hline(
        y=avg, line_dash="dot", line_color="#8a9ab5",
        annotation_text=f"Avg {fmt_currency(avg)}",
        annotation_font_color="#8a9ab5",
    )
    fig_income.update_layout(
        height=280,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e8edf5",
        margin=dict(l=10, r=10, t=10, b=40),
        xaxis=dict(showgrid=False, color="#5a6a80"),
        yaxis=dict(showgrid=True, gridcolor="#1e2530", color="#5a6a80", tickprefix="$"),
        showlegend=False,
    )
    st.plotly_chart(fig_income, use_container_width=True)

with col_exp:
    st.markdown("#### Expense Breakdown")
    if transactions and data_source == "Run live analysis":
        breakdown = _compute_expense_breakdown(transactions)
        if not breakdown:
            breakdown = get_expense_breakdown()
    else:
        breakdown = get_expense_breakdown()
    labels = list(breakdown.keys())
    values = list(breakdown.values())

    fig_exp = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        textinfo="label+percent",
        textfont_size=11,
        marker=dict(colors=px.colors.qualitative.Set3),
    ))
    fig_exp.update_layout(
        height=280,
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e8edf5",
        margin=dict(l=0, r=0, t=10, b=10),
        showlegend=False,
        annotations=[dict(
            text=f"Avg<br>{fmt_currency(metrics.get('avg_monthly_expenses', 0))}/mo",
            x=0.5, y=0.5, font_size=13, showarrow=False,
            font_color="#8a9ab5",
        )],
    )
    st.plotly_chart(fig_exp, use_container_width=True)

# ── Cash Flow Metrics Table ────────────────────────────────────────────────────

with st.expander("Cash Flow Metrics (all 8)", expanded=False):
    metrics_rows = [
        ("Avg Monthly Income",       fmt_currency(metrics.get("avg_monthly_income", 0)),    "Target: maximise"),
        ("Avg Monthly Expenses",     fmt_currency(metrics.get("avg_monthly_expenses", 0)),   "Target: below income"),
        ("Debt-to-Income Ratio",     fmt_pct(metrics.get("dti_ratio", 0)),                   "Good: <36%"),
        ("Income CV (stability)",    f"{metrics.get('income_cv', 0):.3f}",                   "Good: <0.3"),
        ("Total NSF Events",         str(metrics.get("total_nsf_events", 0)),                "Good: 0"),
        ("Cash Buffer Days",         fmt_days(metrics.get("cash_buffer_days", 0)),            "Good: >30 days"),
        ("Rent-to-Income Ratio",     fmt_pct(metrics.get("rent_to_income_ratio", 0)),         "Good: <33%"),
        ("Discretionary Ratio",      fmt_pct(metrics.get("discretionary_spending_ratio", 0)),"Good: <40%"),
        ("Months Analyzed",          str(metrics.get("months_analyzed", 0)),                 "Standard: 6"),
    ]
    import pandas as pd
    df_metrics = pd.DataFrame(metrics_rows, columns=["Metric", "Value", "Benchmark"])
    st.dataframe(df_metrics, use_container_width=True, hide_index=True)

st.divider()

# ── Risk Factors & Strengths ───────────────────────────────────────────────────

col_risk, col_str = st.columns(2)

with col_risk:
    st.markdown("#### Risk Factors")
    risk_factors = ra.get("risk_factors", [])
    if not risk_factors:
        st.success("No significant risk factors identified.")
    for factor in risk_factors:
        sev = factor.get("severity", "low")
        color = SEVERITY_COLORS[sev]
        with st.container(border=True):
            st.markdown(
                f'<span class="severity-{sev}">[{sev.upper()}]</span> {factor["description"]}',
                unsafe_allow_html=True,
            )
            cites = factor.get("citations", [])
            if cites:
                st.caption(f"Citations: {', '.join(cites)}")

with col_str:
    st.markdown("#### Strengths")
    strengths = ra.get("strengths", [])
    if not strengths:
        st.warning("No strengths identified.")
    for strength in strengths:
        with st.container(border=True):
            st.markdown(f"**{strength['description']}**")
            cites = strength.get("citations", [])
            if cites:
                st.caption(f"Citations: {', '.join(cites)}")

st.divider()

# ── Transaction Explorer ───────────────────────────────────────────────────────

st.markdown("#### Transaction Explorer")

if transactions:
    import pandas as pd

    df = pd.DataFrame([
        {
            "Date":      t.get("date", ""),
            "Merchant":  t.get("merchant", ""),
            "Category":  t.get("category", ""),
            "Amount":    t.get("amount", 0),
            "Income":    "Yes" if t.get("is_income") else "No",
            "Recurring": "Yes" if t.get("is_recurring") else "No",
            "Tx ID":     t.get("id", ""),
        }
        for t in transactions
    ]).sort_values("Date", ascending=False)

    col_search, col_cat = st.columns([2, 1])
    with col_search:
        search = st.text_input("Search merchant / category", placeholder="e.g. Payroll, rent…")
    with col_cat:
        cats = ["All"] + sorted(df["Category"].unique().tolist())
        cat_filter = st.selectbox("Filter by category", cats)

    if search:
        mask = df["Merchant"].str.contains(search, case=False) | df["Category"].str.contains(search, case=False)
        df = df[mask]
    if cat_filter != "All":
        df = df[df["Category"] == cat_filter]

    def color_amount(val: float) -> str:
        return "color: #4ade80" if val > 0 else "color: #f87171"

    st.dataframe(
        df.style.map(color_amount, subset=["Amount"]).format({"Amount": "${:,.2f}"}),
        use_container_width=True,
        hide_index=True,
        height=320,
    )
    st.caption(f"{len(df)} transactions shown")
else:
    st.info("Transaction detail not available for this analysis.")

st.divider()

# ── Audit & Run Details ────────────────────────────────────────────────────────

with st.expander("Audit & Run Details"):
    a1, a2, a3 = st.columns(3)
    a1.markdown(f"**Run ID**\n\n`{state.get('run_id', 'N/A')}`")
    a2.markdown(f"**Retries**\n\n{state.get('retry_count', 0)}")
    a3.markdown(f"**Report path**\n\n`{state.get('final_report_path') or 'Not saved'}`")

    if state.get("escalate_to_human"):
        st.warning("**Escalation reasons:**\n" + "\n".join(f"- {r}" for r in state.get("escalation_reasons", [])))

    st.markdown("**Validation details**")
    st.json({
        "overall_validity": vr.get("overall_validity"),
        "passed": vr.get("passed"),
        "hallucinated_claims": vr.get("hallucinated_claims", []),
    })

    insuf = ra.get("insufficient_data_areas", [])
    if insuf:
        st.warning("**Insufficient data areas:**\n" + "\n".join(f"- {i}" for i in insuf))

# ── Footer ─────────────────────────────────────────────────────────────────────

st.markdown(
    '<div style="text-align:center; color:#3a4a60; font-size:0.75rem; padding-top:24px">'
    "AgentLedger — metrics computed deterministically in Python + dbt SQL · "
    "LLM used only for interpretation · every claim citation-validated"
    "</div>",
    unsafe_allow_html=True,
)
