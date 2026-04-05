"""
Datanamix Deed Search API adapter.
Docs:  https://www.datanamix.com/developers-page/
Auth:  API key in header

To get credentials:
    Register at https://www.datanamix.com/
    Their pricing model charges only on successful results.

Base URL: https://api.datanamix.com  (confirm exact URL on their developer hub)
"""
from __future__ import annotations
from datetime import datetime, timezone

import requests

from bondly.models.property import (
    BondRecord, DeedsData, OwnerRecord, PropertyInfo, TitleDeed
)
from bondly.sources.deeds.base import DeedsClient


class DatanamixClient(DeedsClient):

    _BASE = "https://api.datanamix.com/v1"

    def __init__(self, api_key: str):
        self._headers = {
            "X-API-Key": api_key,
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = requests.get(
            f"{self._BASE}{path}",
            headers=self._headers,
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(
            f"{self._BASE}{path}",
            headers=self._headers,
            json=body,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Search methods ────────────────────────────────────────────────────────

    def search_by_address(self, address: str) -> list[dict]:
        data = self._post("/deeds/search", {"searchType": "address", "query": address})
        return [
            {
                "erf_key": r.get("erfKey") or r.get("titleDeedNumber"),
                "address": r.get("address"),
                "township": r.get("township"),
                "erf_number": r.get("erfNumber"),
                "lpi_code": r.get("lpiCode"),
            }
            for r in data.get("results", [])
        ]

    def search_by_erf(self, erf_number: str, township: str, deeds_office: str = "") -> list[dict]:
        body = {"searchType": "erf", "erfNumber": erf_number, "township": township}
        if deeds_office:
            body["deedsOffice"] = deeds_office
        data = self._post("/deeds/search", body)
        return [
            {
                "erf_key": r.get("erfKey") or r.get("titleDeedNumber"),
                "address": r.get("address"),
                "township": r.get("township"),
                "erf_number": r.get("erfNumber"),
                "lpi_code": r.get("lpiCode"),
            }
            for r in data.get("results", [])
        ]

    def search_by_owner(self, id_number: str) -> list[dict]:
        data = self._post("/deeds/search", {"searchType": "owner", "idNumber": id_number})
        return [
            {
                "erf_key": r.get("erfKey") or r.get("titleDeedNumber"),
                "address": r.get("address"),
                "township": r.get("township"),
                "erf_number": r.get("erfNumber"),
                "lpi_code": r.get("lpiCode"),
            }
            for r in data.get("results", [])
        ]

    # ── Full record ───────────────────────────────────────────────────────────

    def get_full_record(self, erf_key: str) -> DeedsData:
        data = self._post("/deeds/full", {"erfKey": erf_key})

        prop  = data.get("property", {})
        deed  = data.get("titleDeed", {})
        owner = data.get("ownership", {})
        bonds = data.get("bonds", [])

        return DeedsData(
            property=PropertyInfo(
                erf_number=prop.get("erfNumber"),
                portion=prop.get("portion"),
                township=prop.get("township"),
                registration_division=prop.get("registrationDivision"),
                province=prop.get("province"),
                street_address=prop.get("address"),
                suburb=prop.get("suburb"),
                city=prop.get("city"),
                land_size_sqm=prop.get("landSize") or prop.get("erfSize"),
                property_type=prop.get("propertyType"),
                sectional_scheme_name=prop.get("schemeName"),
                sectional_unit_number=prop.get("unitNumber"),
                lpi_code=prop.get("lpiCode"),
            ),
            title_deed=TitleDeed(
                deed_number=deed.get("deedNumber"),
                registration_date=deed.get("registrationDate"),
                deeds_office=deed.get("deedsOffice"),
            ),
            current_owner=OwnerRecord(
                owner_name=owner.get("name"),
                owner_type=owner.get("type"),
                id_or_reg_number=owner.get("idNumber"),
                transfer_date=owner.get("transferDate"),
                purchase_price=owner.get("purchasePrice"),
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
                for b in bonds
            ],
            interdicts=data.get("interdicts", []),
            servitudes=data.get("servitudes", []),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
