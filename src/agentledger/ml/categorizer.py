"""
Transaction Categorizer — Hybrid ML + LLM approach.

Architecture:
  1. TF-IDF on merchant description → RandomForest classifier
  2. If confidence < 0.7 → LLM fallback via Google AI API
  3. Results stored with confidence score + source flag

Target: 90%+ accuracy on holdout set.
Interview talking point: "ML for high-volume, LLM for edge cases."
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from agentledger.schemas.models import CategorizedTransaction, Transaction

logger = logging.getLogger(__name__)

# 18 categories matching fintech credit analysis needs
CATEGORIES = [
    "income_salary",
    "income_freelance",
    "income_government",
    "income_other",
    "rent_mortgage",
    "utilities",
    "groceries",
    "dining_entertainment",
    "transportation",
    "healthcare",
    "debt_payment",
    "subscription",
    "gambling",
    "atm_cash",
    "transfer",
    "nsf_fee",
    "savings_investment",
    "other",
]

CONFIDENCE_THRESHOLD = 0.70


class TransactionCategorizer:
    """
    Scikit-learn pipeline for transaction categorization.

    Pipeline: TF-IDF(merchant_name + description) → RandomForest
    Falls back to LLM when confidence < CONFIDENCE_THRESHOLD.
    """

    def __init__(self, model_path: Path | None = None) -> None:
        self._pipeline: Pipeline | None = None
        if model_path and model_path.exists():
            self.load(model_path)
            logger.info("Loaded model from %s", model_path)

    def build_pipeline(self, use_gradient_boosting: bool = False) -> Pipeline:
        """Build the sklearn pipeline. RandomForest baseline, GBM for final."""
        classifier = (
            GradientBoostingClassifier(n_estimators=200, max_depth=5, random_state=42)
            if use_gradient_boosting
            else RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
        )
        return Pipeline([
            ("tfidf", TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=10_000,
                strip_accents="unicode",
                lowercase=True,
            )),
            ("clf", classifier),
        ])

    def _make_feature(self, transactions: list[Transaction]) -> list[str]:
        """Combine merchant name + description into single text feature."""
        return [
            f"{t.merchant_name or ''} {t.description}".strip()
            for t in transactions
        ]

    def train(
        self,
        transactions: list[Transaction],
        labels: list[str],
        test_size: float = 0.2,
    ) -> dict[str, float]:
        """
        Train on labeled data. Returns accuracy metrics.
        Target: 85%+ on holdout (RF baseline), then 90%+ with GBM.
        """
        X = self._make_feature(transactions)
        X_train, X_test, y_train, y_test = train_test_split(
            X, labels, test_size=test_size, random_state=42, stratify=labels
        )

        self._pipeline = self.build_pipeline()
        self._pipeline.fit(X_train, y_train)

        y_pred = self._pipeline.predict(X_test)
        report = classification_report(y_test, y_pred, output_dict=True)
        accuracy = report["accuracy"]  # type: ignore[index]

        logger.info("Training accuracy: %.3f on %d samples", accuracy, len(X_train))
        logger.info("Holdout accuracy:  %.3f on %d samples", accuracy, len(X_test))
        return {"accuracy": accuracy, "n_train": len(X_train), "n_test": len(X_test)}

    def predict(self, transactions: list[Transaction]) -> list[tuple[str, float]]:
        """
        Predict category + confidence for each transaction.
        Returns list of (category, confidence_score) tuples.
        """
        if self._pipeline is None:
            raise RuntimeError("Model not trained. Call train() or load() first.")

        X = self._make_feature(transactions)
        proba = self._pipeline.predict_proba(X)
        classes = self._pipeline.classes_

        results = []
        for p in proba:
            idx = np.argmax(p)
            results.append((classes[idx], float(p[idx])))
        return results

    def categorize(
        self,
        transactions: list[Transaction],
        llm_fallback_fn: callable | None = None,
    ) -> list[CategorizedTransaction]:
        """
        Full categorization pipeline with LLM fallback.
        Returns CategorizedTransaction objects ready for the warehouse.
        """
        predictions = self.predict(transactions)
        categorized = []

        for txn, (category, confidence) in zip(transactions, predictions):
            source: Literal["ml_model", "llm_fallback", "rule_based"] = "ml_model"

            if confidence < CONFIDENCE_THRESHOLD and llm_fallback_fn is not None:
                category = llm_fallback_fn(txn)
                confidence = 1.0  # LLM classified, trust it
                source = "llm_fallback"
                logger.debug("LLM fallback used for tx=%s", txn.transaction_id)

            categorized.append(CategorizedTransaction(
                **txn.model_dump(),
                our_category=category,
                confidence_score=confidence,
                is_income=category.startswith("income_"),
                is_recurring=category in {"rent_mortgage", "utilities", "subscription", "debt_payment"},
                is_essential=category in {"rent_mortgage", "utilities", "groceries", "healthcare"},
                categorization_source=source,
            ))

        low_conf = sum(1 for _, (_, c) in zip(transactions, predictions) if c < CONFIDENCE_THRESHOLD)
        logger.info(
            "Categorized %d transactions | low_confidence=%d (%.1f%%)",
            len(transactions), low_conf, 100 * low_conf / max(len(transactions), 1)
        )
        return categorized

    def save(self, path: Path) -> None:
        """Persist trained model."""
        with open(path, "wb") as f:
            pickle.dump(self._pipeline, f)
        logger.info("Model saved to %s", path)

    def load(self, path: Path) -> None:
        """Load persisted model."""
        with open(path, "rb") as f:
            self._pipeline = pickle.load(f)
