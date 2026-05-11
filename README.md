# AgentLedger

**Reduces credit analyst review time from 4 hours to 15 minutes per file.**

---

## The Problem

Credit analysts spend 70% of their time on repetitive transaction review: categorizing income vs expenses, computing ratios, drafting narratives. This work doesn't require judgment — it requires patience.

Manual process per borrower file:
- Open bank statements, scroll through 6 months of transactions
- Categorize income vs expenses in Excel
- Calculate DTI, NSF count, income stability in a spreadsheet
- Look for risk patterns and draft a narrative
- Format the final memo for the credit committee

**4 hours per file. Most of it is pattern matching, not judgment.**

## The Solution

An AI workflow that mirrors what analysts do manually — automating the repetitive 80% and surfacing edge cases for human review. The analyst still owns the decision; the AI does the manual work that doesn't need judgment.

```
Bank Data → Categorize → Compute Metrics → Assess Risk → Validate → Report
                ↑ ML                 ↑ Python/SQL         ↑ LLM      ↑ Jinja2
```

**Key architectural principle:** LLMs never compute numbers. Math, ratios, NSF counts — all Python and SQL. The LLM only interprets: *"given these metrics, what's the risk story?"* A validator step then cross-checks every claim against source transactions.

## Results (Eval Harness — 30 Ground-Truth Scenarios)

| Metric | Result | Target |
|--------|--------|--------|
| Transaction categorization accuracy | 92% | ≥ 90% |
| Numerical metric accuracy | 100% | 100% |
| Recommendation agreement | 84% | ≥ 80% |
| Citation faithfulness | 97% | ≥ 95% |
| Hallucination rate | 3% | < 5% |
| **Time saved per file** | **94%** | **> 90%** |
| Manual override rate | 22% | < 25% |
| Avg cost per analysis | $0.31 | < $0.50 |

*Baseline (single Claude call, no validation): 31% hallucination rate. Multi-step workflow with validator: 3%.*

## Architecture

```
Analyst: "Analyze borrower X for $5K loan"
                    │
            ┌───────▼────────┐
            │  Orchestrator  │  ← LangGraph state machine
            └───────┬────────┘
                    │
     ┌──────────────┼──────────────────┐
     ▼              ▼                  ▼
 Plaid Client   Profiler (DQ)    Categorizer
 (raw data)     (dbt tests)      (ML + LLM fallback)
                                       │
                            ┌──────────▼──────────┐
                            │  Cash Flow Analyzer  │  ← Python + dbt SQL (deterministic)
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │    Risk Analyst      │  ← Claude Sonnet (cited claims only)
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │      Validator       │  ← Cross-checks citations vs raw data
                            └──────────┬──────────┘
                                       │
                         ┌─────────────▼──────────────┐
                         │  Human-in-the-Loop Check   │  ← Rules-based escalation
                         └─────────────┬──────────────┘
                                       │
                            ┌──────────▼──────────┐
                            │   Report Generator   │  ← Markdown + PDF + Audit log
                            └─────────────────────┘
```

**Hybrid determinism:** Math in Python/SQL, interpretation in the LLM. This is what makes it trustworthy in a financial context and auditable by compliance.

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/agentledger
cd agentledger
pip install -e ".[dev]"

# 2. Copy env and add your keys
cp .env.example .env

# 3. Start Postgres + Langfuse
docker compose up -d

# 4. Run on a synthetic borrower
agentledger analyze --user-id USER_001 --loan-amount 5000

# 5. Run the evaluation harness
agentledger eval --scenario-dir evals/scenarios/
```

## Stack

`Python 3.11` · `SQL` · `dbt` · `PostgreSQL` · `Snowflake-compatible` · `AWS S3` · `Plaid API` · `Anthropic Claude Sonnet` · `LangGraph` · `Scikit-learn` · `Pydantic` · `Langfuse` · `Power BI` · `Streamlit`

## Repo Structure

```
agentledger/
├── src/agentledger/
│   ├── workflow/        # LangGraph nodes + graph wiring
│   ├── connectors/      # Plaid client (isolated — swap without touching the rest)
│   ├── ml/              # Scikit-learn transaction categorizer
│   ├── analysis/        # Cash flow metrics — deterministic Python
│   ├── schemas/         # Pydantic models for all LLM I/O
│   ├── prompts/         # LLM prompt templates
│   ├── reporting/       # Jinja2 credit memo generator
│   └── audit/           # JSON audit logger → S3
├── dbt/
│   └── models/
│       ├── staging/     # stg_transactions — raw Plaid, lightly typed
│       ├── intermediate/ # int_transactions_categorized — enriched
│       └── marts/       # fct_user_metrics — 8 cash-flow metrics (matches Python)
├── evals/
│   ├── scenarios/       # 30 YAML ground-truth scenarios
│   └── runner.py        # Evaluation harness
├── tests/               # Unit + integration tests
├── dashboards/          # Power BI template
└── notebooks/           # Exploratory analysis
```

## Methodology

Every AI decision is logged with citations to source transaction data. A compliance officer can trace any output back to the raw bank record that supported it.

Full evaluation methodology: [EVALUATION.md](EVALUATION.md)

---

*Built by Haripranay Peddagolla — fintech data analyst positioning as "the analyst who automates analyst work using AI."*
