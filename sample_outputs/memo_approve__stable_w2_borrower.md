# Credit Analysis Memo
**Borrower ID:** eval_scn_001_stable_w2
**Run ID:** e9418fee-e866-4acf-9dcc-74c5daf2ed51
**Generated:** 2026-05-18 23:29 UTC
**Loan Request:** $25000 — Evaluation scenario

---

## Executive Summary
The borrower has a stable income and no history of NSF / Overdraft Events, but has a high Debt-to-Income Ratio and Rent-to-Income Ratio which may pose a risk.

**Decision:** APPROVE
**Risk Score:** 50 / 100
**Confidence:** 80%

---

## Cash Flow Analysis
| Metric | Value |
|--------|-------|
| Avg Monthly Income | $5500 |
| Avg Monthly Expenses | $4040 |
| Debt-to-Income Ratio | 28.0% |
| Income Stability (CV) | 0.000 |
| NSF Events | 0 |
| Cash Buffer Days | 11 |
| Rent-to-Income Ratio | 32.7% |
| Discretionary Ratio | 45.1% |

---

## Risk Factors

**[MEDIUM]** Debt-to-Income Ratio is high (28%) which may lead to difficulty in paying the loan
_Citations: tx:eval_eval_scn_001_stable_w2_0005, tx:eval_eval_scn_001_stable_w2_0012, tx:eval_eval_scn_001_stable_w2_0019_


**[MEDIUM]** Rent-to-Income Ratio is high (32.7%) which may leave limited room for other expenses
_Citations: tx:eval_eval_scn_001_stable_w2_0002, tx:eval_eval_scn_001_stable_w2_0009, tx:eval_eval_scn_001_stable_w2_0016_



## Strengths

**Income Stability (CV) is excellent (0.000) which indicates stable income**
_Citations: tx:eval_eval_scn_001_stable_w2_0001, tx:eval_eval_scn_001_stable_w2_0008, tx:eval_eval_scn_001_stable_w2_0015_


**No NSF / Overdraft Events which indicates responsible financial management**
_Citations: _



---

## Recommendation
**APPROVE**


⚠️ **Escalated for Human Review:** Ambiguous risk score: 50


---

## Methodology
All financial metrics computed deterministically in Python + dbt SQL.
LLM used only for risk interpretation — not arithmetic.
Every claim validated against source transaction data.

## Audit
Full audit trail: `logs/audit/run_e9418fee-e866-4acf-9dcc-74c5daf2ed51.jsonl`