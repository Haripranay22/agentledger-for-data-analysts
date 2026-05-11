#!/bin/bash
# ─────────────────────────────────────────────────────────────
# AgentLedger — one-command GitHub setup
# Usage: bash setup_git.sh <your-github-username>
# ─────────────────────────────────────────────────────────────

set -e

GITHUB_USER=${1:-"YOUR_GITHUB_USERNAME"}
REPO_NAME="agentledger"

echo "Setting up git for ${GITHUB_USER}/${REPO_NAME}..."

git init
git add .
git commit -m "feat: initial scaffold — Week 1 Day 1

- Full repo structure (src layout, dbt, evals, tests)
- Pydantic schemas for all LLM I/O (WorkflowState, RiskAssessment, etc.)
- LangGraph graph wiring with validator retry loop
- Deterministic cash flow analyzer (Python) — mirrors fct_user_metrics.sql
- Scikit-learn transaction categorizer stub (TF-IDF + RandomForest)
- Plaid client wrapper
- dbt project: staging → intermediate → marts layers with dbt tests
- 2 eval scenarios (YAML ground-truth)
- Unit tests for cash flow metrics
- GitHub Actions CI
- Analyst-flavored README leading with business value

TODO: wire up Plaid credentials, train categorizer, complete Week 1"

git branch -M main

echo ""
echo "Next steps:"
echo "  1. Go to github.com/new and create a repo named '${REPO_NAME}'"
echo "  2. Run: git remote add origin https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
echo "  3. Run: git push -u origin main"
echo ""
echo "Done! Your first commit is ready to push."
