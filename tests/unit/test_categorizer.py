"""Unit tests for the TransactionCategorizer."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from agentledger.ml.categorizer import (
    CATEGORIES,
    CONFIDENCE_THRESHOLD,
    TransactionCategorizer,
)
from agentledger.schemas.models import Transaction


def make_txn(txn_id: str, merchant: str, description: str) -> Transaction:
    return Transaction(
        transaction_id=txn_id,
        account_id="acc_test",
        user_id="user_test",
        transaction_date=date(2024, 6, 15),
        amount=-50.0,
        merchant_name=merchant,
        description=description,
    )


# ── Category definitions ───────────────────────────────────────────────────────

def test_categories_count():
    assert len(CATEGORIES) == 18


def test_categories_are_strings():
    assert all(isinstance(c, str) for c in CATEGORIES)


def test_categories_include_income_and_nsf():
    assert "income_salary" in CATEGORIES
    assert "nsf_fee" in CATEGORIES
    assert "rent_mortgage" in CATEGORIES
    assert "gambling" in CATEGORIES


def test_confidence_threshold_value():
    assert CONFIDENCE_THRESHOLD == 0.70


# ── Feature engineering ────────────────────────────────────────────────────────

def test_make_feature_combines_merchant_and_description():
    cat = TransactionCategorizer()
    txns = [make_txn("t1", "Whole Foods", "grocery purchase")]
    features = cat._make_feature(txns)
    assert features == ["Whole Foods grocery purchase"]


def test_make_feature_handles_none_merchant():
    cat = TransactionCategorizer()
    txns = [make_txn("t1", None, "payroll deposit")]  # type: ignore[arg-type]
    features = cat._make_feature(txns)
    assert features == ["payroll deposit"]


def test_make_feature_strips_whitespace():
    cat = TransactionCategorizer()
    txns = [make_txn("t1", "", "payroll")]
    features = cat._make_feature(txns)
    assert features[0] == "payroll"


# ── Untrained model ────────────────────────────────────────────────────────────

def test_predict_raises_without_training():
    cat = TransactionCategorizer()
    with pytest.raises(RuntimeError, match="not trained"):
        cat.predict([make_txn("t1", "Walmart", "grocery")])


def test_categorize_raises_without_training():
    cat = TransactionCategorizer()
    with pytest.raises(RuntimeError, match="not trained"):
        cat.categorize([make_txn("t1", "Walmart", "grocery")])


# ── Train → predict ────────────────────────────────────────────────────────────

def _build_training_data() -> tuple[list[Transaction], list[str]]:
    """Labeled dataset — at least 2 samples per class for stratified split."""
    samples = [
        ("EMPLOYER PAYROLL",  "direct deposit salary",        "income_salary"),
        ("ACME CORP PAYROLL", "bi-weekly paycheck",           "income_salary"),
        ("STRIPE PAYOUT",     "freelance payment",            "income_freelance"),
        ("VENMO PAYOUT",      "contractor payment",           "income_freelance"),
        ("GREENWAY APTS",     "rent payment monthly",         "rent_mortgage"),
        ("PROPERTY MGMT",     "monthly rent",                 "rent_mortgage"),
        ("WHOLE FOODS",       "grocery shopping",             "groceries"),
        ("TRADER JOES",       "supermarket purchase",         "groceries"),
        ("CITY ELECTRIC",     "electric bill payment",        "utilities"),
        ("WATER DEPT",        "water utility bill",           "utilities"),
        ("CHIPOTLE",          "restaurant dining",            "dining_entertainment"),
        ("MCDONALDS",         "fast food purchase",           "dining_entertainment"),
        ("NETFLIX",           "streaming subscription",       "subscription"),
        ("SPOTIFY",           "music subscription monthly",   "subscription"),
        ("NAVIENT",           "student loan payment",         "debt_payment"),
        ("VISA CREDIT",       "credit card payment",          "debt_payment"),
        ("NSF FEE",           "insufficient funds fee",       "nsf_fee"),
        ("OVERDRAFT FEE",     "overdraft charge",             "nsf_fee"),
        ("SHELL GAS",         "gas station fuel",             "transportation"),
        ("UBER",              "rideshare trip",               "transportation"),
        ("CVS PHARMACY",      "pharmacy prescription",        "healthcare"),
        ("URGENT CARE",       "medical clinic visit",         "healthcare"),
        ("AMAZON",            "online purchase general",      "other"),
        ("EBAY",              "marketplace purchase",         "other"),
    ]
    txns = [
        make_txn(f"t{i}", merchant, desc)
        for i, (merchant, desc, _) in enumerate(samples)
    ]
    labels = [label for _, _, label in samples]
    return txns, labels


def test_train_returns_accuracy_metrics():
    cat = TransactionCategorizer()
    txns, labels = _build_training_data()
    result = cat.train(txns, labels, test_size=0.5)
    assert "accuracy" in result
    assert "n_train" in result
    assert "n_test" in result
    assert 0 <= result["accuracy"] <= 1


def test_predict_returns_correct_shape():
    cat = TransactionCategorizer()
    txns, labels = _build_training_data()
    cat.train(txns, labels, test_size=0.5)
    preds = cat.predict(txns[:5])
    assert len(preds) == 5
    assert all(isinstance(category, str) and 0.0 <= conf <= 1.0 for category, conf in preds)


def test_predict_categories_in_known_set():
    cat = TransactionCategorizer()
    txns, labels = _build_training_data()
    cat.train(txns, labels, test_size=0.5)
    preds = cat.predict(txns)
    for category, _ in preds:
        assert category in CATEGORIES


def test_categorize_sets_is_income_correctly():
    cat = TransactionCategorizer()
    txns, labels = _build_training_data()
    cat.train(txns, labels, test_size=0.5)
    # Force a high-confidence income prediction by training on a clear signal
    salary_txn = [make_txn("salary_check", "EMPLOYER PAYROLL", "direct deposit salary")]
    salary_preds = cat.predict(salary_txn)
    category, confidence = salary_preds[0]
    # Even if confidence is low, categorize should set is_income based on category
    categorized = cat.categorize(salary_txn)
    assert categorized[0].is_income == category.startswith("income_")


def test_categorize_sets_recurring_flag():
    cat = TransactionCategorizer()
    txns, labels = _build_training_data()
    cat.train(txns, labels, test_size=0.5)
    # Train with enough data to recognize rent
    rent_txn = [make_txn("rent_1", "GREENWAY APTS", "monthly rent")]
    categorized = cat.categorize(rent_txn)
    # Category should be rent_mortgage; if so is_recurring must be True
    if categorized[0].our_category == "rent_mortgage":
        assert categorized[0].is_recurring is True


def test_categorize_calls_llm_fallback_on_low_confidence():
    cat = TransactionCategorizer()
    txns, labels = _build_training_data()
    cat.train(txns, labels, test_size=0.5)

    fallback_called = []

    def mock_fallback(txn: Transaction) -> str:
        fallback_called.append(txn.transaction_id)
        return "other"

    # Patch the pipeline to always return low confidence
    original_predict = cat.predict

    def low_confidence_predict(transactions):
        return [("other", 0.30) for _ in transactions]

    cat.predict = low_confidence_predict  # type: ignore[method-assign]
    result = cat.categorize([make_txn("t_ambiguous", "MYSTERY CORP", "unknown")], mock_fallback)
    assert len(fallback_called) == 1
    assert result[0].categorization_source == "llm_fallback"
    cat.predict = original_predict  # type: ignore[method-assign]


# ── Save / load ────────────────────────────────────────────────────────────────

def test_save_and_load_round_trip():
    cat = TransactionCategorizer()
    txns, labels = _build_training_data()
    cat.train(txns, labels, test_size=0.5)
    original_preds = cat.predict(txns[:3])

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        path = Path(f.name)

    try:
        cat.save(path)
        loaded = TransactionCategorizer(model_path=path)
        loaded_preds = loaded.predict(txns[:3])
        assert [c for c, _ in original_preds] == [c for c, _ in loaded_preds]
    finally:
        path.unlink(missing_ok=True)


def test_load_nonexistent_path_does_not_raise():
    # TransactionCategorizer silently skips loading if path doesn't exist
    cat = TransactionCategorizer(model_path=Path("/nonexistent/model.pkl"))
    assert cat._pipeline is None
