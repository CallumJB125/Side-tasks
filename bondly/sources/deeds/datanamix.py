"""
Datanamix Deed Search API adapter.
Auth: API key in header
Docs: https://www.datanamix.com/developer-hub/product-documentation

Field names come from bondly/sources/deeds/field_maps/datanamix.json.
Every mapping is marked UNVERIFIED until tested against real credentials.
Run `python -m bondly.sources.deeds.verify datanamix <erf_key>` after
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

_BASE = "https://api.datanamix.com"   # confirm exact base URL from their developer hub


class DatanamixClient(DeedsClient):

    def __init__(self, api_key: str):
        self._headers = {
            "X-API-Key": api_key,
            "Accept":    "application/json",
        }
        self._m = DeedsMapper("datanamix")

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = requests.get(f"{_BASE}{path}", headers=self._headers, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(f"{_BASE}{path}", headers=self._headers, json=body, timeout=20)
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
        data = self._post("/v1/deeds/search", {"searchType": "address", "query": address})
        return [self._to_result(r) for r in data.get(self._m.results_key("search"), [])]

    def search_by_erf(self, erf_number: str, township: str, deeds_office: str = "") -> list[dict]:
        body = {"searchType": "erf", "erfNumber": erf_number, "township": township}
        if deeds_office:
            body["deedsOffice"] = deeds_office
        data = self._post("/v1/deeds/search", body)
        return [self._to_result(r) for r in data.get(self._m.results_key("search"), [])]

    def search_by_owner(self, id_number: str) -> list[dict]:
        data = self._post("/v1/deeds/search", {"searchType": "owner", "idNumber": id_number})
        return [self._to_result(r) for r in data.get(self._m.results_key("search"), [])]

    # ── Full record ───────────────────────────────────────────────────────────

    def get_full_record(self, erf_key: str) -> DeedsData:
        raw = self._post("/v1/deeds/full", {"erfKey": erf_key})
        m   = self._m
        fr  = m._map["full_record"]   # section shortcut

        prop_raw  = raw.get(fr["property_key"],  {})
        deed_raw  = raw.get(fr["deed_key"],       {})
        own_raw   = raw.get(fr["ownership_key"],  {})
        bonds_raw = raw.get(fr["bonds_key"],      [])

        def _prop(field):  return m.get(prop_raw,  "full_record.property",  field)
        def _deed(field):  return m.get(deed_raw,  "full_record.title_deed", field)
        def _own(field):   return m.get(own_raw,   "full_record.ownership",  field)
        def _bond(b, field): return m.get(b,       "full_record.bond",       field)

        # Flatten nested section keys for the mapper
        prop_map  = fr["property"]
        deed_map  = fr["title_deed"]
        own_map   = fr["ownership"]
        bond_map  = fr["bond"]

        def resolve(data, mapping, field):
            candidates = mapping.get(field, [field])
            if isinstance(candidates, str):
                candidates = [candidates]
            for k in candidates:
                if k in data and data[k] is not None:
                    return data[k]
            return None

        history_raw = own_raw.get(own_map.get("history_key", "history"), [])

        return DeedsData(
            property=PropertyInfo(
                erf_number=            resolve(prop_raw, prop_map, "erf_number"),
                portion=               resolve(prop_raw, prop_map, "portion"),
                township=              resolve(prop_raw, prop_map, "township"),
                registration_division= resolve(prop_raw, prop_map, "registration_division"),
                province=              resolve(prop_raw, prop_map, "province"),
                street_address=        resolve(prop_raw, prop_map, "street_address"),
                suburb=                resolve(prop_raw, prop_map, "suburb"),
                city=                  resolve(prop_raw, prop_map, "city"),
                land_size_sqm=         resolve(prop_raw, prop_map, "land_size_sqm"),
                property_type=         resolve(prop_raw, prop_map, "property_type"),
                sectional_scheme_name= resolve(prop_raw, prop_map, "sectional_scheme_name"),
                sectional_unit_number= resolve(prop_raw, prop_map, "sectional_unit_number"),
                lpi_code=              resolve(prop_raw, prop_map, "lpi_code"),
            ),
            title_deed=TitleDeed(
                deed_number=       resolve(deed_raw, deed_map, "deed_number"),
                registration_date= resolve(deed_raw, deed_map, "registration_date"),
                deeds_office=      resolve(deed_raw, deed_map, "deeds_office"),
            ),
            current_owner=OwnerRecord(
                owner_name=       resolve(own_raw, own_map, "owner_name"),
                owner_type=       resolve(own_raw, own_map, "owner_type"),
                id_or_reg_number= resolve(own_raw, own_map, "id_or_reg_number"),
                transfer_date=    resolve(own_raw, own_map, "transfer_date"),
                purchase_price=   resolve(own_raw, own_map, "purchase_price"),
            ),
            ownership_history=[
                OwnerRecord(
                    owner_name=     resolve(h, own_map, "owner_name"),
                    owner_type=     resolve(h, own_map, "owner_type"),
                    transfer_date=  resolve(h, own_map, "transfer_date"),
                    purchase_price= resolve(h, own_map, "purchase_price"),
                )
                for h in history_raw
            ],
            bonds=[
                BondRecord(
                    bond_number=       resolve(b, bond_map, "bond_number"),
                    registered_amount= resolve(b, bond_map, "registered_amount"),
                    bond_holder_bank=  resolve(b, bond_map, "bond_holder_bank"),
                    registration_date= resolve(b, bond_map, "registration_date"),
                    cancellation_date= resolve(b, bond_map, "cancellation_date"),
                    status="Cancelled" if resolve(b, bond_map, "cancellation_date") else "Active",
                )
                for b in bonds_raw
            ],
            interdicts= raw.get(fr.get("interdicts_key", "interdicts"), []),
            servitudes=  raw.get(fr.get("servitudes_key", "servitudes"), []),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
