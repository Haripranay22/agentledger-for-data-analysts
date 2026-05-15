"""
Credit Memo Generator — Jinja2 template → Markdown → PDF.

Produces audit-ready memos with:
  - Executive Summary
  - Cash Flow Analysis
  - Risk Factors
  - Strengths
  - Recommendation
  - Methodology
  - Audit Trail

TODO Week 3: implement full template + WeasyPrint PDF export.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentledger.schemas.models import CashFlowMetrics, RiskAssessment, WorkflowState


MEMO_TEMPLATE = """# Credit Analysis Memo
**Borrower ID:** {{ state.user_id }}
**Run ID:** {{ state.run_id }}
**Generated:** {{ generated_at }}
**Loan Request:** ${{ "%.0f"|format(state.loan_amount) }}{% if state.loan_purpose %} — {{ state.loan_purpose }}{% endif %}

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


class MemoGenerator:
    """Generate credit analysis memos from workflow state."""

    def generate_markdown(self, state: "WorkflowState") -> str:
        """Render Jinja2 template to Markdown string."""
        from datetime import datetime, timezone
        from jinja2 import Template

        template = Template(MEMO_TEMPLATE)
        return template.render(
            state=state,
            metrics=state.metrics,
            risk_assessment=state.risk_assessment,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )

    def save(self, state: "WorkflowState", output_dir: Path) -> Path:
        """Save memo as .md and return the path."""
        output_dir.mkdir(parents=True, exist_ok=True)
        md = self.generate_markdown(state)
        path = output_dir / f"memo_{state.user_id}_{state.run_id[:8]}.md"
        path.write_text(md, encoding="utf-8")
        return path
