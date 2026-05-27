# Credit Analysis Memo
**Borrower ID:** eval_scn_004_high_rent_burden
**Run ID:** b030e87e-5a0f-4992-b566-320a09c5bdcf
**Generated:** 2026-05-18 23:30 UTC
**Loan Request:** $25000 — Evaluation scenario

---

## Executive Summary
The borrower's high rent-to-income ratio and negative cash buffer are significant concerns, but their stable income and lack of NSF or overdraft events are positive factors. However, the overall risk profile suggests a decline recommendation.

**Decision:** DECLINE
**Risk Score:** 70 / 100
**Confidence:** 80%

---

## Cash Flow Analysis
| Metric | Value |
|--------|-------|
| Avg Monthly Income | $4500 |
| Avg Monthly Expenses | $4660 |
| Debt-to-Income Ratio | 28.0% |
| Income Stability (CV) | 0.000 |
| NSF Events | 0 |
| Cash Buffer Days | -1 |
| Rent-to-Income Ratio | 60.0% |
| Discretionary Ratio | 33.1% |

---

## Risk Factors

**[HIGH]** High rent-to-income ratio, indicating potential difficulty in meeting loan payments
_Citations: tx:eval_eval_scn_004_high_rent_burden_0002, tx:eval_eval_scn_004_high_rent_burden_0016, tx:eval_eval_scn_004_high_rent_burden_0030_


**[HIGH]** Negative cash buffer, suggesting the borrower may already be experiencing financial strain
_Citations: tx:eval_eval_scn_004_high_rent_burden_0001, tx:eval_eval_scn_004_high_rent_burden_0002, tx:eval_eval_scn_004_high_rent_burden_0008_



## Strengths

**Stable income with low income variability**
_Citations: tx:eval_eval_scn_004_high_rent_burden_0001, tx:eval_eval_scn_004_high_rent_burden_0008, tx:eval_eval_scn_004_high_rent_burden_0015_


**No NSF or overdraft events, indicating responsible financial management**
_Citations: tx:eval_eval_scn_004_high_rent_burden_0001, tx:eval_eval_scn_004_high_rent_burden_0008, tx:eval_eval_scn_004_high_rent_burden_0015_



---

## Recommendation
**DECLINE**


⚠️ **Escalated for Human Review:** Insufficient data: Credit history


---

## Methodology
All financial metrics computed deterministically in Python + dbt SQL.
LLM used only for risk interpretation — not arithmetic.
Every claim validated against source transaction data.

## Audit
Full audit trail: `logs/audit/run_b030e87e-5a0f-4992-b566-320a09c5bdcf.jsonl`