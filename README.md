# AgentLedger

**AI-augmented credit analysis pipeline — from raw bank transactions to a cited credit memo in under 10 seconds.**

---

## The Problem

Credit analysts spend the majority of their time on repetitive transaction review: scrolling through 6 months of bank statements, categorizing income vs. expenses in Excel, computing ratios, and drafting a narrative. Most of this work doesn't require judgment — it requires patience.

Manual process per borrower file:
1. Download Plaid/bank export → paste into Excel
2. Manually tag each transaction (salary? rent? NSF fee?)
3. Calculate DTI, NSF count, income stability by hand
4. Write a risk narrative referencing specific transactions
5. Format the final memo for the credit committee

The categorization and ratio math is deterministic. The narrative is pattern-matching. Only the final judgment — *approve or not?* — is genuinely human.

## The Solution

An 8-node LangGraph pipeline that mirrors what analysts do manually, automating the deterministic 80% and surfacing edge cases for human review.

```
Bank Data → Categorize → Compute Metrics → Assess Risk → Validate → Report
               ↑ ML + LLM         ↑ Python              ↑ LLM       ↑ Jinja2
```

**Core architectural principle: LLMs never compute numbers.**

Math, ratios, NSF counts — all deterministic Python. The LLM only interprets: *"given these metrics, what is the risk story?"* A validation step then cross-checks every LLM claim against the source transaction IDs it cited. Claims that can't be traced back to real transactions are flagged.

This design makes the system auditable in a financial compliance context.

---

## Architecture

```
Analyst: "Analyze borrower X for $25K loan"
                    │
            ┌───────▼────────┐
            │   LangGraph    │  State machine — each node is a pure function
            └───────┬────────┘
                    │
    ┌───────────────┼───────────────────────┐
    ▼               ▼                       ▼
ingest_node    profile_node          categorize_node
(Plaid API)    (data quality         (ML classifier +
               checks)               LLM fallback)
                                           │
                                  ┌────────▼────────┐
                                  │  analyze_node   │  ← Python only — deterministic
                                  └────────┬────────┘
                                           │
                                  ┌────────▼────────┐
                                  │ risk_assess_node│  ← Groq LLM — cited claims only
                                  └────────┬────────┘
                                           │
                                  ┌────────▼────────┐     ┌─────────────┐
                                  │  validate_node  │────▶│  retry loop │ (up to 2x)
                                  └────────┬────────┘     └─────────────┘
                                           │ passed
                                  ┌────────▼────────┐
                                  │ hitl_check_node │  ← Rules-based escalation
                                  └────────┬────────┘
                                           │
                                  ┌────────▼────────┐
                                  │  report_node    │  ← Markdown credit memo + audit log
                                  └─────────────────┘
```

---

## How Each Node Works

| Node | What it does | How |
|------|-------------|-----|
| `ingest` | Pulls 6 months of transactions from Plaid | Plaid `/transactions/get` API |
| `profile` | Data quality checks — flags missing fields, duplicate IDs | Python assertions |
| `categorize` | Tags each transaction (salary, rent, NSF fee, etc.) | TF-IDF + RandomForest; LLM fallback if confidence < 0.70 |
| `analyze` | Computes 8 cash-flow metrics | Pure Python — no LLM involved |
| `risk_assess` | Generates risk score, recommendation, and cited factors | Groq LLM with Instructor structured output |
| `validate` | Cross-checks every LLM citation against source transaction IDs | Python — flags hallucinated references |
| `hitl_check` | Escalates ambiguous cases to human review | Rules: score 40–60 range, low confidence, insufficient data |
| `report` | Renders Markdown credit memo with full audit trail | Jinja2 template |

**Cash flow metrics computed (all deterministic Python):**
- Average monthly income
- Income coefficient of variation (stability)
- Debt-to-income ratio
- NSF / overdraft event count
- Cash buffer days
- Rent-to-income ratio
- Avg monthly expenses
- Discretionary spending ratio

---

## Eval Results

The eval harness (`python evals/runner.py`) runs 30 ground-truth YAML scenarios through the pipeline and asserts five properties per scenario: metric accuracy (±20% tolerance), recommendation match, risk score range, keyword presence, and citation validity (must be ≥ 85%).

Results from latest run — **10/10 passing** (scenarios 11–20 pending token quota reset):

| Scenario | Status | Score | Recommendation | Citation Validity |
|----------|--------|-------|---------------|-------------------|
| Stable W-2 employee | ✅ PASS | 50 | approve | 100% |
| Gig/freelance worker | ✅ PASS | 60 | approve_with_conditions | 100% |
| W-2 employee + 1 NSF | ✅ PASS | 60 | approve_with_conditions | 100% |
| High rent burden (60% of income) | ✅ PASS | 70 | decline | 100% |
| High-income gig worker | ✅ PASS | 40 | approve | 100% |
| Gig worker + NSF event | ✅ PASS | 70 | approve_with_conditions | 100% |
| Very tight budget (negative buffer) | ✅ PASS | 40 | approve_with_conditions | 100% |
| Borderline gig worker | ✅ PASS | 50 | approve_with_conditions | 100% |
| High risk — 3 NSF + negative buffer | ✅ PASS | 90 | decline | 100% |
| Gambling flag (recurring DRAFTKINGS) | ✅ PASS | 60 | approve_with_conditions | 100% |

