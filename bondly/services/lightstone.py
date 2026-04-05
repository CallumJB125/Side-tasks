"""
Lightstone Property API adapter.

Two implementations:
  - LightstoneMockClient   — returns realistic fake data for development/testing
  - LightstoneClient       — real HTTP calls to portal.apis.lightstone.co.za

Switch between them via LIGHTSTONE_MOCK_MODE in bondly/.env.

Once Lightstone approves your account at portal.apis.lightstone.co.za:
  1. Set LIGHTSTONE_MOCK_MODE=False
  2. Set LIGHTSTONE_API_KEY=<your subscription key>
  3. Verify the endpoint paths below match what Lightstone gives you
     (they provide these after contract signing — paths are not public).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests

from bondly.config import get_settings
from bondly.models.mortgage import (
    BondRegistration,
    MortgageReport,
    OwnershipRecord,
    PropertyDetails,
    PropertyValuation,
)

_settings = get_settings()

# ---------------------------------------------------------------------------
# Lightstone endpoint paths (fill in once you have portal access)
# ---------------------------------------------------------------------------
_ENDPOINTS = {
    "property_search":  "/api/property/search",       # GET ?address=...
    "property_detail":  "/api/property/{erf_key}",    # GET
    "bond_detail":      "/api/property/{erf_key}/bond",
    "valuation":        "/api/property/{erf_key}/valuation",
    "ownership":        "/api/property/{erf_key}/ownership",
}


def _mask_id(id_number: str) -> str:
    """Partially mask a SA ID number for privacy."""
    if len(id_number) >= 13:
        return id_number[:6] + "****" + id_number[-3:]
    return id_number[:4] + "****"


# ---------------------------------------------------------------------------
# Real client
# ---------------------------------------------------------------------------

class LightstoneClient:
    def __init__(self):
        self._base = _settings.lightstone_base_url.rstrip("/")
        self._headers = {
            "Ocp-Apim-Subscription-Key": _settings.lightstone_api_key,
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = self._base + path
        resp = requests.get(url, headers=self._headers, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def search_property(self, address: str) -> list[dict]:
        """Search for a property by address. Returns a list of matches."""
        return self._get(_ENDPOINTS["property_search"], {"address": address})

    def get_mortgage_report(
        self,
        erf_key: str,
        owner_id_number: str,
    ) -> MortgageReport:
        prop    = self._get(_ENDPOINTS["property_detail"].format(erf_key=erf_key))
        bond    = self._get(_ENDPOINTS["bond_detail"].format(erf_key=erf_key))
        val     = self._get(_ENDPOINTS["valuation"].format(erf_key=erf_key))
        own     = self._get(_ENDPOINTS["ownership"].format(erf_key=erf_key))

        return _map_to_report(prop, bond, val, own, owner_id_number)


def _map_to_report(prop: dict, bond: dict, val: dict, own: dict, owner_id: str) -> MortgageReport:
    """
    Map raw Lightstone API response dicts to MortgageReport.
    Field names here are guesses based on Lightstone's known data model —
    adjust to match actual response keys once you have API access.
    """
    return MortgageReport(
        property=PropertyDetails(
            erf_number=prop.get("erfNumber") or prop.get("erf_number"),
            title_deed_number=prop.get("titleDeedNumber") or prop.get("title_deed"),
            street_address=prop.get("streetAddress") or prop.get("address"),
            suburb=prop.get("suburb"),
            city=prop.get("city") or prop.get("town"),
            province=prop.get("province"),
            land_size_sqm=prop.get("landSize") or prop.get("erf_size"),
            property_type=prop.get("propertyType") or prop.get("property_type"),
        ),
        ownership=OwnershipRecord(
            owner_name=own.get("ownerName") or own.get("owner_name"),
            id_number_masked=_mask_id(owner_id),
            transfer_date=own.get("transferDate") or own.get("transfer_date"),
            purchase_price=own.get("purchasePrice") or own.get("last_sale_price"),
        ),
        bond_registration=BondRegistration(
            registered_amount=bond.get("bondAmount") or bond.get("registered_amount"),
            registration_date=bond.get("registrationDate") or bond.get("registration_date"),
            bond_number=bond.get("bondNumber") or bond.get("bond_number"),
            bond_holder_bank=bond.get("bondHolder") or bond.get("bondholder_name"),
        ),
        valuation=PropertyValuation(
            estimated_value=val.get("estimatedValue") or val.get("avm_value"),
            valuation_date=val.get("valuationDate") or val.get("valuation_date"),
            valuation_band_low=val.get("bandLow") or val.get("band_low"),
            valuation_band_high=val.get("bandHigh") or val.get("band_high"),
        ),
        retrieved_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Mock client — realistic South African data for development
# ---------------------------------------------------------------------------

class LightstoneMockClient:

    _MOCK_PROPERTIES = [
        {
            "erf_key": "GP-JHB-ERF-0012345",
            "address": "12 Sandton Drive, Sandton, Johannesburg",
            "suburb": "Sandton",
            "city": "Johannesburg",
            "province": "Gauteng",
            "erf_number": "ERF 12345",
            "title_deed": "T45678/2019",
            "land_size_sqm": 650.0,
            "property_type": "Residential",
            "bond_amount": "R 1 850 000",
            "bond_date": "2019-06-15",
            "bond_number": "B123456/2019",
            "bond_holder": "Standard Bank of South Africa",
            "owner_name": "J SMITH",
            "transfer_date": "2019-06-15",
            "purchase_price": "R 2 300 000",
            "avm_value": "R 2 650 000",
            "valuation_date": "2026-01-15",
            "band_low": "R 2 450 000",
            "band_high": "R 2 850 000",
        },
        {
            "erf_key": "WC-CPT-ERF-0078901",
            "address": "7 Kloof Street, Gardens, Cape Town",
            "suburb": "Gardens",
            "city": "Cape Town",
            "province": "Western Cape",
            "erf_number": "ERF 78901",
            "title_deed": "T11234/2021",
            "land_size_sqm": 420.0,
            "property_type": "Residential",
            "bond_amount": "R 3 200 000",
            "bond_date": "2021-03-22",
            "bond_number": "B987654/2021",
            "bond_holder": "FirstRand Bank Limited (FNB)",
            "owner_name": "P VAN DER MERWE",
            "transfer_date": "2021-03-22",
            "purchase_price": "R 4 100 000",
            "avm_value": "R 4 850 000",
            "valuation_date": "2026-01-15",
            "band_low": "R 4 500 000",
            "band_high": "R 5 200 000",
        },
    ]

    def search_property(self, address: str) -> list[dict]:
        """Fuzzy-match on address from mock data."""
        term = address.lower()
        return [
            {"erf_key": p["erf_key"], "address": p["address"], "suburb": p["suburb"], "city": p["city"]}
            for p in self._MOCK_PROPERTIES
            if term in p["address"].lower() or any(w in p["address"].lower() for w in term.split())
        ] or [
            {"erf_key": p["erf_key"], "address": p["address"], "suburb": p["suburb"], "city": p["city"]}
            for p in self._MOCK_PROPERTIES[:1]
        ]

    def get_mortgage_report(self, erf_key: str, owner_id_number: str) -> MortgageReport:
        prop = next(
            (p for p in self._MOCK_PROPERTIES if p["erf_key"] == erf_key),
            self._MOCK_PROPERTIES[0],
        )
        return MortgageReport(
            property=PropertyDetails(
                erf_number=prop["erf_number"],
                title_deed_number=prop["title_deed"],
                street_address=prop["address"],
                suburb=prop["suburb"],
                city=prop["city"],
                province=prop["province"],
                land_size_sqm=prop["land_size_sqm"],
                property_type=prop["property_type"],
            ),
            ownership=OwnershipRecord(
                owner_name=prop["owner_name"],
                id_number_masked=_mask_id(owner_id_number),
                transfer_date=prop["transfer_date"],
                purchase_price=prop["purchase_price"],
            ),
            bond_registration=BondRegistration(
                registered_amount=prop["bond_amount"],
                registration_date=prop["bond_date"],
                bond_number=prop["bond_number"],
                bond_holder_bank=prop["bond_holder"],
            ),
            valuation=PropertyValuation(
                estimated_value=prop["avm_value"],
                valuation_date=prop["valuation_date"],
                valuation_band_low=prop["band_low"],
                valuation_band_high=prop["band_high"],
            ),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )


def get_client() -> LightstoneClient | LightstoneMockClient:
    if _settings.lightstone_mock_mode:
        return LightstoneMockClient()
    return LightstoneClient()
