from pydantic import BaseModel


class MortgageSearchRequest(BaseModel):
    property_address: str | None = None
    erf_number: str | None = None
    title_deed_number: str | None = None


class BondRegistration(BaseModel):
    registered_amount: str | None
    registration_date: str | None
    bond_number: str | None
    bond_holder_bank: str | None


class PropertyDetails(BaseModel):
    erf_number: str | None
    title_deed_number: str | None
    street_address: str | None
    suburb: str | None
    city: str | None
    province: str | None
    land_size_sqm: float | None
    property_type: str | None


class OwnershipRecord(BaseModel):
    owner_name: str | None
    id_number_masked: str | None    # e.g. 850101****083
    transfer_date: str | None
    purchase_price: str | None


class PropertyValuation(BaseModel):
    estimated_value: str | None
    valuation_date: str | None
    valuation_band_low: str | None
    valuation_band_high: str | None


class MortgageReport(BaseModel):
    """
    Full mortgage data report returned to the homeowner.

    NOTE: bond_registration contains deeds-office data (what was registered).
    Live outstanding balance, current interest rate, and repayment schedule
    are NOT available here — those require a direct query to your bank.
    """
    property: PropertyDetails
    ownership: OwnershipRecord
    bond_registration: BondRegistration
    valuation: PropertyValuation
    source: str = "Lightstone Property"
    retrieved_at: str
    disclaimer: str = (
        "This data reflects the Deeds Registry at time of retrieval. "
        "Outstanding balance and current interest rate must be confirmed "
        "directly with your bondholder bank."
    )
