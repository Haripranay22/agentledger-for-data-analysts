"""
Credit Memo Generator — Jinja2 template → Markdown + PDF.

Produces audit-ready memos with:
  - Executive Summary
  - Cash Flow Analysis
  - Risk Factors
  - Strengths
  - Recommendation
  - Methodology
  - Audit Trail
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentledger.schemas.models import WorkflowState

logger = logging.getLogger(__name__)

# ── Markdown template ──────────────────────────────────────────────────────────

MEMO_TEMPLATE = """# Credit Analysis Memo
**Borrower ID:** {{ state.user_id }}
**Run ID:** {{ state.run_id }}
**Generated:** {{ generated_at }}
**Loan Request:** ${{ "%.0f"|format(state.loan_amount) }}
{%- if state.loan_purpose %} — {{ state.loan_purpose }}{% endif %}

---

## Executive Summary
{{ risk_assessment.reasoning_summary }}

**Decision:** {{ risk_assessment.recommendation | upper | replace("_", " ") }}
**Risk Score:** {{ risk_assessment.risk_score }} / 100
**Confidence:** {{ "%.0f%%"|format(risk_assessment.confidence * 100) }}

---

## Cash Flow Analysis
| Metric | Value |
|--------|-------|
| Avg Monthly Income | ${{ "%.0f"|format(metrics.avg_monthly_income) }} |
| Avg Monthly Expenses | ${{ "%.0f"|format(metrics.avg_monthly_expenses) }} |
| Debt-to-Income Ratio | {{ "%.1f%%"|format(metrics.dti_ratio * 100) }} |
| Income Stability (CV) | {{ "%.3f"|format(metrics.income_cv) }} |
| NSF Events | {{ metrics.total_nsf_events }} |
| Cash Buffer Days | {{ "%.0f"|format(metrics.cash_buffer_days) }} |
| Rent-to-Income Ratio | {{ "%.1f%%"|format(metrics.rent_to_income_ratio * 100) }} |
| Discretionary Ratio | {{ "%.1f%%"|format(metrics.discretionary_spending_ratio * 100) }} |

---

## Risk Factors
{% for factor in risk_assessment.risk_factors %}
**[{{ factor.severity | upper }}]** {{ factor.description }}
_Citations: {{ factor.citations | join(", ") }}_

{% endfor %}

## Strengths
{% for strength in risk_assessment.strengths %}
**{{ strength.description }}**
_Citations: {{ strength.citations | join(", ") }}_

{% endfor %}

---

## Recommendation
**{{ risk_assessment.recommendation | upper | replace("_", " ") }}**

{% if state.escalate_to_human %}
⚠️ **Escalated for Human Review:** {{ state.escalation_reasons | join("; ") }}
{% endif %}

---

## Methodology
All financial metrics computed deterministically in Python + dbt SQL.
LLM used only for risk interpretation — not arithmetic.
Every claim validated against source transaction data.

