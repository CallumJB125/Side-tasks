"""
South African mortgage affordability calculator.

Uses NCA (National Credit Act) and standard SA bank guidelines:
- NDI (Net Disposable Income) = gross income - PAYE - existing debt - living costs
- Max new bond repayment ≤ NDI × 0.40
- Bond amount derived from annuity formula: PV at prime rate over 20 years
"""
from __future__ import annotations
from bondly.models.profile import AffordabilityResult, ExpenseBreakdown, WasteSaving

# NCA-aligned ratio: max new debt repayment as fraction of NDI
_NDI_RATIO = 0.40

# Suggested monthly caps for "waste" categories
_WASTE_TARGETS: dict[str, float] = {
    "alcohol": 0.0,
    "gambling": 0.0,
    "food_dining": 1500.0,
    "subscriptions": 500.0,
}

_DEBT_CATEGORIES = {"bond_repayment", "housing"}


# ---------------------------------------------------------------------------
# SARS PAYE — 2024/25 tax year (1 March 2024 – 28 February 2025)
# ---------------------------------------------------------------------------

_BRACKETS = [
    # (upper_limit, marginal_rate, cumulative_tax_at_lower_limit, lower_limit)
    (237_100,   0.18, 0,        0),
    (370_500,   0.26, 42_678,   237_100),
    (512_800,   0.31, 77_362,   370_500),
    (673_000,   0.36, 121_475,  512_800),
    (857_900,   0.39, 179_147,  673_000),
    (1_817_000, 0.41, 251_258,  857_900),
    (float("inf"), 0.45, 644_489, 1_817_000),
]
_PRIMARY_REBATE = 17_235


def _annual_paye(annual_gross: float) -> float:
    for upper, rate, base, lower in _BRACKETS:
        if annual_gross <= upper:
            tax = base + (annual_gross - lower) * rate
            return max(0.0, tax - _PRIMARY_REBATE)
    return max(0.0, annual_gross * 0.45 - _PRIMARY_REBATE)


# ---------------------------------------------------------------------------
# Bond maths
# ---------------------------------------------------------------------------

def _bond_from_repayment(monthly_repayment: float, annual_rate: float, term_years: int) -> float:
    """PV of an annuity — max bond given a monthly repayment capacity."""
    if annual_rate <= 0 or monthly_repayment <= 0:
        return 0.0
    r = annual_rate / 100 / 12
    n = term_years * 12
    return monthly_repayment * (1 - (1 + r) ** -n) / r


# ---------------------------------------------------------------------------
# Main calculator
# ---------------------------------------------------------------------------

def calculate_affordability(
    breakdown: ExpenseBreakdown,
    current_bond_amount: float | None = None,
    annual_interest_rate: float = 11.75,
    term_years: int = 20,
) -> AffordabilityResult:
    gross = breakdown.total_income
    by_cat = breakdown.by_category

    # Split expenses into debt vs living
    debt_total = sum(v for k, v in by_cat.items() if k in _DEBT_CATEGORIES)
    living_total = sum(v for k, v in by_cat.items() if k not in _DEBT_CATEGORIES)

    # Tax (monthly PAYE estimate)
    monthly_tax = _annual_paye(gross * 12) / 12
    net_income = gross - monthly_tax

    # NDI = net income minus all committed expenses
    ndi = net_income - debt_total - living_total

    # Max repayment & bond
    max_repayment = max(0.0, ndi * _NDI_RATIO)
    max_bond = _bond_from_repayment(max_repayment, annual_interest_rate, term_years)

    gap = (max_bond - current_bond_amount) if current_bond_amount is not None else None

    # Waste analysis
    waste = _waste_savings(by_cat, annual_interest_rate, term_years)
    total_freed = sum(w.monthly_saving for w in waste)
    optimised_repayment = max_repayment + total_freed * _NDI_RATIO
    optimised_bond = _bond_from_repayment(optimised_repayment, annual_interest_rate, term_years)

    score, notes = _score(gross, ndi, by_cat)

    return AffordabilityResult(
        gross_monthly_income=round(gross, 2),
        estimated_monthly_tax=round(monthly_tax, 2),
        net_monthly_income=round(net_income, 2),
        total_monthly_debt=round(debt_total, 2),
        total_monthly_living=round(living_total, 2),
        net_disposable_income=round(ndi, 2),
        max_monthly_repayment=round(max_repayment, 2),
        max_bond_amount=round(max_bond, 2),
        current_bond_amount=round(current_bond_amount, 2) if current_bond_amount is not None else None,
        affordability_gap=round(gap, 2) if gap is not None else None,
        interest_rate_used=annual_interest_rate,
        term_years=term_years,
        waste_savings=waste,
        optimised_max_bond=round(optimised_bond, 2),
        affordability_score=score,
        affordability_notes=notes,
    )


def _waste_savings(
    by_cat: dict[str, float],
    annual_rate: float,
    term_years: int,
) -> list[WasteSaving]:
    results = []
    for cat, target in _WASTE_TARGETS.items():
        actual = by_cat.get(cat, 0.0)
        if actual <= target:
            continue
        saving = actual - target
        bond_increase = _bond_from_repayment(saving * _NDI_RATIO, annual_rate, term_years)

        labels = {
            "alcohol": f"Cutting alcohol spending (R{actual:,.0f} → R0/month) unlocks R{bond_increase:,.0f} more bond.",
            "gambling": f"Stopping gambling (R{actual:,.0f}/month) unlocks R{bond_increase:,.0f} more bond — and most SA banks decline applicants with gambling transactions.",
            "food_dining": f"Capping eating out at R{target:,.0f}/month (currently R{actual:,.0f}) unlocks R{bond_increase:,.0f} more bond.",
            "subscriptions": f"Trimming subscriptions to R{target:,.0f}/month (currently R{actual:,.0f}) unlocks R{bond_increase:,.0f} more bond.",
        }
        results.append(WasteSaving(
            category=cat,
            current_monthly=round(actual, 2),
            suggested_monthly=round(target, 2),
            monthly_saving=round(saving, 2),
            bond_increase=round(bond_increase, 2),
            description=labels.get(cat, f"Reducing {cat} from R{actual:,.0f} to R{target:,.0f}/month."),
        ))
    return results


def _score(gross: float, ndi: float, by_cat: dict) -> tuple[str, list[str]]:
    notes: list[str] = []

    if gross == 0:
        return "Unknown", ["No income detected — upload a current/cheque account statement."]

    ratio = ndi / gross

    gambling = by_cat.get("gambling", 0.0)
    alcohol = by_cat.get("alcohol", 0.0)

    if gambling > 0:
        notes.append(
            f"Gambling detected (R{gambling:,.0f}/month). Most SA banks automatically decline "
            "bond applications when gambling transactions appear on statements."
        )
    if alcohol > 2_000:
        notes.append(
            f"High alcohol spending (R{alcohol:,.0f}/month) is flagged by bank affordability assessors."
        )
    if ndi < 0:
        notes.append("Monthly expenses exceed income — no capacity for bond repayments at current spending levels.")

    if ratio > 0.20:
        return "Strong", notes
    if ratio > 0.05:
        return "Moderate", notes
    if ratio > 0:
        return "Tight", notes
    return "Distressed", notes
