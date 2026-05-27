"""
Credit Memo Generator — Jinja2 template → Markdown + PDF.

Produces audit-ready memos with:
  - Executive Summary
  - Cash Flow Analysis
  - Risk Factors & Strengths
  - Recommendation
  - Methodology & Audit Trail
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentledger.schemas.models import WorkflowState


# ── Markdown template ──────────────────────────────────────────────────────────

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


# ── HTML template (WeasyPrint → PDF) ──────────────────────────────────────────

_DECISION_STYLES = {
    "approve":                 ("#16a34a", "#dcfce7", "APPROVE"),
    "approve_with_conditions": ("#d97706", "#fef3c7", "APPROVE WITH CONDITIONS"),
    "decline":                 ("#dc2626", "#fee2e2", "DECLINE"),
    "manual_review":           ("#7c3aed", "#ede9fe", "MANUAL REVIEW"),
}

_SEVERITY_COLORS = {
    "low":    "#16a34a",
    "medium": "#d97706",
    "high":   "#dc2626",
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {
    size: A4;
    margin: 18mm 20mm 18mm 20mm;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 9.5pt;
    color: #1e293b;
    line-height: 1.5;
  }

  /* ── Header ─────────────────────────────────────────────── */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-bottom: 2.5px solid #1e293b;
    padding-bottom: 10px;
    margin-bottom: 18px;
  }
  .brand { font-size: 18pt; font-weight: 700; letter-spacing: -0.5px; color: #1e293b; }
  .brand span { color: #2563eb; }
  .meta { text-align: right; color: #64748b; font-size: 8pt; line-height: 1.8; }
  .meta strong { color: #1e293b; }

  /* ── Decision banner ─────────────────────────────────────── */
  .decision-banner {
    padding: 12px 18px;
    border-radius: 5px;
    border-left: 6px solid {{ dec_border }};
    background: {{ dec_bg }};
    margin-bottom: 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .decision-label {
    font-size: 16pt;
    font-weight: 700;
    color: {{ dec_border }};
    letter-spacing: 0.3px;
  }
  .decision-meta { text-align: right; color: #475569; font-size: 8.5pt; line-height: 1.8; }

  /* ── Risk score bar ──────────────────────────────────────── */
  .score-row { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
  .score-track {
    flex: 1;
    height: 14px;
    background: linear-gradient(to right, #dcfce7 0%, #fef3c7 35%, #fee2e2 65%);
    border-radius: 7px;
    position: relative;
  }
  .score-needle {
    position: absolute;
    top: -3px;
    width: 4px;
    height: 20px;
    background: #1e293b;
    border-radius: 2px;
    left: {{ score_pct }}%;
    transform: translateX(-50%);
  }
  .score-label { font-size: 20pt; font-weight: 700; color: #1e293b; min-width: 70px; text-align: right; }
  .score-caption { font-size: 8pt; color: #64748b; min-width: 100px; }

  /* ── Section headings ────────────────────────────────────── */
  h2 {
    font-size: 11pt;
    font-weight: 700;
    color: #1e293b;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
    margin: 18px 0 10px;
  }

  /* ── Metrics table ───────────────────────────────────────── */
  table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 6px;
  }
  th {
    background: #f1f5f9;
    text-align: left;
    padding: 5px 10px;
    font-size: 8.5pt;
    color: #475569;
    font-weight: 600;
  }
  td {
    padding: 5px 10px;
    border-bottom: 1px solid #f1f5f9;
    font-size: 9pt;
  }
  tr:last-child td { border-bottom: none; }
  td.value { font-weight: 600; text-align: right; }
  td.flag-ok   { color: #16a34a; font-weight: 700; text-align: right; }
  td.flag-warn { color: #d97706; font-weight: 700; text-align: right; }
  td.flag-bad  { color: #dc2626; font-weight: 700; text-align: right; }

  /* ── Two-column layout ───────────────────────────────────── */
  .two-col { display: flex; gap: 20px; }
  .two-col > div { flex: 1; }

  /* ── Risk factor cards ───────────────────────────────────── */
  .factor-card {
    border-left: 4px solid #e2e8f0;
    padding: 7px 10px;
    margin-bottom: 8px;
    background: #fafafa;
    border-radius: 0 4px 4px 0;
  }
  .factor-card.high   { border-left-color: #dc2626; }
  .factor-card.medium { border-left-color: #d97706; }
  .factor-card.low    { border-left-color: #16a34a; }
  .factor-card.strength { border-left-color: #2563eb; background: #eff6ff; }

  .severity-badge {
    display: inline-block;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 3px;
    margin-bottom: 3px;
    color: white;
  }
  .badge-high   { background: #dc2626; }
  .badge-medium { background: #d97706; }
  .badge-low    { background: #16a34a; }
  .badge-strength { background: #2563eb; }

  .factor-desc { font-size: 9pt; color: #1e293b; margin-bottom: 3px; }
  .citations { font-size: 7.5pt; color: #94a3b8; font-style: italic; }

  /* ── Escalation box ──────────────────────────────────────── */
  .escalation-box {
    background: #fef3c7;
    border: 1px solid #fbbf24;
    border-radius: 4px;
    padding: 8px 12px;
    margin: 10px 0;
    font-size: 8.5pt;
    color: #92400e;
  }

  /* ── Executive summary ───────────────────────────────────── */
  .summary-text {
    background: #f8fafc;
    border-left: 4px solid #2563eb;
    padding: 10px 14px;
    border-radius: 0 4px 4px 0;
    font-size: 9.5pt;
    color: #334155;
    line-height: 1.6;
  }

  /* ── Footer ──────────────────────────────────────────────── */
  .footer {
    margin-top: 24px;
    padding-top: 10px;
    border-top: 1px solid #e2e8f0;
    font-size: 7.5pt;
    color: #94a3b8;
    display: flex;
    justify-content: space-between;
  }
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div class="brand">Agent<span>Ledger</span></div>
  <div class="meta">
    <strong>Borrower ID:</strong> {{ state.user_id }}<br>
    <strong>Run ID:</strong> {{ state.run_id }}<br>
    <strong>Generated:</strong> {{ generated_at }}
  </div>
</div>

<!-- Loan info line -->
<p style="color:#64748b;font-size:8.5pt;margin-bottom:14px;">
  <strong style="color:#1e293b;">Loan Request:</strong>
  ${{ "%.0f"|format(state.loan_amount) }}
  {% if state.loan_purpose %} &mdash; {{ state.loan_purpose }}{% endif %}
</p>

<!-- Decision banner -->
<div class="decision-banner {{ dec_class }}">
  <div class="decision-label">{{ dec_label }}</div>
  <div class="decision-meta">
    Risk Score: <strong>{{ risk_assessment.risk_score }} / 100</strong><br>
    Confidence: <strong>{{ "%.0f%%"|format(risk_assessment.confidence * 100) }}</strong>
  </div>
</div>

<!-- Risk score bar -->
<div class="score-row">
  <div style="font-size:8pt;color:#64748b;min-width:80px;">Low Risk</div>
  <div class="score-track">
    <div class="score-needle"></div>
  </div>
  <div style="font-size:8pt;color:#64748b;min-width:80px;text-align:right;">High Risk</div>
  <div class="score-label">{{ risk_assessment.risk_score }}</div>
  <div class="score-caption" style="font-size:8pt;color:#64748b;">/ 100</div>
</div>

<!-- Executive summary -->
<h2>Executive Summary</h2>
<div class="summary-text">{{ risk_assessment.reasoning_summary }}</div>

<!-- Cash flow metrics -->
<h2>Cash Flow Analysis</h2>
<table>
  <tr>
    <th>Metric</th>
    <th style="text-align:right;">Value</th>
    <th style="text-align:right;">Signal</th>
  </tr>
  <tr>
    <td>Avg Monthly Income</td>
    <td class="value">${{ "%.0f"|format(metrics.avg_monthly_income) }}</td>
    <td class="flag-ok">—</td>
  </tr>
  <tr>
    <td>Avg Monthly Expenses</td>
    <td class="value">${{ "%.0f"|format(metrics.avg_monthly_expenses) }}</td>
    <td class="flag-ok">—</td>
  </tr>
  <tr>
    <td>Debt-to-Income Ratio</td>
    <td class="value">{{ "%.1f%%"|format(metrics.dti_ratio * 100) }}</td>
    <td class="{{ 'flag-ok' if metrics.dti_ratio < 0.36 else 'flag-warn' if metrics.dti_ratio < 0.50 else 'flag-bad' }}">
      {{ '✓ Good' if metrics.dti_ratio < 0.36 else '⚠ Elevated' if metrics.dti_ratio < 0.50 else '✗ High' }}
    </td>
  </tr>
  <tr>
    <td>Income Stability (CV)</td>
    <td class="value">{{ "%.3f"|format(metrics.income_cv) }}</td>
    <td class="{{ 'flag-ok' if metrics.income_cv < 0.15 else 'flag-warn' if metrics.income_cv < 0.30 else 'flag-bad' }}">
      {{ '✓ Stable' if metrics.income_cv < 0.15 else '⚠ Variable' if metrics.income_cv < 0.30 else '✗ Volatile' }}
    </td>
  </tr>
  <tr>
    <td>NSF / Overdraft Events</td>
    <td class="value">{{ metrics.total_nsf_events }}</td>
    <td class="{{ 'flag-ok' if metrics.total_nsf_events == 0 else 'flag-warn' if metrics.total_nsf_events <= 2 else 'flag-bad' }}">
      {{ '✓ None' if metrics.total_nsf_events == 0 else '⚠ ' ~ metrics.total_nsf_events ~ ' event(s)' }}
    </td>
  </tr>
  <tr>
    <td>Cash Buffer Days</td>
    <td class="value">{{ "%.0f"|format(metrics.cash_buffer_days) }} days</td>
    <td class="{{ 'flag-ok' if metrics.cash_buffer_days > 15 else 'flag-warn' if metrics.cash_buffer_days > 0 else 'flag-bad' }}">
      {{ '✓ Healthy' if metrics.cash_buffer_days > 15 else '⚠ Thin' if metrics.cash_buffer_days > 0 else '✗ Negative' }}
    </td>
  </tr>
  <tr>
    <td>Rent-to-Income Ratio</td>
    <td class="value">{{ "%.1f%%"|format(metrics.rent_to_income_ratio * 100) }}</td>
    <td class="{{ 'flag-ok' if metrics.rent_to_income_ratio < 0.30 else 'flag-warn' if metrics.rent_to_income_ratio < 0.40 else 'flag-bad' }}">
      {{ '✓ Low' if metrics.rent_to_income_ratio < 0.30 else '⚠ Moderate' if metrics.rent_to_income_ratio < 0.40 else '✗ High' }}
    </td>
  </tr>
  <tr>
    <td>Discretionary Spending Ratio</td>
    <td class="value">{{ "%.1f%%"|format(metrics.discretionary_spending_ratio * 100) }}</td>
    <td class="flag-ok">—</td>
  </tr>
</table>

{% if state.escalate_to_human %}
<div class="escalation-box">
  ⚠ <strong>Escalated for Human Review:</strong> {{ state.escalation_reasons | join(" &bull; ") }}
</div>
{% endif %}

<!-- Risk factors + Strengths -->
<div class="two-col">
  <div>
    <h2>Risk Factors</h2>
    {% if risk_assessment.risk_factors %}
      {% for factor in risk_assessment.risk_factors %}
      <div class="factor-card {{ factor.severity }}">
        <span class="severity-badge badge-{{ factor.severity }}">{{ factor.severity | upper }}</span>
        <div class="factor-desc">{{ factor.description }}</div>
        <div class="citations">{{ factor.citations | join(", ") }}</div>
      </div>
      {% endfor %}
    {% else %}
      <p style="color:#94a3b8;font-size:8.5pt;">No significant risk factors identified.</p>
    {% endif %}
  </div>

  <div>
    <h2>Strengths</h2>
    {% if risk_assessment.strengths %}
      {% for strength in risk_assessment.strengths %}
      <div class="factor-card strength">
        <span class="severity-badge badge-strength">STRENGTH</span>
        <div class="factor-desc">{{ strength.description }}</div>
        <div class="citations">{{ strength.citations | join(", ") }}</div>
      </div>
      {% endfor %}
    {% else %}
      <p style="color:#94a3b8;font-size:8.5pt;">No notable strengths identified.</p>
    {% endif %}
  </div>
</div>

<!-- Methodology -->
<h2>Methodology & Audit</h2>
<table>
  <tr>
    <th style="width:30%;">Component</th>
    <th>Details</th>
  </tr>
  <tr>
    <td>Metrics Engine</td>
    <td>All 8 cash-flow metrics computed deterministically in Python + dbt SQL. LLM never performs arithmetic.</td>
  </tr>
  <tr>
    <td>Transaction Categorizer</td>
    <td>TF-IDF + RandomForest (ML). LLM fallback used only when ML confidence &lt; 70%.</td>
  </tr>
  <tr>
    <td>Risk Assessment</td>
    <td>GPT-OSS 120B via OpenRouter. Every claim must cite source transaction_ids.</td>
  </tr>
  <tr>
    <td>Citation Validator</td>
    <td>All cited transaction IDs cross-referenced against source data. Validity threshold: 85%.</td>
  </tr>
  <tr>
    <td>Audit Trail</td>
    <td>logs/audit/run_{{ state.run_id }}.jsonl</td>
  </tr>
</table>

<!-- Footer -->
<div class="footer">
  <span>AgentLedger &mdash; AI-Augmented Credit Analysis</span>
  <span>Run ID: {{ state.run_id }} &nbsp;|&nbsp; {{ generated_at }}</span>
</div>

</body>
</html>"""


