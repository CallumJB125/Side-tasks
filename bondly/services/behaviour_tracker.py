"""
Detect meaningful changes in a customer's financial behaviour between two periods.

Designed to run month-on-month after customers upload successive statements.
Changes are ranked alert > warning > info so the most critical surface first.
"""
from __future__ import annotations
from bondly.models.profile import BehaviourChange, CustomerProfile

# Thresholds: fraction change that triggers each severity level
_THRESHOLDS: dict[str, dict[str, float]] = {
    "income":          {"warning": 0.10, "alert": 0.20},
    "net_cash_flow":   {"warning": 0.15, "alert": 0.30},
    "total_expenses":  {"warning": 0.10, "alert": 0.25},
    "gambling":        {"warning": 0.01, "alert": 0.50},  # any increase = warning
    "alcohol":         {"warning": 0.20, "alert": 0.50},
    "food_dining":     {"warning": 0.25, "alert": 0.50},
    "subscriptions":   {"warning": 0.25, "alert": 0.50},
    "fees":            {"warning": 0.25, "alert": 0.50},
}

# Categories whose first appearance is an automatic alert
_RISKY_NEW_CATEGORIES = {"gambling"}

# Categories where an increase is a positive signal
_POSITIVE_CATEGORIES = {"savings", "education"}


def detect_changes(previous: CustomerProfile, current: CustomerProfile) -> list[BehaviourChange]:
    """
    Compare two monthly profiles and return a sorted list of behaviour changes.
    `previous` is the older period, `current` is the newer one.
    """
    changes: list[BehaviourChange] = []

    prev_b = previous.expense_breakdown
    curr_b = current.expense_breakdown

    # Top-line metrics
    _check(changes, "gross_monthly_income",
           previous.gross_monthly_income, current.gross_monthly_income,
           threshold_key="income", lower_is_worse=True)

    _check(changes, "net_cash_flow",
           prev_b.net_cash_flow, curr_b.net_cash_flow,
           threshold_key="net_cash_flow", lower_is_worse=True)

    _check(changes, "total_expenses",
           prev_b.total_expenses, curr_b.total_expenses,
           threshold_key="total_expenses", lower_is_worse=False)

    # Per-category changes
    all_cats = set(prev_b.by_category) | set(curr_b.by_category)
    for cat in all_cats:
        prev_val = prev_b.by_category.get(cat, 0.0)
        curr_val = curr_b.by_category.get(cat, 0.0)

        # New risky category — automatic alert
        if prev_val == 0 and curr_val > 0 and cat in _RISKY_NEW_CATEGORIES:
            changes.append(BehaviourChange(
                field="category_spending",
                category=cat,
                previous_value=0.0,
                current_value=round(curr_val, 2),
                change_pct=100.0,
                direction="up",
                severity="alert",
                message=(
                    f"New {cat} spending detected (R{curr_val:,.0f}/month). "
                    "SA banks automatically flag gambling on bond applications — "
                    "3–6 months of clean statements are required before applying."
                ),
            ))
            continue

        # Positive trend
        if cat in _POSITIVE_CATEGORIES and curr_val > prev_val and prev_val > 0:
            pct = (curr_val - prev_val) / prev_val * 100
            changes.append(BehaviourChange(
                field="category_spending",
                category=cat,
                previous_value=round(prev_val, 2),
                current_value=round(curr_val, 2),
                change_pct=round(pct, 1),
                direction="up",
                severity="info",
                message=f"{cat.replace('_', ' ').title()} up {pct:.0f}% — positive financial behaviour that strengthens bond applications.",
            ))
            continue

        # Threshold-based change for tracked categories
        if cat in _THRESHOLDS and prev_val > 0:
            _check(changes, "category_spending",
                   prev_val, curr_val,
                   threshold_key=cat, lower_is_worse=False,
                   category=cat)

    # Sort: alert first, then warning, then info
    _severity_order = {"alert": 0, "warning": 1, "info": 2}
    changes.sort(key=lambda c: _severity_order.get(c.severity, 3))
    return changes


def _check(
    changes: list[BehaviourChange],
    field: str,
    prev: float,
    curr: float,
    threshold_key: str,
    lower_is_worse: bool,
    category: str | None = None,
) -> None:
    if prev == 0:
        return

    pct = (curr - prev) / abs(prev)
    abs_pct = abs(pct)
    thresholds = _THRESHOLDS.get(threshold_key, {"warning": 0.10, "alert": 0.20})

    if abs_pct < thresholds["warning"]:
        return

    direction = "up" if curr > prev else "down"
    severity = "alert" if abs_pct >= thresholds["alert"] else "warning"

    # For metrics where lower is worse (income, cash flow): going down is bad, up is good
    if lower_is_worse and direction == "up":
        severity = "info"

    changes.append(BehaviourChange(
        field=field,
        category=category,
        previous_value=round(prev, 2),
        current_value=round(curr, 2),
        change_pct=round(pct * 100, 1),
        direction=direction,
        severity=severity,
        message=_message(field, category, direction, prev, curr, abs_pct),
    ))


def _message(field: str, category: str | None, direction: str, prev: float, curr: float, pct: float) -> str:
    label = (category or field).replace("_", " ")
    verb = "increased" if direction == "up" else "decreased"
    return f"{label.title()} {verb} by {pct * 100:.0f}% (R{prev:,.0f} → R{curr:,.0f}/month)."
