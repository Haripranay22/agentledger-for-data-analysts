"""
Demo data for the credit analysis dashboard.
Generates a realistic borrower profile without requiring API keys.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

DEMO_STATE: dict[str, Any] = {
    "user_id": "USER_001",
    "loan_amount": 15000.0,
    "loan_purpose": "Home Improvement",
    "run_id": "demo-" + str(uuid.uuid4())[:8],
    "final_report_path": None,
    "escalate_to_human": False,
    "escalation_reasons": [],
    "retry_count": 0,
    "metrics": {
        "user_id": "USER_001",
        "avg_monthly_income": 5500.00,
        "income_cv": 0.083,
        "avg_monthly_expenses": 3220.00,
        "dti_ratio": 0.118,
        "total_nsf_events": 0,
        "discretionary_spending_ratio": 0.31,
        "rent_to_income_ratio": 0.327,
        "cash_buffer_days": 42.5,
        "months_analyzed": 6,
    },
    "risk_assessment": {
        "risk_score": 26,
        "recommendation": "approve",
        "confidence": 0.91,
        "reasoning_summary": (
            "Borrower demonstrates strong income stability with consistent W-2 deposits "
            "and a healthy debt-to-income ratio well below the 36% threshold. "
            "Zero NSF events and 42 days of cash buffer indicate sound financial management."
        ),
        "risk_factors": [
            {
                "description": "Moderate discretionary spending (31%) warrants monitoring",
                "severity": "low",
                "citations": ["tx:demo_001", "tx:demo_002"],
            },
        ],
        "strengths": [
            {
                "description": "Consistent W-2 salary deposits every 2 weeks — high income predictability",
                "severity": "low",
                "citations": ["tx:demo_010", "tx:demo_011", "tx:demo_012"],
            },
            {
                "description": "Zero NSF/overdraft events across 6 months of history",
                "severity": "low",
                "citations": [],
            },
            {
                "description": "DTI ratio of 11.8% is well below the 36% threshold",
                "severity": "low",
                "citations": ["tx:demo_020", "tx:demo_021"],
            },
        ],
        "insufficient_data_areas": [],
    },
    "validation_result": {
        "overall_validity": 0.97,
        "passed": True,
        "hallucinated_claims": [],
        "citation_checks": [],
        "feedback_for_risk_analyst": None,
    },
}


def _make_date(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


DEMO_TRANSACTIONS: list[dict[str, Any]] = [
    # Income — bi-weekly salary
    {"id": "tx:demo_010", "date": _make_date(3),  "amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_011", "date": _make_date(17), "amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_012", "date": _make_date(31), "amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_013", "date": _make_date(45), "amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_014", "date": _make_date(59), "amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_015", "date": _make_date(73), "amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_016", "date": _make_date(87), "amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_017", "date": _make_date(101),"amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_018", "date": _make_date(115),"amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_019", "date": _make_date(129),"amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_019b","date": _make_date(143),"amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    {"id": "tx:demo_019c","date": _make_date(157),"amount": 2750.00,  "merchant": "ACME Corp Payroll",      "category": "income_salary",    "is_income": True,  "is_recurring": True},
    # Rent
    {"id": "tx:demo_030", "date": _make_date(5),  "amount": -1800.00, "merchant": "Greenway Apartments",   "category": "rent_mortgage",    "is_income": False, "is_recurring": True},
    {"id": "tx:demo_031", "date": _make_date(35), "amount": -1800.00, "merchant": "Greenway Apartments",   "category": "rent_mortgage",    "is_income": False, "is_recurring": True},
    {"id": "tx:demo_032", "date": _make_date(65), "amount": -1800.00, "merchant": "Greenway Apartments",   "category": "rent_mortgage",    "is_income": False, "is_recurring": True},
    {"id": "tx:demo_033", "date": _make_date(95), "amount": -1800.00, "merchant": "Greenway Apartments",   "category": "rent_mortgage",    "is_income": False, "is_recurring": True},
    {"id": "tx:demo_034", "date": _make_date(125),"amount": -1800.00, "merchant": "Greenway Apartments",   "category": "rent_mortgage",    "is_income": False, "is_recurring": True},
    {"id": "tx:demo_035", "date": _make_date(155),"amount": -1800.00, "merchant": "Greenway Apartments",   "category": "rent_mortgage",    "is_income": False, "is_recurring": True},
    # Debt payment
    {"id": "tx:demo_020", "date": _make_date(8),  "amount": -325.00,  "merchant": "Navient Student Loan",  "category": "debt_payment",     "is_income": False, "is_recurring": True},
    {"id": "tx:demo_021", "date": _make_date(38), "amount": -325.00,  "merchant": "Navient Student Loan",  "category": "debt_payment",     "is_income": False, "is_recurring": True},
    {"id": "tx:demo_022", "date": _make_date(68), "amount": -325.00,  "merchant": "Navient Student Loan",  "category": "debt_payment",     "is_income": False, "is_recurring": True},
    {"id": "tx:demo_023", "date": _make_date(98), "amount": -325.00,  "merchant": "Navient Student Loan",  "category": "debt_payment",     "is_income": False, "is_recurring": True},
    {"id": "tx:demo_024", "date": _make_date(128),"amount": -325.00,  "merchant": "Navient Student Loan",  "category": "debt_payment",     "is_income": False, "is_recurring": True},
    {"id": "tx:demo_025", "date": _make_date(158),"amount": -325.00,  "merchant": "Navient Student Loan",  "category": "debt_payment",     "is_income": False, "is_recurring": True},
    # Utilities
    {"id": "tx:demo_040", "date": _make_date(10), "amount": -85.00,   "merchant": "City Electric Co",      "category": "utilities",        "is_income": False, "is_recurring": True},
    {"id": "tx:demo_041", "date": _make_date(40), "amount": -92.00,   "merchant": "City Electric Co",      "category": "utilities",        "is_income": False, "is_recurring": True},
    {"id": "tx:demo_042", "date": _make_date(70), "amount": -78.00,   "merchant": "City Electric Co",      "category": "utilities",        "is_income": False, "is_recurring": True},
    {"id": "tx:demo_043", "date": _make_date(100),"amount": -88.00,   "merchant": "City Electric Co",      "category": "utilities",        "is_income": False, "is_recurring": True},
    {"id": "tx:demo_044", "date": _make_date(130),"amount": -95.00,   "merchant": "City Electric Co",      "category": "utilities",        "is_income": False, "is_recurring": True},
    {"id": "tx:demo_045", "date": _make_date(160),"amount": -81.00,   "merchant": "City Electric Co",      "category": "utilities",        "is_income": False, "is_recurring": True},
    # Groceries
    {"id": "tx:demo_050", "date": _make_date(4),  "amount": -145.00,  "merchant": "Whole Foods Market",    "category": "groceries",        "is_income": False, "is_recurring": False},
    {"id": "tx:demo_051", "date": _make_date(12), "amount": -132.00,  "merchant": "Trader Joes",           "category": "groceries",        "is_income": False, "is_recurring": False},
    {"id": "tx:demo_052", "date": _make_date(25), "amount": -158.00,  "merchant": "Whole Foods Market",    "category": "groceries",        "is_income": False, "is_recurring": False},
    {"id": "tx:demo_053", "date": _make_date(42), "amount": -141.00,  "merchant": "Costco",                "category": "groceries",        "is_income": False, "is_recurring": False},
    {"id": "tx:demo_054", "date": _make_date(55), "amount": -129.00,  "merchant": "Trader Joes",           "category": "groceries",        "is_income": False, "is_recurring": False},
    {"id": "tx:demo_055", "date": _make_date(80), "amount": -168.00,  "merchant": "Whole Foods Market",    "category": "groceries",        "is_income": False, "is_recurring": False},
    # Dining / discretionary
    {"id": "tx:demo_001", "date": _make_date(6),  "amount": -48.50,   "merchant": "Chipotle",              "category": "dining_entertainment","is_income": False,"is_recurring": False},
    {"id": "tx:demo_002", "date": _make_date(14), "amount": -62.00,   "merchant": "Netflix",               "category": "subscription",     "is_income": False, "is_recurring": True},
    {"id": "tx:demo_003", "date": _make_date(22), "amount": -35.00,   "merchant": "Spotify",               "category": "subscription",     "is_income": False, "is_recurring": True},
    {"id": "tx:demo_004", "date": _make_date(30), "amount": -89.00,   "merchant": "AMC Theaters",          "category": "dining_entertainment","is_income": False,"is_recurring": False},
    {"id": "tx:demo_005", "date": _make_date(48), "amount": -124.00,  "merchant": "Delta Airlines",        "category": "dining_entertainment","is_income": False,"is_recurring": False},
    # Transportation
    {"id": "tx:demo_060", "date": _make_date(2),  "amount": -55.00,   "merchant": "Shell Gas Station",     "category": "transportation",   "is_income": False, "is_recurring": False},
    {"id": "tx:demo_061", "date": _make_date(18), "amount": -52.00,   "merchant": "Exxon",                 "category": "transportation",   "is_income": False, "is_recurring": False},
    {"id": "tx:demo_062", "date": _make_date(50), "amount": -48.00,   "merchant": "Shell Gas Station",     "category": "transportation",   "is_income": False, "is_recurring": False},
    {"id": "tx:demo_063", "date": _make_date(90), "amount": -320.00,  "merchant": "Jiffy Lube",            "category": "transportation",   "is_income": False, "is_recurring": False},
]


def get_monthly_income_series() -> tuple[list[str], list[float]]:
    """Returns (month_labels, income_values) for the income trend chart."""
    from datetime import date
    today = date.today()
    months = []
    values = []
    for i in range(5, -1, -1):
        m = (today.month - i - 1) % 12 + 1
        y = today.year - ((today.month - i - 1) // 12)
        label = date(y, m, 1).strftime("%b %Y")
        months.append(label)
        # Slight variation around $5,500 to simulate real income
        base = 5500.0
        variation = [0, 0, 0, 0, 0, 5500][i % 6]  # consistent W-2
        values.append(base + ([-50, 0, 50, -25, 0, 25][i]))
    return months, values


def get_expense_breakdown() -> dict[str, float]:
    """Category → avg monthly spend for donut chart."""
    return {
        "Rent / Mortgage": 1800.00,
        "Debt Payments": 325.00,
        "Groceries": 145.50,
        "Utilities": 86.50,
        "Dining & Entertainment": 75.83,
        "Subscriptions": 16.25,
        "Transportation": 79.17,
        "Other": 36.58,
    }
