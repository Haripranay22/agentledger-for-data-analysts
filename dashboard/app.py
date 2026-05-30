"""
AgentLedger — Credit Analysis Dashboard
Production-grade Streamlit app for AI-augmented credit risk review.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# Load .env at module startup so env-var checks reflect real credentials
from dotenv import dotenv_values as _dotenv_values
_env_file = ROOT / ".env"
if _env_file.exists():
    _dotenv = _dotenv_values(_env_file)
    for _k, _v in _dotenv.items():
        os.environ[_k] = _v or ""
    for _var in ("OPENAI_BASE_URL",):
        if _var not in _dotenv:
            os.environ.pop(_var, None)

from dashboard.review_store import REVIEW_DECISION_LABELS as _REVIEW_DECISION_LABELS
from dashboard.review_store import ReviewStore
from dashboard.sample_data import (
    DEMO_STATE,
    DEMO_TRANSACTIONS,
    get_expense_breakdown,
    get_monthly_income_series,
)

logger = logging.getLogger(__name__)
_review_store = ReviewStore()

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AgentLedger | Credit Intelligence",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  /* ── Global reset ── */
  .block-container { padding-top: 1.8rem !important; padding-bottom: 2rem !important; }

  /* ── Brand header ── */
  .brand-header {
    display: flex; align-items: center; gap: 10px;
    padding: 0 0 4px 0; margin-bottom: 2px;
  }
  .brand-logo {
    width: 28px; height: 28px; border-radius: 6px;
    background: linear-gradient(135deg, #4f8ef7 0%, #7c3aed 100%);
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 14px; font-weight: 900; color: white;
  }
  .brand-name {
    font-size: 1.15rem; font-weight: 800; color: #e8edf5;
    letter-spacing: -0.01em;
  }
  .brand-tag {
    font-size: 0.68rem; color: #4f8ef7; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase;
  }

  /* ── KPI cards ── */
  .kpi-card {
    background: linear-gradient(145deg, #1a2035 0%, #141824 100%);
    border: 1px solid #2a3350;
    border-radius: 12px;
    padding: 18px 20px 14px 20px;
    position: relative;
    overflow: hidden;
  }
  .kpi-card::before {
    content: ""; position: absolute; top: 0; left: 0;
    width: 3px; height: 100%;
  }
  .kpi-card.green::before  { background: #4ade80; }
  .kpi-card.amber::before  { background: #fbbf24; }
  .kpi-card.red::before    { background: #f87171; }
  .kpi-card.blue::before   { background: #60a5fa; }
  .kpi-card.purple::before { background: #a78bfa; }
  .kpi-label {
    font-size: 0.7rem; color: #6b7a9a; text-transform: uppercase;
    letter-spacing: 0.07em; font-weight: 600; margin-bottom: 6px;
  }
  .kpi-value {
    font-size: 1.75rem; font-weight: 800; color: #e8edf5;
    line-height: 1.1; letter-spacing: -0.02em;
  }
  .kpi-sub {
    font-size: 0.72rem; margin-top: 5px; font-weight: 500;
  }
  .kpi-sub.good  { color: #4ade80; }
  .kpi-sub.warn  { color: #fbbf24; }
  .kpi-sub.bad   { color: #f87171; }
  .kpi-sub.muted { color: #4a5a78; }

  /* ── Recommendation badge ── */
  .rec-badge {
    display: inline-block; padding: 5px 16px;
    border-radius: 20px; font-size: 0.78rem;
    font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase;
  }
  .rec-approve               { background: #14532d; color: #4ade80; border: 1px solid #166534; }
  .rec-approve_with_conditions { background: #451a03; color: #fbbf24; border: 1px solid #92400e; }
  .rec-manual_review         { background: #0c1a3a; color: #60a5fa; border: 1px solid #1e3a5f; }
  .rec-decline               { background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; }
  .rec-defer                 { background: #2e1065; color: #a78bfa; border: 1px solid #4c1d95; }
  .human-badge {
    display: inline-block; background: #1e3a5f; color: #93c5fd;
    font-size: 0.65rem; font-weight: 700; padding: 2px 7px;
    border-radius: 8px; margin-left: 6px; vertical-align: middle;
    letter-spacing: 0.05em; text-transform: uppercase;
  }
  .reviewed-tag {
    display: inline-block; background: #14532d; color: #4ade80;
    font-size: 0.68rem; font-weight: 700; padding: 2px 9px;
    border-radius: 10px; letter-spacing: 0.04em; margin-left: 10px;
    vertical-align: middle;
  }

  /* ── Section header ── */
  .section-title {
    font-size: 0.8rem; font-weight: 700; color: #4f8ef7;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin-bottom: 14px; padding-bottom: 8px;
    border-bottom: 1px solid #1e2a40;
  }

  /* ── Severity ── */
  .sev-low    { color: #4ade80; font-weight: 700; }
  .sev-medium { color: #fbbf24; font-weight: 700; }
  .sev-high   { color: #f87171; font-weight: 700; }

  /* ── HITL panels ── */
  .hitl-pending {
    background: linear-gradient(135deg, #2d1f00, #1a1400);
    border: 1px solid #92400e; border-left: 4px solid #f59e0b;
    border-radius: 10px; padding: 16px 20px; margin-bottom: 16px;
  }
  .hitl-done {
    background: linear-gradient(135deg, #0a1f0a, #061206);
    border: 1px solid #166534; border-left: 4px solid #22c55e;
    border-radius: 10px; padding: 16px 20px; margin-bottom: 16px;
  }

  /* ── Hero launch panel ── */
  .hero-panel {
    background: linear-gradient(145deg, #0f1b35 0%, #0a0f1e 100%);
    border: 1px solid #1e2e50; border-radius: 16px;
    padding: 36px 40px; text-align: center; margin: 20px 0;
  }
  .hero-title {
    font-size: 2rem; font-weight: 800; color: #e8edf5;
    letter-spacing: -0.03em; margin-bottom: 8px;
  }
  .hero-sub {
    font-size: 0.95rem; color: #5a6a8a; margin-bottom: 28px;
  }
  .preflight-item {
    display: inline-flex; align-items: center; gap: 6px;
    background: #141824; border: 1px solid #2a3350;
    border-radius: 8px; padding: 7px 14px;
    font-size: 0.78rem; color: #8a9ab5; font-weight: 600; margin: 4px;
  }

  /* ── Step log ── */
  .step-row {
    display: flex; align-items: center; gap: 10px;
    padding: 7px 0; border-bottom: 1px solid #1a2030;
    font-size: 0.82rem; color: #a0b0c8;
  }
  .step-row:last-child { border-bottom: none; }
  .step-done  { color: #4ade80; }
  .step-active { color: #fbbf24; }

  /* ── Factor card ── */
  .factor-card {
    background: #111827; border: 1px solid #1e2a3a;
    border-radius: 8px; padding: 12px 14px; margin-bottom: 8px;
  }

  /* ── Misc overrides ── */
  div[data-testid="stMetric"] label { color: #6b7a9a !important; font-size: 0.7rem !important; }
  div[data-testid="stMetric"] div[data-testid="metric-container"] > div:first-child {
    font-size: 1.4rem !important;
  }
  div[data-testid="stSidebar"] { border-right: 1px solid #1a2030 !important; }
  .stDataFrame { border: 1px solid #1e2a3a !important; border-radius: 8px !important; }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────

REC_LABELS = {
    "approve":                 "Approve",
    "approve_with_conditions": "Approve w/ Conditions",
    "manual_review":           "Manual Review",
    "decline":                 "Decline",
    "defer":                   "Defer",
    "confirm_ai":              "Confirm AI",
}

EXPENSE_COLORS = [
    "#4f8ef7", "#7c3aed", "#06b6d4", "#10b981",
    "#f59e0b", "#ef4444", "#ec4899", "#8b5cf6",
]

_PIPELINE_STEPS = {
    "ingest_node":      ("1", "Ingesting transactions from Plaid"),
    "profile_node":     ("2", "Profiling cash flow metrics"),
    "categorize_node":  ("3", "Categorizing transactions with LLM"),
    "analyze_node":     ("4", "Analyzing spending patterns"),
    "risk_assess_node": ("5", "Running AI risk assessment"),
    "validate_node":    ("6", "Validating citations & claims"),
    "hitl_check_node":  ("7", "Checking escalation criteria"),
    "report_node":      ("8", "Generating credit memo"),
}

_MONTH_LABELS = ["Jan","Feb","Mar","Apr","May","Jun",
                 "Jul","Aug","Sep","Oct","Nov","Dec"]


# ── Cached resources ───────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _get_pipeline():
    """Import and return the LangGraph pipeline (cached — no re-import on rerun)."""
    from agentledger.workflow.graph import credit_analysis_graph
    return credit_analysis_graph


# ── Helpers ────────────────────────────────────────────────────────────────────

def fmt_currency(v: float | None) -> str:
    if v is None:
        return "—"
    return f"${v:,.0f}"


def fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"


def fmt_days(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.0f}d"


def risk_color(score: int) -> str:
    if score < 30:
        return "#4ade80"
    if score < 60:
        return "#fbbf24"
    return "#f87171"


def _iso_to_month_label(iso_month: str) -> str:
    try:
        y, m = iso_month.split("-")
        return f"{_MONTH_LABELS[int(m) - 1]} '{y[2:]}"
    except (ValueError, IndexError):
        return iso_month


def _pipeline_result_to_dict(result: Any) -> dict[str, Any]:
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
    raw = (
        result.transactions
        if hasattr(result, "transactions")
        else result.get("transactions", [])
    )
    out = []
    for t in raw:
        if hasattr(t, "transaction_id"):
            out.append({
                "id": t.transaction_id,
                "date": (
                    t.transaction_date.isoformat()
                    if hasattr(t.transaction_date, "isoformat")
                    else str(t.transaction_date)
                ),
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


def _compute_income_series(
    transactions: list[dict[str, Any]],
) -> tuple[list[str], list[float]]:
    monthly: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.get("is_income") and t.get("amount") is not None:
            date_str = str(t.get("date", ""))[:7]
            # Validate YYYY-MM format strictly to avoid phantom chart entries
            if (len(date_str) == 7 and date_str[4] == "-"
                    and date_str[:4].isdigit() and date_str[5:].isdigit()):
                monthly[date_str] += abs(t["amount"])
    months_iso = sorted(monthly.keys())
    return [_iso_to_month_label(m) for m in months_iso], [monthly[m] for m in months_iso]


def _compute_expense_breakdown(
    transactions: list[dict[str, Any]],
) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for t in transactions:
        if (
            not t.get("is_income")
            and t.get("amount") is not None
            and t["amount"] != 0
        ):
            cat = t.get("category") or "other"
            totals[cat] += abs(t["amount"])
    return dict(sorted(totals.items(), key=lambda x: x[1], reverse=True)[:8])


def _load_review(run_id: str) -> dict[str, Any] | None:
    if not run_id:
        return st.session_state.get("_hitl_review_no_id")
    return _review_store.load(run_id)


def _save_review(run_id: str, review: dict[str, Any]) -> None:
    if run_id:
        _review_store.save(
            run_id=run_id,
            reviewer=review["reviewer"],
            decision=review["decision"],
            notes=review.get("notes", ""),
            ai_recommendation=review.get("ai_recommendation", ""),
            escalation_reasons=review.get("escalation_reasons", []),
            timestamp=review.get("timestamp"),
        )
    else:
        st.session_state["_hitl_review_no_id"] = review


def load_saved_analyses() -> list[Path]:
    reports_dir = ROOT / "reports"
    if not reports_dir.exists():
        return []
    return sorted(reports_dir.glob("**/state_*.json"), reverse=True)


def _kpi_card(
    label: str,
    value: str,
    sub: str,
    sub_class: str,
    accent: str,
) -> str:
    return (
        f'<div class="kpi-card {accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub {sub_class}">{sub}</div>'
        f'</div>'
    )


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div class="brand-header">'
        '<div class="brand-logo">⬡</div>'
        '<div><div class="brand-name">AgentLedger</div>'
        '<div class="brand-tag">Credit Intelligence</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    data_source = st.radio(
        "Mode",
        ["Demo (no API needed)", "Run live analysis", "Load saved analysis"],
        index=0,
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown('<div style="font-size:0.7rem;color:#4a5a78;text-transform:uppercase;letter-spacing:0.08em;font-weight:700;margin-bottom:8px">API Status</div>', unsafe_allow_html=True)

    _checks = [
        ("LLM",   bool(os.environ.get("OPENAI_API_KEY"))),
        ("Plaid", bool(os.environ.get("PLAID_CLIENT_ID") and os.environ.get("PLAID_SECRET"))),
        ("S3",    bool(os.environ.get("AUDIT_S3_BUCKET"))),
        ("DB",    bool(os.environ.get("DATABASE_URL") or os.environ.get("DB_HOST"))),
        ("Tracing", bool(os.environ.get("LANGFUSE_PUBLIC_KEY"))),
    ]
    for _name, _ok in _checks:
        _dot = '<span style="color:#4ade80">●</span>' if _ok else '<span style="color:#2a3a50">●</span>'
        st.markdown(
            f'<div style="font-size:0.78rem;color:#6b7a9a;padding:2px 0">{_dot} {_name}</div>',
            unsafe_allow_html=True,
        )

    if data_source == "Run live analysis" and "live_result" in st.session_state:
        st.divider()
        _rid = str(st.session_state["live_result"][0].get("run_id") or "")
        st.markdown(
            f'<div style="font-size:0.7rem;color:#4f8ef7;font-weight:600">ACTIVE RUN</div>'
            f'<div style="font-size:0.75rem;color:#4a5a78;font-family:monospace">{_rid[:20] or "—"}</div>',
            unsafe_allow_html=True,
        )
        if st.button("🔄 New Analysis", use_container_width=True):
            del st.session_state["live_result"]
            st.rerun()


# ── Data loading ───────────────────────────────────────────────────────────────

state: dict[str, Any] = {}
transactions: list[dict[str, Any]] = []

if data_source == "Demo (no API needed)":
    state = DEMO_STATE
    transactions = DEMO_TRANSACTIONS

elif data_source == "Load saved analysis":
    saved = load_saved_analyses()
    if saved:
        chosen = st.selectbox(
            "Select saved analysis",
            saved,
            format_func=lambda p: f"{p.parent.name} / {p.stem}",
        )
        if chosen:
            try:
                state = json.loads(Path(chosen).read_text())
                transactions = []
            except Exception as exc:
                st.error(f"Could not load file: {exc}")
                st.stop()
    else:
        st.info(
            "No saved analyses found in `reports/`.\n\n"
            "Run via CLI first:\n```\nagentledger analyze --user-id USER_001 --loan-amount 15000\n```"
        )
        st.stop()

else:  # Run live analysis
    has_llm    = bool(os.environ.get("OPENAI_API_KEY"))
    has_plaid  = bool(os.environ.get("PLAID_CLIENT_ID") and os.environ.get("PLAID_SECRET"))
    has_token  = bool(os.environ.get("PLAID_ACCESS_TOKEN"))
    can_run    = has_llm and has_plaid

    if "live_result" not in st.session_state:
        # ── One-click launch panel ─────────────────────────────────────────────
        st.markdown(
            '<div class="hero-panel">'
            '<div class="hero-title">One-Click Credit Analysis</div>'
            '<div class="hero-sub">Ingest → Profile → Categorize → Risk Assess → Validate → Report</div>'
            f'<div style="margin-bottom:24px">'
            f'<span class="preflight-item">{"✅" if has_llm else "❌"} LLM API</span>'
            f'<span class="preflight-item">{"✅" if has_plaid else "❌"} Plaid Credentials</span>'
            f'<span class="preflight-item">{"✅" if has_token else "⚙️"} Access Token</span>'
            f'</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        with st.form("launch_form"):
            fc1, fc2 = st.columns([1, 2])
            with fc1:
                uid   = st.text_input("Borrower ID", value="USER_001")
                token_input = st.text_input(
                    "Plaid Access Token",
                    type="password",
                    placeholder="Leave blank to use .env token",
                ) if not has_token else ""
            with fc2:
                loan_amt = st.number_input(
                    "Loan Amount ($)", min_value=500.0, max_value=2_000_000.0,
                    value=25_000.0, step=1_000.0,
                )
                loan_purpose = st.text_input("Loan Purpose", value="Debt consolidation")

            launch = st.form_submit_button(
                "⚡  Run Complete Analysis",
                disabled=not can_run,
                use_container_width=True,
                type="primary",
            )
            if not can_run:
                st.caption("Add OPENAI_API_KEY and Plaid credentials to your .env file to enable.")

        if launch:
            # ── Step-by-step progress via LangGraph streaming ─────────────────
            from agentledger.schemas.models import WorkflowState

            access_token = token_input.strip() if (not has_token and token_input) else None
            if access_token:
                os.environ["PLAID_ACCESS_TOKEN"] = access_token

            initial = WorkflowState(
                user_id=uid.strip(),
                loan_amount=float(loan_amt),
                loan_purpose=loan_purpose.strip() or None,
            )

            step_placeholder = st.empty()
            completed_steps: list[str] = []
            error_msg: str | None = None
            final_result: Any = None

            with st.status("Running analysis — please wait…", expanded=True) as status_box:
                try:
                    graph = _get_pipeline()
                    for chunk in graph.stream(initial):
                        node_name = list(chunk.keys())[0]
                        num, desc = _PIPELINE_STEPS.get(node_name, ("?", node_name))
                        completed_steps.append(desc)
                        status_box.write(
                            f'<div class="step-row">'
                            f'<span class="step-done">✓</span>'
                            f'<span style="color:#8a9ab5;font-size:0.75rem;width:14px">{num}</span>'
                            f'<span>{desc}</span>'
                            f'</div>',
                        )
                        final_result = chunk[node_name]

                    status_box.update(
                        label="✅ Analysis complete", state="complete", expanded=False
                    )
                except Exception as exc:
                    logger.exception("Pipeline error")
                    error_msg = str(exc)
                    status_box.update(label="❌ Analysis failed", state="error")

            if error_msg:
                st.error(
                    f"**Analysis failed.** The pipeline encountered an error.\n\n"
                    f"> {error_msg}\n\n"
                    f"Check your `.env` credentials and Plaid access token, then try again."
                )
                st.stop()

            if final_result is not None:
                result_state = _pipeline_result_to_dict(final_result)
                result_txns  = _extract_transactions(final_result)
                st.session_state["live_result"] = (result_state, result_txns)
                st.rerun()

        st.stop()

    state, transactions = st.session_state["live_result"]


# ── Guard ──────────────────────────────────────────────────────────────────────

if not state:
    st.info("Select a data source in the sidebar to begin.")
    st.stop()

# ── Unpack state ───────────────────────────────────────────────────────────────

metrics  = state.get("metrics") or {}
ra       = state.get("risk_assessment") or {}
vr       = state.get("validation_result") or {}
rec      = ra.get("recommendation") or "manual_review"
run_id   = str(state.get("run_id") or "")
escalated = bool(state.get("escalate_to_human"))

existing_review = _load_review(run_id)
human_decision  = existing_review["decision"] if existing_review else ""
display_rec     = (
    human_decision if (human_decision and human_decision != "confirm_ai") else rec
)

# ── Page header ────────────────────────────────────────────────────────────────

h1, h2 = st.columns([3, 1])
with h1:
    reviewed_tag = (
        f'<span class="reviewed-tag">✔ {existing_review["reviewer"]}</span>'
        if existing_review else ""
    )
    st.markdown(
        f'<h2 style="margin:0;font-weight:800;letter-spacing:-0.02em;color:#e8edf5">'
        f'{state["user_id"]}{reviewed_tag}</h2>',
        unsafe_allow_html=True,
    )
    loan_str = fmt_currency(state.get("loan_amount", 0))
    purpose  = state.get("loan_purpose") or ""
    rid_str  = run_id[:12] or "demo"
    st.markdown(
        f'<div style="font-size:0.83rem;color:#5a6a8a;margin-top:3px">'
        f'Loan request: <strong style="color:#8a9ab5">{loan_str}</strong>'
        + (f' — {purpose}' if purpose else '')
        + f'&nbsp;&nbsp;·&nbsp;&nbsp;Run <code style="color:#4f8ef7">{rid_str}</code>'
        f'</div>',
        unsafe_allow_html=True,
    )

with h2:
    badge_class = f"rec-{display_rec}"
    badge_label = REC_LABELS.get(display_rec, display_rec.upper())
    human_tag   = (
        '<span class="human-badge">HUMAN</span>'
        if existing_review and human_decision != "confirm_ai" else ""
    )
    pending_tag = (
        '<div style="font-size:0.72rem;color:#fbbf24;margin-top:5px;text-align:right">⚠ Pending review</div>'
        if (escalated and not existing_review) else ""
    )
    st.markdown(
        f'<div style="text-align:right;padding-top:6px">'
        f'<span class="rec-badge {badge_class}">{badge_label}</span>{human_tag}'
        f'{pending_tag}'
        f'</div>',
        unsafe_allow_html=True,
    )

st.divider()

# ── HITL Review Panel ──────────────────────────────────────────────────────────

if escalated:
    _amend_key = f"_hitl_amend_{run_id or 'demo'}"

    if existing_review:
        dl = _REVIEW_DECISION_LABELS.get(existing_review["decision"], existing_review["decision"])
        notes_frag = (
            f'<br><br><span style="color:#9ca3af;font-style:italic">{existing_review["notes"]}</span>'
            if existing_review.get("notes") else ""
        )
        st.markdown(
            f'<div class="hitl-done">'
            f'<strong style="color:#4ade80">✔ Human review complete</strong>'
            f'<span style="color:#4a5a78;font-size:0.75rem;margin-left:10px">'
            f'{existing_review.get("timestamp","")[:19].replace("T"," ")} UTC</span>'
            f'<br><span style="color:#9ca3af">{existing_review["reviewer"]}</span>'
            f'&nbsp;·&nbsp;<strong style="color:#e8edf5">{dl}</strong>'
            f'{notes_frag}'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("✏ Amend review", key=_amend_key):
            st.session_state[_amend_key + "_open"] = True
        show_form = st.session_state.get(_amend_key + "_open", False)
    else:
        reasons_html = "".join(
            f'<li style="color:#fcd34d;margin:3px 0">{r}</li>'
            for r in state.get("escalation_reasons", [])
        )
        st.markdown(
            f'<div class="hitl-pending">'
            f'<strong style="color:#f59e0b">⚠ Escalated for human review</strong>'
            f'<ul style="margin:8px 0 0 0;padding-left:18px">{reasons_html}</ul>'
            f'</div>',
            unsafe_allow_html=True,
        )
        show_form = True

    if show_form:
        ai_label = REC_LABELS.get(rec, rec)
        d_opts   = list(_REVIEW_DECISION_LABELS.keys())
        d_labels = [_REVIEW_DECISION_LABELS[d] for d in d_opts]
        def_idx  = (
            d_opts.index(existing_review["decision"])
            if existing_review and existing_review["decision"] in d_opts else 0
        )
        with st.form(f"hitl_{run_id or 'demo'}"):
            st.markdown(f'<div class="section-title">Submit Human Review</div>', unsafe_allow_html=True)
            rc1, rc2 = st.columns([1, 2])
            with rc1:
                rev_name = st.text_input(
                    "Reviewer",
                    value=existing_review["reviewer"] if existing_review else "",
                    placeholder="Your name",
                )
            with rc2:
                d_idx = st.selectbox(
                    f"Decision (AI: {ai_label})",
                    range(len(d_opts)),
                    format_func=lambda i: d_labels[i],
                    index=def_idx,
                )
            rev_notes = st.text_area(
                "Notes",
                value=existing_review.get("notes", "") if existing_review else "",
                placeholder="Rationale, conditions, or documentation requests…",
                height=90,
            )
            submitted_rev = st.form_submit_button("✔ Submit Review", type="primary")

        if submitted_rev:
            if not rev_name.strip():
                st.error("Reviewer name is required.")
            else:
                _save_review(run_id, {
                    "run_id": run_id,
                    "reviewer": rev_name.strip(),
                    "decision": d_opts[int(d_idx)],
                    "notes": rev_notes.strip(),
                    "ai_recommendation": rec,
                    "escalation_reasons": state.get("escalation_reasons", []),
                })
                st.session_state.pop(_amend_key + "_open", None)
                st.rerun()

    st.divider()

# ── KPI Row ────────────────────────────────────────────────────────────────────

avg_inc  = metrics.get("avg_monthly_income", 0) or 0
dti      = metrics.get("dti_ratio", 0) or 0
nsf      = metrics.get("total_nsf_events", 0) or 0
buf      = metrics.get("cash_buffer_days", 0) or 0
conf     = ra.get("confidence", 0) or 0
score    = ra.get("risk_score", 50) or 50

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.markdown(_kpi_card(
        "Avg Monthly Income", fmt_currency(avg_inc),
        "Primary income stream", "muted", "green"
    ), unsafe_allow_html=True)
with k2:
    dti_ok = dti < 0.36
    st.markdown(_kpi_card(
        "Debt-to-Income", fmt_pct(dti),
        "Good (< 36%)" if dti_ok else "High (≥ 36%)",
        "good" if dti_ok else "bad", "green" if dti_ok else "red"
    ), unsafe_allow_html=True)
with k3:
    st.markdown(_kpi_card(
        "NSF Events", str(nsf),
        "No overdrafts" if nsf == 0 else f"{nsf} overdraft events",
        "good" if nsf == 0 else "bad", "green" if nsf == 0 else "red"
    ), unsafe_allow_html=True)
with k4:
    buf_ok = buf >= 30
    st.markdown(_kpi_card(
        "Cash Buffer", fmt_days(buf),
        "Strong (> 30d)" if buf_ok else "Thin",
        "good" if buf_ok else "warn", "green" if buf_ok else "amber"
    ), unsafe_allow_html=True)
with k5:
    st.markdown(_kpi_card(
        "AI Confidence", fmt_pct(conf),
        "High" if conf >= 0.75 else ("Medium" if conf >= 0.55 else "Low"),
        "good" if conf >= 0.75 else ("warn" if conf >= 0.55 else "bad"),
        "blue"
    ), unsafe_allow_html=True)

st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

# ── Risk Gauge + AI Brief ──────────────────────────────────────────────────────

g1, g2 = st.columns([1, 2])

with g1:
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": "Risk Score", "font": {"size": 13, "color": "#6b7a9a"}},
        number={"font": {"size": 44, "color": risk_color(score)}, "suffix": ""},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#2a3a50"},
            "bar": {"color": risk_color(score), "thickness": 0.22},
            "bgcolor": "#141824",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 30],   "color": "#0d2318"},
                {"range": [30, 60],  "color": "#2d1a03"},
                {"range": [60, 100], "color": "#2d0a0a"},
            ],
            "threshold": {
                "line": {"color": "#e8edf5", "width": 2},
                "thickness": 0.75, "value": score,
            },
        },
    ))
    fig_gauge.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=30, b=5),
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e8edf5",
    )
    st.plotly_chart(fig_gauge, use_container_width=True)
    risk_label = "LOW RISK" if score < 30 else ("MEDIUM RISK" if score < 60 else "HIGH RISK")
    st.markdown(
        f'<div style="text-align:center;color:{risk_color(score)};font-weight:800;'
        f'letter-spacing:0.1em;font-size:0.78rem">{risk_label}</div>',
        unsafe_allow_html=True,
    )

with g2:
    st.markdown('<div class="section-title">AI Analyst Brief</div>', unsafe_allow_html=True)
    st.info(ra.get("reasoning_summary") or "No summary available.")

    validity = vr.get("overall_validity") or 0
    vpass    = vr.get("passed", False)
    halluc   = len(vr.get("hallucinated_claims") or [])

    v1, v2, v3 = st.columns(3)
    with v1:
        color_v = "#4ade80" if validity >= 0.85 else "#f87171"
        st.markdown(
            f'<div style="font-size:0.7rem;color:#6b7a9a;text-transform:uppercase;letter-spacing:0.06em">Citation Validity</div>'
            f'<div style="font-size:1.4rem;font-weight:800;color:{color_v}">{fmt_pct(validity)}</div>',
            unsafe_allow_html=True,
        )
    with v2:
        color_s = "#4ade80" if vpass else "#f87171"
        st.markdown(
            f'<div style="font-size:0.7rem;color:#6b7a9a;text-transform:uppercase;letter-spacing:0.06em">Validation</div>'
            f'<div style="font-size:1.4rem;font-weight:800;color:{color_s}">{"Passed" if vpass else "Failed"}</div>',
            unsafe_allow_html=True,
        )
    with v3:
        color_h = "#4ade80" if halluc == 0 else "#f87171"
        st.markdown(
            f'<div style="font-size:0.7rem;color:#6b7a9a;text-transform:uppercase;letter-spacing:0.06em">Hallucinations</div>'
            f'<div style="font-size:1.4rem;font-weight:800;color:{color_h}">{halluc}</div>',
            unsafe_allow_html=True,
        )

st.divider()

# ── Charts ─────────────────────────────────────────────────────────────────────

c1, c2 = st.columns(2)

with c1:
    st.markdown('<div class="section-title">Monthly Income Trend</div>', unsafe_allow_html=True)
    try:
        months, income_vals = get_monthly_income_series()  # default
        if transactions:
            live_m, live_v = _compute_income_series(transactions)
            if live_m:
                months, income_vals = live_m, live_v
        avg_i = avg_inc

        fig_inc = go.Figure()
        fig_inc.add_trace(go.Scatter(
            x=months, y=income_vals,
            mode="lines+markers",
            line=dict(color="#4f8ef7", width=2.5),
            marker=dict(size=7, color="#4f8ef7", line=dict(color="#0f1117", width=2)),
            fill="tozeroy",
            fillcolor="rgba(79,142,247,0.07)",
            hovertemplate="<b>%{x}</b><br>Income: $%{y:,.0f}<extra></extra>",
        ))
        if avg_i:
            fig_inc.add_hline(
                y=avg_i, line_dash="dot", line_color="#2a3a60",
                annotation_text=f"Avg {fmt_currency(avg_i)}",
                annotation_font_color="#4a5a78",
                annotation_font_size=11,
            )
        fig_inc.update_layout(
            height=260,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e8edf5",
            margin=dict(l=10, r=10, t=5, b=30),
            xaxis=dict(showgrid=False, color="#3a4a60", tickfont_size=11),
            yaxis=dict(
                showgrid=True, gridcolor="#141f30", color="#3a4a60",
                tickprefix="$", tickfont_size=11,
            ),
            showlegend=False,
            hovermode="x unified",
        )
        st.plotly_chart(fig_inc, use_container_width=True)
    except Exception as exc:
        logger.exception("Income chart error")
        st.warning(f"Chart unavailable: {exc}")

with c2:
    st.markdown('<div class="section-title">Expense Breakdown</div>', unsafe_allow_html=True)
    try:
        breakdown = get_expense_breakdown()  # default
        if transactions:
            live_bd = _compute_expense_breakdown(transactions)
            if live_bd:
                breakdown = live_bd
        labels_e = list(breakdown.keys())
        values_e = list(breakdown.values())

        fig_exp = go.Figure(go.Pie(
            labels=labels_e, values=values_e,
            hole=0.58,
            textinfo="label+percent",
            textfont=dict(size=10.5, color="#e8edf5"),
            marker=dict(
                colors=EXPENSE_COLORS[:len(labels_e)],
                line=dict(color="#0f1117", width=2),
            ),
            hovertemplate="<b>%{label}</b><br>$%{value:,.0f} (%{percent})<extra></extra>",
        ))
        avg_exp = metrics.get("avg_monthly_expenses") or 0
        fig_exp.update_layout(
            height=260,
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e8edf5",
            margin=dict(l=0, r=0, t=5, b=5),
            showlegend=False,
            annotations=[dict(
                text=f'<b>{fmt_currency(avg_exp)}</b><br><span style="font-size:9">avg/mo</span>',
                x=0.5, y=0.5, font_size=14, showarrow=False,
                font_color="#8a9ab5",
            )],
        )
        st.plotly_chart(fig_exp, use_container_width=True)
    except Exception as exc:
        logger.exception("Expense chart error")
        st.warning(f"Chart unavailable: {exc}")

# ── Metrics table ──────────────────────────────────────────────────────────────

with st.expander("Full Cash Flow Metrics", expanded=False):
    import pandas as pd
    rows = [
        ("Avg Monthly Income",       fmt_currency(metrics.get("avg_monthly_income")),       "Maximise"),
        ("Avg Monthly Expenses",     fmt_currency(metrics.get("avg_monthly_expenses")),      "Below income"),
        ("Debt-to-Income Ratio",     fmt_pct(metrics.get("dti_ratio")),                      "< 36%"),
        ("Income Stability (CV)",    f'{metrics.get("income_cv", 0):.3f}',                   "< 0.30"),
        ("NSF / Overdraft Events",   str(metrics.get("total_nsf_events", 0)),                "0"),
        ("Cash Buffer Days",         fmt_days(metrics.get("cash_buffer_days")),              "> 30 days"),
        ("Rent-to-Income",           fmt_pct(metrics.get("rent_to_income_ratio")),           "< 33%"),
        ("Discretionary Spend Ratio",fmt_pct(metrics.get("discretionary_spending_ratio")),  "< 40%"),
        ("Months Analyzed",          str(metrics.get("months_analyzed", 0)),                 "6 minimum"),
    ]
    st.dataframe(
        pd.DataFrame(rows, columns=["Metric", "Value", "Benchmark"]),
        use_container_width=True, hide_index=True,
    )

st.divider()

# ── Risk Factors & Strengths ───────────────────────────────────────────────────

rf1, rf2 = st.columns(2)

with rf1:
    st.markdown('<div class="section-title">Risk Factors</div>', unsafe_allow_html=True)
    risk_factors = ra.get("risk_factors") or []
    if not risk_factors:
        st.markdown(
            '<div class="factor-card"><span style="color:#4ade80">✓</span> '
            '<span style="color:#6b7a9a">No significant risk factors identified.</span></div>',
            unsafe_allow_html=True,
        )
    for f in risk_factors:
        sev = f.get("severity", "low")
        sev_colors = {"low": "#4ade80", "medium": "#fbbf24", "high": "#f87171"}
        c = sev_colors.get(sev, "#8a9ab5")
        cites = ", ".join(f.get("citations") or [])
        st.markdown(
            f'<div class="factor-card">'
            f'<span style="color:{c};font-weight:700;font-size:0.7rem;text-transform:uppercase">'
            f'{sev}</span>'
            f'<div style="color:#c8d5e8;margin-top:4px;font-size:0.87rem">{f["description"]}</div>'
            + (f'<div style="color:#3a4a60;font-size:0.72rem;margin-top:4px">{cites}</div>' if cites else "")
            + '</div>',
            unsafe_allow_html=True,
        )

with rf2:
    st.markdown('<div class="section-title">Strengths</div>', unsafe_allow_html=True)
    strengths = ra.get("strengths") or []
    if not strengths:
        st.markdown(
            '<div class="factor-card"><span style="color:#6b7a9a">No strengths identified.</span></div>',
            unsafe_allow_html=True,
        )
    for s in strengths:
        cites = ", ".join(s.get("citations") or [])
        st.markdown(
            f'<div class="factor-card">'
            f'<span style="color:#4ade80;font-size:0.8rem">✓</span>'
            f'<div style="color:#c8d5e8;margin-top:4px;font-size:0.87rem">{s["description"]}</div>'
            + (f'<div style="color:#3a4a60;font-size:0.72rem;margin-top:4px">{cites}</div>' if cites else "")
            + '</div>',
            unsafe_allow_html=True,
        )

st.divider()

# ── Transaction Explorer ───────────────────────────────────────────────────────

st.markdown('<div class="section-title">Transaction Explorer</div>', unsafe_allow_html=True)

if transactions:
    import pandas as pd
    try:
        df = pd.DataFrame([
            {
                "Date":      t.get("date", ""),
                "Merchant":  t.get("merchant", ""),
                "Category":  t.get("category", ""),
                "Amount ($)": t.get("amount", 0),
                "Income":    "✓" if t.get("is_income") else "",
                "Recurring": "✓" if t.get("is_recurring") else "",
            }
            for t in transactions
        ]).sort_values("Date", ascending=False)

        sr1, sr2, sr3 = st.columns([2, 1, 1])
        with sr1:
            search = st.text_input("Search", placeholder="Merchant or category…", label_visibility="collapsed")
        with sr2:
            cats = ["All categories"] + sorted(df["Category"].unique().tolist())
            cat_filter = st.selectbox("Category", cats, label_visibility="collapsed")
        with sr3:
            inc_filter = st.selectbox("Type", ["All", "Income only", "Expenses only"], label_visibility="collapsed")

        if search:
            mask = (
                df["Merchant"].str.contains(search, case=False, na=False)
                | df["Category"].str.contains(search, case=False, na=False)
            )
            df = df[mask]
        if cat_filter != "All categories":
            df = df[df["Category"] == cat_filter]
        if inc_filter == "Income only":
            df = df[df["Income"] == "✓"]
        elif inc_filter == "Expenses only":
            df = df[df["Income"] == ""]

        def _color_amt(val: float) -> str:
            return "color: #4ade80; font-weight:600" if val > 0 else "color: #f87171"

        st.dataframe(
            df.style.map(_color_amt, subset=["Amount ($)"]).format({"Amount ($)": "${:,.2f}"}),
            use_container_width=True,
            hide_index=True,
            height=300,
        )
        st.caption(f"{len(df):,} transactions shown")
    except Exception as exc:
        logger.exception("Transaction table error")
        st.warning(f"Transaction table unavailable: {exc}")
else:
    st.markdown(
        '<div style="color:#3a4a60;font-size:0.85rem;padding:16px 0">'
        'Transaction detail not available for this analysis.</div>',
        unsafe_allow_html=True,
    )

st.divider()

# ── Audit panel ────────────────────────────────────────────────────────────────

with st.expander("Audit & Run Details", expanded=False):
    aa1, aa2, aa3 = st.columns(3)
    aa1.markdown(f"**Run ID**\n\n`{run_id or 'N/A'}`")
    aa2.markdown(f"**Retries**\n\n{state.get('retry_count', 0)}")
    aa3.markdown(f"**Report**\n\n`{state.get('final_report_path') or '—'}`")

    if escalated:
        reasons = state.get("escalation_reasons") or []
        st.warning("**Escalation reasons:** " + " · ".join(reasons))
    if existing_review:
        dl = _REVIEW_DECISION_LABELS.get(
            existing_review["decision"], existing_review["decision"]
        )
        st.info(
            f"**Human review:** {existing_review['reviewer']} · {dl} · "
            f"{existing_review.get('timestamp','')[:19].replace('T',' ')} UTC"
        )

# ── Footer ─────────────────────────────────────────────────────────────────────

st.markdown(
    '<div style="text-align:center;color:#1e2a3a;font-size:0.72rem;padding:20px 0 8px">'
    'AgentLedger · Metrics computed deterministically in Python · '
    'LLM used only for interpretation · Every claim citation-validated'
    '</div>',
    unsafe_allow_html=True,
)
