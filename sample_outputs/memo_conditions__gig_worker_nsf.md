# Credit Analysis Memo
**Borrower ID:** eval_scn_006_gig_with_nsf
**Run ID:** 03b5d01e-ebf2-4f98-b424-bd0d45e8da56
**Generated:** 2026-05-18 23:30 UTC
**Loan Request:** $25000 — Evaluation scenario

---

## Executive Summary
The borrower's financial situation is generally stable but exhibits some risk factors such as a high debt-to-income ratio and a recent NSF event. The borrower's income stability and the fact that their average monthly income exceeds expenses are strengths.

**Decision:** APPROVE WITH CONDITIONS
**Risk Score:** 70 / 100
**Confidence:** 80%

---

## Cash Flow Analysis
| Metric | Value |
|--------|-------|
| Avg Monthly Income | $4500 |
| Avg Monthly Expenses | $3601 |
| Debt-to-Income Ratio | 31.0% |
| Income Stability (CV) | 0.269 |
| NSF Events | 1 |
| Cash Buffer Days | 8 |
| Rent-to-Income Ratio | 33.3% |
| Discretionary Ratio | 46.7% |

---

## Risk Factors

**[MEDIUM]** High debt-to-income ratio indicates potential difficulties in servicing the loan.
_Citations: tx:eval_eval_scn_006_gig_with_nsf_0005, tx:eval_eval_scn_006_gig_with_nsf_0012, tx:eval_eval_scn_006_gig_with_nsf_0019_


**[LOW]** NSF/Overdraft events may suggest cash flow management issues.
_Citations: tx:eval_eval_scn_006_gig_with_nsf_0029_



## Strengths

**The borrower has a stable income stream with low income stability coefficient (CV = 0.269).**
_Citations: tx:eval_eval_scn_006_gig_with_nsf_0001, tx:eval_eval_scn_006_gig_with_nsf_0008, tx:eval_eval_scn_006_gig_with_nsf_0015_


**The borrower's average monthly income exceeds their average monthly expenses.**
_Citations: tx:eval_eval_scn_006_gig_with_nsf_0001, tx:eval_eval_scn_006_gig_with_nsf_0002, tx:eval_eval_scn_006_gig_with_nsf_0003_



---

## Recommendation
**APPROVE WITH CONDITIONS**


⚠️ **Escalated for Human Review:** Insufficient data: long-term credit history


---

## Methodology
All financial metrics computed deterministically in Python + dbt SQL.
LLM used only for risk interpretation — not arithmetic.
Every claim validated against source transaction data.

## Audit
Full audit trail: `logs/audit/run_03b5d01e-ebf2-4f98-b424-bd0d45e8da56.jsonl`