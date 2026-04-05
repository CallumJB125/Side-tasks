"""
AfriGIS Property Search & Ownership API adapter.
Docs: https://developers.afrigis.co.za/oas3/property-search-api/
Auth: OAuth2 client_credentials

To get credentials:
    Contact AfriGIS at https://developers.afrigis.co.za/
    Request a trial account — free trial available.
    You'll receive a client_id and client_secret.

Base URLs:
    Auth:     https://identity.afrigis.co.za/connect/token
    Property: https://xdv.afrigis.co.za/rest/api/v3/property/
    Deeds:    https://xdv.afrigis.co.za/rest/api/v3/deeds/
"""
from __future__ import annotations
from datetime import datetime, timezone

import requests

from bondly.models.property import (
    BondRecord, DeedsData, OwnerRecord, PropertyInfo, TitleDeed
)
from bondly.sources.deeds.base import DeedsClient


class AfriGISClient(DeedsClient):

    _TOKEN_URL = "https://identity.afrigis.co.za/connect/token"
    _BASE = "https://xdv.afrigis.co.za/rest/api/v3"

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None

    def _get_token(self) -> str:
        resp = requests.post(
            self._TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "afrigis.agi",
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
        resp = requests.get(
            f"{self._BASE}{path}",
            headers=self._headers(),
            params=params,
            timeout=20,
        )
        if resp.status_code == 401:
            # Token expired — refresh once
            self._get_token()
            resp = requests.get(
                f"{self._BASE}{path}",
                headers=self._headers(),
                params=params,
                timeout=20,
            )
        resp.raise_for_status()
        return resp.json()

    # ── Search methods ────────────────────────────────────────────���─────────

    def search_by_address(self, address: str) -> list[dict]:
        data = self._get("/property/search", {"query": address, "limit": 10})
        return [
            {
                "erf_key": r.get("lpiCode") or r.get("id"),
                "address": r.get("addressDetails", {}).get("fullAddress"),
                "township": r.get("township"),
                "erf_number": r.get("erfNumber"),
                "lpi_code": r.get("lpiCode"),
            }
            for r in data.get("results", [])
        ]

    def search_by_erf(self, erf_number: str, township: str, deeds_office: str = "") -> list[dict]:
        params = {"erfNumber": erf_number, "township": township}
        if deeds_office:
            params["deedsOffice"] = deeds_office
        data = self._get("/property/erf", params)
        return [
            {
                "erf_key": r.get("lpiCode"),
                "address": r.get("addressDetails", {}).get("fullAddress"),
                "township": r.get("township"),
                "erf_number": r.get("erfNumber"),
                "lpi_code": r.get("lpiCode"),
            }
            for r in data.get("results", [])
        ]

    def search_by_owner(self, id_number: str) -> list[dict]:
        data = self._get("/deeds/owner", {"idNumber": id_number})
        return [
            {
                "erf_key": r.get("lpiCode"),
                "address": r.get("addressDetails", {}).get("fullAddress"),
                "township": r.get("township"),
                "erf_number": r.get("erfNumber"),
                "lpi_code": r.get("lpiCode"),
            }
            for r in data.get("results", [])
        ]

    # ── Full record ─────────────────────────────────────────────────────────

    def get_full_record(self, erf_key: str) -> DeedsData:
        prop  = self._get(f"/property/{erf_key}")
        deeds = self._get(f"/deeds/{erf_key}")
        owner = self._get(f"/deeds/{erf_key}/ownership")
        bonds = self._get(f"/deeds/{erf_key}/bonds")

        return DeedsData(
            property=PropertyInfo(
                erf_number=prop.get("erfNumber"),
                portion=prop.get("portion"),
                township=prop.get("township"),
                registration_division=prop.get("registrationDivision"),
                province=prop.get("province"),
                street_address=prop.get("addressDetails", {}).get("fullAddress"),
                suburb=prop.get("addressDetails", {}).get("suburb"),
                city=prop.get("addressDetails", {}).get("city"),
                land_size_sqm=prop.get("extent"),
                property_type=prop.get("propertyType"),
                sectional_scheme_name=prop.get("schemeName"),
                sectional_unit_number=prop.get("unitNumber"),
                lpi_code=prop.get("lpiCode"),
            ),
            title_deed=TitleDeed(
                deed_number=deeds.get("titleDeedNumber"),
                registration_date=deeds.get("registrationDate"),
                deeds_office=deeds.get("deedsOffice"),
            ),
            current_owner=OwnerRecord(
                owner_name=owner.get("currentOwner", {}).get("name"),
                owner_type=owner.get("currentOwner", {}).get("type"),
                id_or_reg_number=owner.get("currentOwner", {}).get("idNumber"),
                transfer_date=owner.get("currentOwner", {}).get("transferDate"),
                purchase_price=owner.get("currentOwner", {}).get("purchasePrice"),
            ),
            ownership_history=[
                OwnerRecord(
                    owner_name=h.get("name"),
                    owner_type=h.get("type"),
                    transfer_date=h.get("transferDate"),
                    purchase_price=h.get("purchasePrice"),
                )
                for h in owner.get("history", [])
            ],
            bonds=[
                BondRecord(
                    bond_number=b.get("bondNumber"),
                    registered_amount=b.get("amount"),
                    bond_holder_bank=b.get("bondHolder"),
                    registration_date=b.get("registrationDate"),
                    cancellation_date=b.get("cancellationDate"),
                    status="Cancelled" if b.get("cancellationDate") else "Active",
                )
                for b in bonds.get("bonds", [])
            ],
            interdicts=deeds.get("interdicts", []),
            servitudes=deeds.get("servitudes", []),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