## Audit
Full audit trail: `logs/audit/run_{{ state.run_id }}.jsonl`
"""

# ── HTML template for PDF export ───────────────────────────────────────────────

HTML_MEMO_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
@page {
  margin: 2.2cm 2.5cm;
  size: A4;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 10.5pt;
  color: #1a1a2e;
  line-height: 1.55;
}
.header {
  border-bottom: 3px solid #1e3a8a;
  padding-bottom: 10px;
  margin-bottom: 16px;
}
.header h1 {
  font-size: 18pt;
  color: #1e3a8a;
  margin-bottom: 4px;
}
.meta {
  font-size: 9pt;
  color: #64748b;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
}
h2 {
  font-size: 12pt;
  color: #1e3a8a;
  border-left: 4px solid #2563eb;
  padding-left: 8px;
  margin: 18px 0 8px 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0 14px 0;
  font-size: 10pt;
}
th {
  background: #1e3a8a;
  color: white;
  padding: 6px 10px;
  text-align: left;
  font-weight: 600;
}
td { padding: 5px 10px; border-bottom: 1px solid #e2e8f0; }
tr:nth-child(even) td { background: #f8fafc; }
.decision-box {
  border: 2px solid;
  border-radius: 6px;
  padding: 12px 16px;
  margin: 12px 0;
  display: flex;
  gap: 20px;
  align-items: center;
}
.decision-approve              { border-color: #16a34a; background: #f0fdf4; }
.decision-approve_with_conditions { border-color: #d97706; background: #fffbeb; }
.decision-manual_review        { border-color: #2563eb; background: #eff6ff; }
.decision-decline              { border-color: #dc2626; background: #fef2f2; }
.decision-approve .rec-label              { color: #16a34a; }
.decision-approve_with_conditions .rec-label { color: #d97706; }
.decision-manual_review .rec-label        { color: #2563eb; }
.decision-decline .rec-label             { color: #dc2626; }
.rec-label { font-size: 14pt; font-weight: 700; }
.score-box { text-align: center; min-width: 70px; }
.score-num { font-size: 26pt; font-weight: 700; color: {{ score_color }}; }
.score-sub { font-size: 8pt; color: #64748b; }
.summary-text { font-size: 10.5pt; line-height: 1.6; flex: 1; }
.factor {
  margin: 7px 0;
  padding: 7px 12px;
  background: #f8fafc;
  border-left: 3px solid #cbd5e1;
  border-radius: 0 4px 4px 0;
}
.sev-low    { color: #16a34a; font-weight: 700; font-size: 9pt; }
.sev-medium { color: #d97706; font-weight: 700; font-size: 9pt; }
.sev-high   { color: #dc2626; font-weight: 700; font-size: 9pt; }
.citation { font-size: 8.5pt; color: #64748b; margin-top: 2px; }
.escalation {
  background: #fff7ed;
  border: 1px solid #f97316;
  border-radius: 4px;
  padding: 8px 12px;
  margin: 10px 0;
  font-size: 10pt;
  color: #9a3412;
}
.methodology {
  font-size: 9pt;
  color: #64748b;
  border-top: 1px solid #e2e8f0;
  padding-top: 12px;
  margin-top: 18px;
}
.footer {
  font-size: 8pt;
  color: #94a3b8;
  text-align: center;
  margin-top: 20px;
  border-top: 1px solid #e2e8f0;
  padding-top: 8px;
}
hr { border: none; border-top: 1px solid #e2e8f0; margin: 14px 0; }
</style>
</head>
<body>

<div class="header">
  <h1>Credit Analysis Memo</h1>
  <div class="meta">
    <span><strong>Borrower ID:</strong> {{ state.user_id }}</span>
    <span><strong>Run ID:</strong> {{ state.run_id }}</span>
    <span><strong>Generated:</strong> {{ generated_at }}</span>
    <span><strong>Loan Request:</strong>
      ${{ "%.0f"|format(state.loan_amount) }}
      {%- if state.loan_purpose %} — {{ state.loan_purpose }}{% endif %}
    </span>
  </div>
</div>

<h2>Executive Summary</h2>

<div class="decision-box decision-{{ risk_assessment.recommendation }}">
  <div class="score-box">
    <div class="score-num">{{ risk_assessment.risk_score }}</div>
    <div class="score-sub">Risk Score</div>
  </div>
  <div class="summary-text">
    <div class="rec-label">
      {{ risk_assessment.recommendation | upper | replace("_", " ") }}
    </div>
    <div style="margin-top: 5px">{{ risk_assessment.reasoning_summary }}</div>
    <div style="font-size:9pt; color:#64748b; margin-top:6px">
      Confidence: {{ "%.0f%%"|format(risk_assessment.confidence * 100) }}
    </div>
  </div>
</div>

{% if state.escalate_to_human %}
<div class="escalation">
  ⚠️ <strong>Escalated for Human Review:</strong>
  {{ state.escalation_reasons | join("; ") }}
</div>
{% endif %}

<h2>Cash Flow Analysis</h2>
<table>
  <thead>
    <tr>
      <th>Metric</th>
      <th>Value</th>
      <th>Benchmark</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Avg Monthly Income</td>
        <td>${{ "%.0f"|format(metrics.avg_monthly_income) }}</td>
        <td>—</td></tr>
    <tr><td>Avg Monthly Expenses</td>
        <td>${{ "%.0f"|format(metrics.avg_monthly_expenses) }}</td>
        <td>Below income</td></tr>
    <tr><td>Debt-to-Income Ratio</td>
        <td>{{ "%.1f%%"|format(metrics.dti_ratio * 100) }}</td>
        <td>Good &lt; 36%</td></tr>
    <tr><td>Income Stability (CV)</td>
        <td>{{ "%.3f"|format(metrics.income_cv) }}</td>
        <td>Good &lt; 0.30</td></tr>
    <tr><td>NSF Events</td>
        <td>{{ metrics.total_nsf_events }}</td>
        <td>Target: 0</td></tr>
    <tr><td>Cash Buffer Days</td>
        <td>{{ "%.0f"|format(metrics.cash_buffer_days) }} days</td>
        <td>Good &gt; 30</td></tr>
    <tr><td>Rent-to-Income Ratio</td>
        <td>{{ "%.1f%%"|format(metrics.rent_to_income_ratio * 100) }}</td>
        <td>Good &lt; 33%</td></tr>
    <tr><td>Discretionary Ratio</td>
        <td>{{ "%.1f%%"|format(metrics.discretionary_spending_ratio * 100) }}</td>
        <td>Good &lt; 40%</td></tr>
    <tr><td>Months Analyzed</td>
        <td>{{ metrics.months_analyzed }}</td>
        <td>Standard: 6</td></tr>
  </tbody>
</table>

<h2>Risk Factors</h2>
{% if risk_assessment.risk_factors %}
  {% for factor in risk_assessment.risk_factors %}
  <div class="factor">
    <span class="sev-{{ factor.severity }}">[{{ factor.severity | upper }}]</span>
    {{ factor.description }}
    {% if factor.citations %}
    <div class="citation">Citations: {{ factor.citations | join(", ") }}</div>
    {% endif %}
  </div>
  {% endfor %}
{% else %}
  <p style="color:#16a34a">No significant risk factors identified.</p>
{% endif %}

<h2>Strengths</h2>
{% if risk_assessment.strengths %}
  {% for strength in risk_assessment.strengths %}
  <div class="factor" style="border-left-color: #16a34a;">
    {{ strength.description }}
    {% if strength.citations %}
    <div class="citation">Citations: {{ strength.citations | join(", ") }}</div>
    {% endif %}
  </div>
  {% endfor %}
{% else %}
  <p style="color:#64748b">No strengths noted.</p>
{% endif %}

<hr>

<div class="methodology">
  <strong>Methodology:</strong> All financial metrics computed deterministically
  in Python + dbt SQL.
  LLM used only for risk interpretation — not arithmetic.
  Every claim validated against source transaction data (citation validity:
  {{ "%.0f%%"|format((validation_validity or 0) * 100) }}).
  Full audit trail: <code>logs/audit/run_{{ state.run_id }}.jsonl</code>
</div>

<div class="footer">
  AgentLedger Credit Analysis — CONFIDENTIAL —
  Generated {{ generated_at }} — Run {{ state.run_id }}
</div>

</body>
</html>
"""


