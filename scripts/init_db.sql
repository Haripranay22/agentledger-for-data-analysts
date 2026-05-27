-- AgentLedger database schema
-- Run: psql -U agentledger -d agentledger -f scripts/init_db.sql

CREATE TABLE IF NOT EXISTS runs (
    run_id          UUID PRIMARY KEY,
    user_id         TEXT NOT NULL,
    loan_amount     NUMERIC(12, 2) NOT NULL,
    loan_purpose    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Cash flow metrics (computed deterministically)
    avg_monthly_income          NUMERIC(12, 2),
    avg_monthly_expenses        NUMERIC(12, 2),
    income_cv                   NUMERIC(6, 4),
    dti_ratio                   NUMERIC(6, 4),
    total_nsf_events            INTEGER,
    discretionary_spending_ratio NUMERIC(6, 4),
    rent_to_income_ratio        NUMERIC(6, 4),
    cash_buffer_days            NUMERIC(8, 2),
    months_analyzed             INTEGER,

    -- LLM risk assessment
    risk_score      INTEGER CHECK (risk_score BETWEEN 0 AND 100),
    recommendation  TEXT CHECK (recommendation IN ('approve','approve_with_conditions','decline','manual_review')),
    confidence      NUMERIC(4, 3),
    reasoning_summary TEXT,
    model_used      TEXT,

    -- Validation
    citation_validity   NUMERIC(4, 3),
    validation_passed   BOOLEAN,

    -- HITL
    escalated_to_human  BOOLEAN DEFAULT FALSE,
    escalation_reasons  TEXT[],

    -- Output
    report_path     TEXT,
    report_pdf_path TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    transaction_id      TEXT NOT NULL,
    account_id          TEXT NOT NULL,
    user_id             TEXT NOT NULL,
    transaction_date    DATE NOT NULL,
    amount              NUMERIC(12, 2) NOT NULL,
    merchant_name       TEXT,
    description         TEXT,
    our_category        TEXT,
    confidence_score    NUMERIC(4, 3),
    is_income           BOOLEAN,
    is_recurring        BOOLEAN,
    is_essential        BOOLEAN,
    categorization_source TEXT
);

CREATE TABLE IF NOT EXISTS risk_factors (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    factor_type TEXT NOT NULL CHECK (factor_type IN ('risk', 'strength')),
    severity    TEXT CHECK (severity IN ('low', 'medium', 'high')),
    description TEXT NOT NULL,
    citations   TEXT[]
);

CREATE TABLE IF NOT EXISTS citation_checks (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    transaction_id  TEXT NOT NULL,
    found           BOOLEAN NOT NULL,
    claim_supported BOOLEAN NOT NULL,
    reason          TEXT
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_runs_user_id    ON runs(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_recommendation ON runs(recommendation);
CREATE INDEX IF NOT EXISTS idx_transactions_run_id ON transactions(run_id);
CREATE INDEX IF NOT EXISTS idx_risk_factors_run_id ON risk_factors(run_id);
