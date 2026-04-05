"""
Unified property + mortgage report combining deeds and bank statement data.
"""
from typing import Optional
from pydantic import BaseModel


# ── Deeds data ────────────────────────────────────────────────────────────────

class PropertyInfo(BaseModel):
    erf_number: Optional[str] = None
    portion: Optional[str] = None
    township: Optional[str] = None
    registration_division: Optional[str] = None
    province: Optional[str] = None
    street_address: Optional[str] = None
    suburb: Optional[str] = None
    city: Optional[str] = None
    land_size_sqm: Optional[float] = None
    property_type: Optional[str] = None          # Residential / Sectional / Commercial
    sectional_scheme_name: Optional[str] = None
    sectional_unit_number: Optional[str] = None
    lpi_code: Optional[str] = None               # Land Parcel Identifier


class TitleDeed(BaseModel):
    deed_number: Optional[str] = None
    registration_date: Optional[str] = None
    deeds_office: Optional[str] = None           # e.g. Johannesburg, Cape Town


class OwnerRecord(BaseModel):
    owner_name: Optional[str] = None
    owner_type: Optional[str] = None             # Individual / Company / Trust / CC
    id_or_reg_number: Optional[str] = None
    transfer_date: Optional[str] = None
    purchase_price: Optional[str] = None


class BondRecord(BaseModel):
    bond_number: Optional[str] = None
    registered_amount: Optional[str] = None
    bond_holder_bank: Optional[str] = None
    registration_date: Optional[str] = None
    cancellation_date: Optional[str] = None      # populated if bond was cancelled
    status: Optional[str] = None                 # Active / Cancelled


class DeedsData(BaseModel):
    property: PropertyInfo
    title_deed: TitleDeed
    current_owner: OwnerRecord
    ownership_history: list[OwnerRecord] = []
    bonds: list[BondRecord] = []                 # all bonds, including cancelled
    interdicts: list[str] = []
    servitudes: list[str] = []
    source: str = "Deeds Registry"
    retrieved_at: Optional[str] = None


# ── Bank statement data ───────────────────────────────────────────────────────

class PaymentRecord(BaseModel):
    date: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[str] = None
    balance_after: Optional[str] = None


class StatementData(BaseModel):
    bank: Optional[str] = None
    account_number: Optional[str] = None
    account_holder: Optional[str] = None
    statement_date: Optional[str] = None
    statement_period: Optional[str] = None

    # Core loan figures
    outstanding_balance: Optional[str] = None
    original_loan_amount: Optional[str] = None
    current_interest_rate: Optional[str] = None
    monthly_repayment: Optional[str] = None
    next_payment_date: Optional[str] = None
    remaining_term_months: Optional[int] = None

    # Arrears
    arrears_amount: Optional[str] = None
    arrears_months: Optional[int] = None

    # Payment history
    last_payment_date: Optional[str] = None
    last_payment_amount: Optional[str] = None
    payment_history: list[PaymentRecord] = []

    # Fees
    service_fee: Optional[str] = None
    other_fees: Optional[str] = None

    source: str = "Bank Statement"


# ── Combined report ───────────────────────────────────────────────────────────

class PropertyReport(BaseModel):
    """
    Full picture of a South African home loan — deeds data + live statement data.
    """
    deeds: Optional[DeedsData] = None
    statement: Optional[StatementData] = None
    generated_at: Optional[str] = None
    completeness: dict = {}                      # which sections were successfully populated

    def summary(self) -> dict:
        active_bonds = [b for b in (self.deeds.bonds if self.deeds else []) if b.status == "Active"]
        return {
            "property_address": self.deeds.property.street_address if self.deeds else None,
            "erf_number": self.deeds.property.erf_number if self.deeds else None,
            "title_deed": self.deeds.title_deed.deed_number if self.deeds else None,
            "current_owner": self.deeds.current_owner.owner_name if self.deeds else None,
            "active_bonds": len(active_bonds),
            "bond_holder": active_bonds[0].bond_holder_bank if active_bonds else None,
            "registered_amount": active_bonds[0].registered_amount if active_bonds else None,
            "outstanding_balance": self.statement.outstanding_balance if self.statement else None,
            "current_interest_rate": self.statement.current_interest_rate if self.statement else None,
            "monthly_repayment": self.statement.monthly_repayment if self.statement else None,
            "arrears": self.statement.arrears_amount if self.statement else None,
        }
