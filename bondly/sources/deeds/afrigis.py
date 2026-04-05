"""
AfriGIS Property Search & Ownership API adapter.
Auth: OAuth2 client_credentials
Docs: https://developers.afrigis.co.za/oas3/property-search-api/

Field names come from bondly/sources/deeds/field_maps/afrigis.json.
Every mapping is marked UNVERIFIED until tested against real credentials.
Run `python -m bondly.sources.deeds.verify afrigis <erf_key>` after
obtaining credentials to see raw responses and confirm/correct the map.
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from bondly.models.property import (
    BondRecord, DeedsData, OwnerRecord, PropertyInfo, TitleDeed,
)
from bondly.sources.deeds.base import DeedsClient
from bondly.sources.deeds.mapper import DeedsMapper

_AUTH_URL = "https://identity.afrigis.co.za/connect/token"
_BASE     = "https://xdv.afrigis.co.za/rest/api/v3"


class AfriGISClient(DeedsClient):

    def __init__(self, client_id: str, client_secret: str):
        self._client_id     = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._m = DeedsMapper("afrigis")

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        resp = requests.post(
            _AUTH_URL,
            data={
                "grant_type":    "client_credentials",
                "client_id":     self._client_id,
                "client_secret": self._client_secret,
                "scope":         "afrigis.agi",
            },
            timeout=15,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        if not self._token:
            self._get_token()
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        url  = f"{_BASE}{path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=20)
        if resp.status_code == 401:
            self._get_token()
            resp = requests.get(url, headers=self._headers(), params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _to_result(self, raw: dict) -> dict:
        m = self._m
        return {
            "erf_key":    m.get(raw, "search", "erf_key"),
            "address":    m.get(raw, "search", "address"),
            "township":   m.get(raw, "search", "township"),
            "erf_number": m.get(raw, "search", "erf_number"),
            "lpi_code":   m.get(raw, "search", "lpi_code"),
        }

    # ── Search ────────────────────────────────────────────────────────────────

    def search_by_address(self, address: str) -> list[dict]:
        data = self._get("/property/search", {"query": address, "limit": 10})
        return [self._to_result(r) for r in data.get(self._m.results_key("search"), [])]

    def search_by_erf(self, erf_number: str, township: str, deeds_office: str = "") -> list[dict]:
        params = {"erfNumber": erf_number, "township": township}
        if deeds_office:
            params["deedsOffice"] = deeds_office
        data = self._get("/property/erf", params)
        return [self._to_result(r) for r in data.get(self._m.results_key("search_by_erf"), [])]

    def search_by_owner(self, id_number: str) -> list[dict]:
        data = self._get("/deeds/owner", {"idNumber": id_number})
        return [self._to_result(r) for r in data.get(self._m.results_key("search_by_owner"), [])]

    # ── Full record ───────────────────────────────────────────────────────────

    def get_full_record(self, erf_key: str) -> DeedsData:
        prop  = self._get(f"/property/{erf_key}")
        deed  = self._get(f"/deeds/{erf_key}")
        own   = self._get(f"/deeds/{erf_key}/ownership")
        bonds = self._get(f"/deeds/{erf_key}/bonds")

        m = self._m

        current_raw = own.get(m.section_key("ownership", "current_owner_key"), own)
        history_raw = own.get(m.section_key("ownership", "history_key"), [])
        bonds_raw   = bonds.get(m.section_key("bonds", "bonds_key"), [])

        return DeedsData(
            property=PropertyInfo(
                erf_number=            m.get(prop, "property_detail", "erf_number"),
                portion=               m.get(prop, "property_detail", "portion"),
                township=              m.get(prop, "property_detail", "township"),
                registration_division= m.get(prop, "property_detail", "registration_division"),
                province=              m.get(prop, "property_detail", "province"),
                street_address=        m.get(prop, "property_detail", "street_address"),
                suburb=                m.get(prop, "property_detail", "suburb"),
                city=                  m.get(prop, "property_detail", "city"),
                land_size_sqm=         m.get(prop, "property_detail", "land_size_sqm"),
                property_type=         m.get(prop, "property_detail", "property_type"),
                sectional_scheme_name= m.get(prop, "property_detail", "sectional_scheme_name"),
                sectional_unit_number= m.get(prop, "property_detail", "sectional_unit_number"),
                lpi_code=              m.get(prop, "property_detail", "lpi_code"),
            ),
            title_deed=TitleDeed(
                deed_number=       m.get(deed, "title_deed", "deed_number"),
                registration_date= m.get(deed, "title_deed", "registration_date"),
                deeds_office=      m.get(deed, "title_deed", "deeds_office"),
            ),
            current_owner=OwnerRecord(
                owner_name=       m.get(current_raw, "ownership", "owner_name"),
                owner_type=       m.get(current_raw, "ownership", "owner_type"),
                id_or_reg_number= m.get(current_raw, "ownership", "id_or_reg_number"),
                transfer_date=    m.get(current_raw, "ownership", "transfer_date"),
                purchase_price=   m.get(current_raw, "ownership", "purchase_price"),
            ),
            ownership_history=[
                OwnerRecord(
                    owner_name=     m.get(h, "ownership", "owner_name"),
                    owner_type=     m.get(h, "ownership", "owner_type"),
                    transfer_date=  m.get(h, "ownership", "transfer_date"),
                    purchase_price= m.get(h, "ownership", "purchase_price"),
                )
                for h in history_raw
            ],
            bonds=[
                BondRecord(
                    bond_number=       m.get(b, "bonds", "bond_number"),
                    registered_amount= m.get(b, "bonds", "registered_amount"),
                    bond_holder_bank=  m.get(b, "bonds", "bond_holder_bank"),
                    registration_date= m.get(b, "bonds", "registration_date"),
                    cancellation_date= m.get(b, "bonds", "cancellation_date"),
                    status="Cancelled" if m.get(b, "bonds", "cancellation_date") else "Active",
                )
                for b in bonds_raw
            ],
            interdicts= deed.get(m.section_key("title_deed", "interdicts"), []),
            servitudes=  deed.get(m.section_key("title_deed", "servitudes"), []),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