def _score_color(score: int) -> str:
    if score < 30:
        return "#16a34a"
    if score < 60:
        return "#d97706"
    return "#dc2626"


class MemoGenerator:
    """Generate credit analysis memos from workflow state."""

    def _render_context(self, state: WorkflowState) -> dict[str, Any]:
        ra = state.risk_assessment
        vr = state.validation_result
        return {
            "state": state,
            "metrics": state.metrics,
            "risk_assessment": ra,
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            "score_color": _score_color(ra.risk_score) if ra else "#64748b",
            "validation_validity": vr.overall_validity if vr else None,
        }

    def generate_markdown(self, state: WorkflowState) -> str:
        """Render Jinja2 template to Markdown string."""
        from jinja2 import Template

        return Template(MEMO_TEMPLATE).render(**self._render_context(state))

    def generate_html(self, state: WorkflowState) -> str:
        """Render HTML memo for PDF conversion."""
        from jinja2 import Template

        return Template(HTML_MEMO_TEMPLATE).render(**self._render_context(state))

    def save_pdf(self, state: WorkflowState, output_dir: Path) -> Path | None:
        """Render HTML → PDF via WeasyPrint. Returns path or None on failure."""
        try:
            from weasyprint import HTML  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("WeasyPrint not installed — PDF export skipped. pip install weasyprint")
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        html_str = self.generate_html(state)
        run_id = (state.run_id or "unknown")[:8]
        pdf_path = output_dir / f"memo_{state.user_id}_{run_id}.pdf"

        try:
            HTML(string=html_str).write_pdf(str(pdf_path))
            logger.info("[report] PDF written: %s", pdf_path)
            return pdf_path
        except Exception as exc:
            logger.warning("[report] PDF generation failed: %s", exc)
            return None

    def save(self, state: WorkflowState, output_dir: Path) -> Path:
        """Save memo as .md (always) and .pdf (if WeasyPrint available)."""
        output_dir.mkdir(parents=True, exist_ok=True)
        md = self.generate_markdown(state)
        run_id = (state.run_id or "unknown")[:8]
        md_path = output_dir / f"memo_{state.user_id}_{run_id}.md"
        md_path.write_text(md, encoding="utf-8")
        self.save_pdf(state, output_dir)
        return md_path