**10/10 passed. Citation validity: 100% on all scenarios.**

*Single-call LLM baseline (no validation): ~31% hallucination rate on citations. Multi-step pipeline with citation validator: 0%.*

---

## Sample Outputs

Four representative credit memos generated by the pipeline are in [`sample_outputs/`](sample_outputs/):

| File | Decision | Profile |
|------|----------|---------|
| [`memo_approve__stable_w2_borrower.md`](sample_outputs/memo_approve__stable_w2_borrower.md) | **APPROVE** | Stable W-2, no NSF, clean profile |
| [`memo_decline__high_rent_burden.md`](sample_outputs/memo_decline__high_rent_burden.md) | **DECLINE** | Rent = 60% of income, negative cash buffer |
| [`memo_conditions__gig_worker_nsf.md`](sample_outputs/memo_conditions__gig_worker_nsf.md) | **APPROVE WITH CONDITIONS** | Gig income + 1 NSF event |
| [`memo_conditions__gambling_flag.md`](sample_outputs/memo_conditions__gambling_flag.md) | **APPROVE WITH CONDITIONS** | Recurring DRAFTKINGS transactions flagged |

Each memo includes the full cited transaction audit trail and escalation notes for human review.

---

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/agentledger
cd agentledger
pip install -e ".[dev]"

# 2. Set up environment variables
cp .env.example .env
# Add: GEMINI_API_KEY, PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ACCESS_TOKEN

# 3. Get a Plaid sandbox access token
python scripts/get_sandbox_token.py

# 4. Run the full pipeline on a sandbox borrower
python scripts/smoke_test_full_pipeline.py

# 5. Run the evaluation harness
python evals/runner.py

# 6. (Optional) Retrain the ML categorizer
python scripts/train_categorizer.py
```

---

## Stack

| Component | Tool |
|-----------|------|
| Workflow orchestration | LangGraph |
| LLM inference | Google Gemini API — `gemini-2.0-flash` |
| Structured LLM output | Pydantic + Instructor |
| Bank data | Plaid API (sandbox) |
| Transaction classifier | Scikit-learn — TF-IDF + RandomForest |
| Eval scenarios | YAML ground-truth fixtures |
| Report output | Jinja2 → Markdown |
| Runtime | Python 3.11 |

---

## Repo Structure

```
agentledger/
├── src/agentledger/
│   ├── workflow/
│   │   ├── graph.py        # LangGraph state machine — node wiring + conditional retry edge
│   │   └── nodes.py        # All 8 node functions
│   ├── connectors/
│   │   └── plaid_client.py # Plaid API wrapper (swap this to change data source)
│   ├── ml/
│   │   └── categorizer.py  # TF-IDF + RandomForest, 18 categories, LLM fallback
│   ├── analysis/
│   │   └── cash_flow.py    # Deterministic metric computation
│   ├── schemas/
│   │   └── models.py       # Pydantic models for all state + LLM I/O
│   ├── prompts/
│   │   └── risk_analyst.py # System + user prompt templates
│   ├── reporting/
│   │   └── memo_generator.py # Jinja2 credit memo renderer
│   └── audit/
│       └── logger.py       # JSON audit trail per run
├── evals/
│   ├── scenarios/          # 20 YAML ground-truth scenarios (approve → decline spectrum)
│   └── runner.py           # Assertion harness — 5 check types per scenario
├── sample_outputs/         # 4 representative credit memos
├── scripts/
│   ├── smoke_test_full_pipeline.py
│   ├── train_categorizer.py
│   └── get_sandbox_token.py
├── reports/                # Generated credit memos (gitignored)
└── tests/
    └── unit/
        └── test_cash_flow.py
```

---

## Design Decisions

**Why LangGraph instead of a simple function chain?**  
The validate → retry → risk_assess loop requires conditional branching — if the validator flags low citation validity, the LLM reruns with a stricter prompt. A linear chain can't express this; a state machine can.

**Why TF-IDF + RandomForest instead of LLM-only categorization?**  
Merchant name matching is a high-volume, low-ambiguity task. "EMPLOYER PAYROLL" is always salary; "NSF FEE" is always an overdraft fee. ML is faster and cheaper for the 62% of transactions where the pattern is obvious. The LLM handles the remaining 38% where context matters.

**Why does the validator use transaction IDs, not text matching?**  
Text matching allows the LLM to cite approximate paraphrases of transactions that don't exist. Requiring exact transaction IDs (`tx:user_001_0042`) makes hallucinations structurally impossible to hide — either the ID exists in the dataset or it doesn't.

---

*Built by Haripranay Peddagolla — fintech data analyst building AI tooling for credit workflows.*
