from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class TransactionCategory(str, Enum):
    INCOME = "income"
    HOUSING = "housing"
    BOND_REPAYMENT = "bond_repayment"
    GROCERIES = "groceries"
    FOOD_DINING = "food_dining"
    ALCOHOL = "alcohol"
    GAMBLING = "gambling"
    FUEL = "fuel"
    TRANSPORT = "transport"
    INSURANCE = "insurance"
    MEDICAL = "medical"
    EDUCATION = "education"
    SUBSCRIPTIONS = "subscriptions"
    SAVINGS = "savings"
    CLOTHING = "clothing"
    TRANSFERS = "transfers"
    FEES = "fees"
    OTHER = "other"


class Transaction(BaseModel):
    date: str
    description: str
    amount: float           # positive = credit (income), negative = debit (expense)
    category: TransactionCategory
    is_income: bool = False
    raw_description: str = ""


class ExpenseBreakdown(BaseModel):
    total_income: float = 0.0
    total_expenses: float = 0.0
    net_cash_flow: float = 0.0
    by_category: dict[str, float] = {}
    transaction_count: dict[str, int] = {}
    salary_credits: list[float] = []
    largest_expenses: list[dict] = []


class WasteSaving(BaseModel):
    category: str
    current_monthly: float
    suggested_monthly: float
    monthly_saving: float
    bond_increase: float
    description: str


class AffordabilityResult(BaseModel):
    gross_monthly_income: float
    estimated_monthly_tax: float
    net_monthly_income: float
    total_monthly_debt: float
    total_monthly_living: float
    net_disposable_income: float

    max_monthly_repayment: float
    max_bond_amount: float
    current_bond_amount: Optional[float] = None
    affordability_gap: Optional[float] = None

    interest_rate_used: float
    term_years: int = 20

    waste_savings: list[WasteSaving] = []
    optimised_max_bond: float = 0.0

    affordability_score: str = ""
    affordability_notes: list[str] = []


class BehaviourChange(BaseModel):
    field: str
    category: Optional[str] = None
    previous_value: float
    current_value: float
    change_pct: float
    direction: str      # "up" | "down"
    severity: str       # "info" | "warning" | "alert"
    message: str


class CustomerProfile(BaseModel):
    user_id: int
    period: str
    statement_period: Optional[str] = None

    gross_monthly_income: float = 0.0
    net_monthly_income: float = 0.0
    income_sources: list[str] = []

    expense_breakdown: ExpenseBreakdown = ExpenseBreakdown()
    affordability: Optional[AffordabilityResult] = None

    transactions: list[Transaction] = []

    bank_detected: Optional[str] = None
    parse_confidence: float = 0.0
    created_at: Optional[str] = None