# ── MemoGenerator ──────────────────────────────────────────────────────────────

class MemoGenerator:
    """Generate credit analysis memos as Markdown and PDF."""

    def generate_markdown(self, state: WorkflowState) -> str:
        from datetime import datetime

        from jinja2 import Template

        template = Template(MEMO_TEMPLATE)
        return template.render(
            state=state,
            metrics=state.metrics,
            risk_assessment=state.risk_assessment,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        )

    def generate_html(self, state: WorkflowState) -> str:
        from datetime import datetime

        from jinja2 import Template

        rec = state.risk_assessment.recommendation if state.risk_assessment else "manual_review"
        dec_border, dec_bg, dec_label = _DECISION_STYLES.get(
            rec, ("#374151", "#f3f4f6", rec.replace("_", " ").upper())
        )
        dec_class = f"decision-{rec}"
        score = state.risk_assessment.risk_score if state.risk_assessment else 50
        score_pct = max(2, min(98, score))  # keep needle inside track

        template = Template(HTML_TEMPLATE)
        return template.render(
            state=state,
            metrics=state.metrics,
            risk_assessment=state.risk_assessment,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            dec_border=dec_border,
            dec_bg=dec_bg,
            dec_label=dec_label,
            dec_class=dec_class,
            score_pct=score_pct,
        )

    def save(self, state: WorkflowState, output_dir: Path) -> tuple[Path, Path | None]:
        """
        Save memo as .md and .pdf.
        Returns (md_path, pdf_path). pdf_path is None if WeasyPrint is unavailable.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = f"memo_{state.user_id}_{(state.run_id or 'no-run-id')[:8]}"

        md_path = output_dir / f"{stem}.md"
        md_path.write_text(self.generate_markdown(state), encoding="utf-8")

        pdf_path = self._save_pdf(state, output_dir / f"{stem}.pdf")
        return md_path, pdf_path

    def _save_pdf(self, state: WorkflowState, pdf_path: Path) -> Path | None:
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_RIGHT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                HRFlowable,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError:
            return None

        from datetime import datetime

        ra = state.risk_assessment
        m = state.metrics
        if ra is None or m is None:
            return None

        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        # ── Color palette ───────────────────────────────────────────────────────
        _DEC_FG = {
            "approve":                 colors.HexColor("#16a34a"),
            "approve_with_conditions": colors.HexColor("#d97706"),
            "decline":                 colors.HexColor("#dc2626"),
            "manual_review":           colors.HexColor("#7c3aed"),
        }
        _DEC_BG = {
            "approve":                 colors.HexColor("#dcfce7"),
            "approve_with_conditions": colors.HexColor("#fef3c7"),
            "decline":                 colors.HexColor("#fee2e2"),
            "manual_review":           colors.HexColor("#ede9fe"),
        }
        _DEC_LABEL = {
            "approve":                 "APPROVE",
            "approve_with_conditions": "APPROVE WITH CONDITIONS",
            "decline":                 "DECLINE",
            "manual_review":           "MANUAL REVIEW",
        }
        _SEV_FG = {
            "low":    colors.HexColor("#16a34a"),
            "medium": colors.HexColor("#d97706"),
            "high":   colors.HexColor("#dc2626"),
        }
        SLATE  = colors.HexColor("#1e293b")
        MUTED  = colors.HexColor("#64748b")
        BORDER = colors.HexColor("#e2e8f0")
        BLUE   = colors.HexColor("#2563eb")
        BG     = colors.HexColor("#f8fafc")

        rec = ra.recommendation
        dec_fg = _DEC_FG.get(rec, SLATE)
        dec_bg = _DEC_BG.get(rec, BG)
        dec_label = _DEC_LABEL.get(rec, rec.replace("_", " ").upper())

        # ── Styles ──────────────────────────────────────────────────────────────
        base = getSampleStyleSheet()

        def sty(name, parent="Normal", **kw):  # type: ignore[no-untyped-def]
            return ParagraphStyle(name, parent=base[parent], **kw)

        S = {
            "brand":    sty("brand",    fontSize=18, textColor=SLATE,
                            fontName="Helvetica-Bold", leading=22),
            "meta":     sty("meta",     fontSize=8,  textColor=MUTED, leading=12),
            "h2":       sty("h2",       fontSize=11, textColor=SLATE,
                            fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6),
            "body":     sty("body",     fontSize=9,  textColor=SLATE, leading=14),
            "muted":    sty("muted",    fontSize=8,  textColor=MUTED, leading=12),
            "cite":     sty("cite",     fontSize=7.5, textColor=MUTED,
                            fontName="Helvetica-Oblique", leading=11),
            "dec":      sty("dec",      fontSize=15, textColor=dec_fg,
                            fontName="Helvetica-Bold", leading=18),
            "summary":  sty("summary",  fontSize=9,  textColor=colors.HexColor("#334155"),
                            leading=15, leftIndent=8),
            "footer":   sty("footer",   fontSize=7.5, textColor=MUTED, leading=11),
            "badge":    sty("badge",    fontSize=8,  textColor=colors.white,
                            fontName="Helvetica-Bold", leading=11),
        }

        # ── Document ────────────────────────────────────────────────────────────
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=20*mm, rightMargin=20*mm,
            topMargin=18*mm, bottomMargin=18*mm,
        )
        W = A4[0] - 40*mm   # usable width
        story = []

        def hr(thickness=1, color=BORDER):  # type: ignore[no-untyped-def]
            return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=6)

        # ── Header ──────────────────────────────────────────────────────────────
        header_data = [
            [Paragraph("<b>Agent</b><font color='#2563eb'>Ledger</font>", S["brand"]),
             Paragraph(
                 f"<b>Borrower ID:</b> {state.user_id}<br/>"
                 f"<b>Run ID:</b> {state.run_id}<br/>"
                 f"<b>Generated:</b> {generated_at}",
                 S["meta"],
             )],
        ]
        header_tbl = Table(header_data, colWidths=[W * 0.55, W * 0.45])
        header_tbl.setStyle(TableStyle([
            ("ALIGN",  (1, 0), (1, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("LINEBELOW", (0, 0), (-1, 0), 2, SLATE),
        ]))
        story.append(header_tbl)
        story.append(Spacer(1, 6))

        loan_line = f"<b>Loan Request:</b> ${state.loan_amount:,.0f}"
        if state.loan_purpose:
            loan_line += f" — {state.loan_purpose}"
        story.append(Paragraph(loan_line, S["muted"]))
        story.append(Spacer(1, 10))

        # ── Decision banner ─────────────────────────────────────────────────────
        banner_data = [[
            Paragraph(dec_label, S["dec"]),
            Paragraph(
                f"Risk Score: <b>{ra.risk_score} / 100</b><br/>"
                f"Confidence: <b>{ra.confidence:.0%}</b>",
                sty("dm", fontSize=9, textColor=MUTED, alignment=TA_RIGHT, leading=13),
            ),
        ]]
        banner = Table(banner_data, colWidths=[W * 0.65, W * 0.35])
        banner.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, -1), dec_bg),
            ("LEFTPADDING",  (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING",   (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
            ("LINEAFTER",    (0, 0), (0, -1),  5, dec_fg),
            ("ALIGN",        (1, 0), (1, 0),   "RIGHT"),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("ROUNDEDCORNERS", (0, 0), (-1, -1), 4),
        ]))
        story.append(banner)
        story.append(Spacer(1, 10))

        # ── Executive summary ───────────────────────────────────────────────────
        story.append(Paragraph("Executive Summary", S["h2"]))
        story.append(hr())
        sum_tbl = Table([[Paragraph(ra.reasoning_summary, S["summary"])]], colWidths=[W])
        sum_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, -1), BG),
            ("LEFTPADDING",  (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING",   (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
            ("LINEAFTER",    (0, 0), (0, -1),  4, BLUE),
        ]))
        story.append(sum_tbl)
        story.append(Spacer(1, 8))

        # ── Cash flow metrics ───────────────────────────────────────────────────
        story.append(Paragraph("Cash Flow Analysis", S["h2"]))
        story.append(hr())

        def _flag(val, ok_thr, warn_thr, ok="✓ Good", warn="⚠ Elevated", bad="✗ High", invert=False):  # type: ignore[no-untyped-def]
            if invert:
                color = _SEV_FG["low"] if val > ok_thr else (_SEV_FG["medium"] if val > warn_thr else _SEV_FG["high"])
                label = ok if val > ok_thr else (warn if val > warn_thr else bad)
            else:
                color = _SEV_FG["low"] if val < ok_thr else (_SEV_FG["medium"] if val < warn_thr else _SEV_FG["high"])
                label = ok if val < ok_thr else (warn if val < warn_thr else bad)
            return Paragraph(f"<font color='#{color.hexval()[2:]}'>{label}</font>",
                             sty("fl", fontSize=8.5, alignment=TA_RIGHT))

        metrics_data = [
            ["Metric", "Value", "Signal"],
            ["Avg Monthly Income",        f"${m.avg_monthly_income:,.0f}",           "—"],
            ["Avg Monthly Expenses",      f"${m.avg_monthly_expenses:,.0f}",          "—"],
            ["Debt-to-Income Ratio",      f"{m.dti_ratio:.1%}",
             _flag(m.dti_ratio, 0.36, 0.50, "✓ Good", "⚠ Elevated", "✗ High")],
            ["Income Stability (CV)",     f"{m.income_cv:.3f}",
             _flag(m.income_cv, 0.15, 0.30, "✓ Stable", "⚠ Variable", "✗ Volatile")],
            ["NSF / Overdraft Events",    str(m.total_nsf_events),
             _flag(m.total_nsf_events, 1, 3, "✓ None", "⚠ Present", "✗ Multiple")],
            ["Cash Buffer Days",          f"{m.cash_buffer_days:.0f} days",
             _flag(m.cash_buffer_days, 0, 15, "✗ Negative", "⚠ Thin", "✓ Healthy", invert=True)],
            ["Rent-to-Income Ratio",      f"{m.rent_to_income_ratio:.1%}",
             _flag(m.rent_to_income_ratio, 0.30, 0.40, "✓ Low", "⚠ Moderate", "✗ High")],
            ["Discretionary Spending",    f"{m.discretionary_spending_ratio:.1%}",   "—"],
        ]

        def _cell(v):  # type: ignore[no-untyped-def]
            return v if isinstance(v, Paragraph) else Paragraph(str(v), sty("mc", fontSize=9))

        metrics_rows = [[_cell(c) for c in row] for row in metrics_data]
        metrics_tbl = Table(metrics_rows, colWidths=[W * 0.50, W * 0.25, W * 0.25])
        metrics_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor("#f1f5f9")),
            ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0),  8.5),
            ("TEXTCOLOR",    (0, 0), (-1, 0),  MUTED),
            ("ALIGN",        (1, 0), (-1, -1), "RIGHT"),
            ("LINEBELOW",    (0, 0), (-1, -2), 0.5, BORDER),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(metrics_tbl)
        story.append(Spacer(1, 8))

        # ── Escalation notice ───────────────────────────────────────────────────
        if state.escalate_to_human and state.escalation_reasons:
            esc_text = "⚠  Escalated for Human Review: " + " • ".join(state.escalation_reasons)
            esc_tbl = Table([[Paragraph(esc_text, sty("es", fontSize=8.5,
                              textColor=colors.HexColor("#92400e")))]], colWidths=[W])
            esc_tbl.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#fef3c7")),
                ("LINEABOVE",    (0, 0), (-1, 0),  1, colors.HexColor("#fbbf24")),
                ("LINEBELOW",    (0, 0), (-1, -1), 1, colors.HexColor("#fbbf24")),
                ("LEFTPADDING",  (0, 0), (-1, -1), 10),
                ("TOPPADDING",   (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
            ]))
            story.append(esc_tbl)
            story.append(Spacer(1, 8))

        # ── Risk factors + Strengths ────────────────────────────────────────────
        # Each factor is a single flat Table row: [badge | description + citations]
        # Avoids nested flowables-in-cells which causes reportlab LayoutError.
        def _append_factors(factors, is_strength=False):  # type: ignore[no-untyped-def]
            for f in factors:
                fg = BLUE if is_strength else _SEV_FG.get(f.severity, MUTED)
                label = "STRENGTH" if is_strength else f.severity.upper()
                bg = colors.HexColor("#eff6ff") if is_strength else colors.HexColor("#fafafa")
                cites = ", ".join(f.citations) if f.citations else "—"
                card = Table(
                    [[
                        Paragraph(
                            label,
                            sty(f"bl_{label}", fontSize=7, textColor=colors.white,
                                fontName="Helvetica-Bold", alignment=TA_CENTER),
                        ),
                        Paragraph(
                            f'{f.description}<br/>'
                            f'<font color="#94a3b8" size="7"><i>{cites}</i></font>',
                            sty(f"fd_{label}", fontSize=9, leading=14),
                        ),
                    ]],
                    colWidths=[14 * mm, W - 14 * mm],
                )
                card.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (0, 0),   fg),
                    ("BACKGROUND",    (1, 0), (1, 0),   bg),
                    ("LINEBEFORE",    (1, 0), (1, 0),   4, fg),
                    ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                    ("ALIGN",         (0, 0), (0, 0),   "CENTER"),
                    ("LEFTPADDING",   (0, 0), (0, 0),   4),
                    ("RIGHTPADDING",  (0, 0), (0, 0),   4),
                    ("LEFTPADDING",   (1, 0), (1, 0),   10),
                    ("RIGHTPADDING",  (1, 0), (1, 0),   8),
                    ("TOPPADDING",    (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]))
                story.append(card)
                story.append(Spacer(1, 4))

        story.append(Paragraph("Risk Factors", S["h2"]))
        story.append(hr())
        if ra.risk_factors:
            _append_factors(ra.risk_factors, is_strength=False)
        else:
            story.append(Paragraph("No significant risk factors identified.", S["muted"]))

        story.append(Paragraph("Strengths", S["h2"]))
        story.append(hr())
        if ra.strengths:
            _append_factors(ra.strengths, is_strength=True)
        else:
            story.append(Paragraph("No notable strengths identified.", S["muted"]))

        story.append(Spacer(1, 8))

        # ── Methodology ─────────────────────────────────────────────────────────
        story.append(Paragraph("Methodology & Audit", S["h2"]))
        story.append(hr())
        meth_rows = [
            ["Metrics Engine",        "All 8 cash-flow metrics computed deterministically in Python + dbt SQL. LLM never performs arithmetic."],
            ["Transaction Categorizer","TF-IDF + RandomForest (ML). LLM fallback only when ML confidence < 70%."],
            ["Risk Assessment",       "GPT-OSS 120B via OpenRouter. Every claim cites source transaction_ids."],
            ["Citation Validator",    "All cited IDs cross-referenced against source data. Validity threshold: 85%."],
            ["Audit Trail",           f"logs/audit/run_{state.run_id}.jsonl"],
        ]
        meth_tbl = Table(
            [[Paragraph(r[0], sty("mk", fontSize=8.5, fontName="Helvetica-Bold", textColor=MUTED)),
              Paragraph(r[1], sty("mv", fontSize=8.5))] for r in meth_rows],
            colWidths=[W * 0.28, W * 0.72],
        )
        meth_tbl.setStyle(TableStyle([
            ("LINEBELOW",    (0, 0), (-1, -2), 0.5, BORDER),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ]))
        story.append(meth_tbl)
        story.append(Spacer(1, 12))

        # ── Footer ──────────────────────────────────────────────────────────────
        story.append(hr(color=BORDER))
        footer_data = [[
            Paragraph("AgentLedger — AI-Augmented Credit Analysis", S["footer"]),
            Paragraph(f"Run ID: {state.run_id}  |  {generated_at}",
                      sty("fr", fontSize=7.5, textColor=MUTED, alignment=TA_RIGHT)),
        ]]
        footer_tbl = Table(footer_data, colWidths=[W * 0.6, W * 0.4])
        footer_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(footer_tbl)

        doc.build(story)
        return pdf_path
