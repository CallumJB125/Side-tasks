"""
Mock deeds client for development and testing.
Returns realistic South African property data without hitting any external API.
"""
from datetime import datetime, timezone

from bondly.models.property import (
    BondRecord, DeedsData, OwnerRecord, PropertyInfo, TitleDeed
)
from bondly.sources.deeds.base import DeedsClient

_MOCK_DB = {
    "GP-JHB-ERF-12345": {
        "property": PropertyInfo(
            erf_number="12345",
            portion="0",
            township="Sandton",
            registration_division="I.R.",
            province="Gauteng",
            street_address="12 Sandton Drive, Sandton, Johannesburg, 2196",
            suburb="Sandton",
            city="Johannesburg",
            land_size_sqm=650.0,
            property_type="Residential",
            lpi_code="GP-JHB-ERF-12345",
        ),
        "title_deed": TitleDeed(
            deed_number="T45678/2019",
            registration_date="2019-06-15",
            deeds_office="Johannesburg",
        ),
        "current_owner": OwnerRecord(
            owner_name="JOHN MICHAEL SMITH",
            owner_type="Individual",
            id_or_reg_number="850101****083",
            transfer_date="2019-06-15",
            purchase_price="R 2 300 000",
        ),
        "ownership_history": [
            OwnerRecord(
                owner_name="PETER JAMES WILLIAMS",
                owner_type="Individual",
                transfer_date="2014-03-10",
                purchase_price="R 1 750 000",
            ),
            OwnerRecord(
                owner_name="SANDTON DEVELOPMENTS (PTY) LTD",
                owner_type="Company",
                transfer_date="2011-07-22",
                purchase_price="R 950 000",
            ),
        ],
        "bonds": [
            BondRecord(
                bond_number="B123456/2019",
                registered_amount="R 1 850 000",
                bond_holder_bank="Standard Bank of South Africa Limited",
                registration_date="2019-06-15",
                status="Active",
            ),
        ],
        "interdicts": [],
        "servitudes": ["Right of way servitude in favour of erf 12344"],
    },
    "WC-CPT-ERF-78901": {
        "property": PropertyInfo(
            erf_number="78901",
            portion="0",
            township="Gardens",
            registration_division="Cape Division",
            province="Western Cape",
            street_address="7 Kloof Street, Gardens, Cape Town, 8001",
            suburb="Gardens",
            city="Cape Town",
            land_size_sqm=420.0,
            property_type="Residential",
            lpi_code="WC-CPT-ERF-78901",
        ),
        "title_deed": TitleDeed(
            deed_number="T11234/2021",
            registration_date="2021-03-22",
            deeds_office="Cape Town",
        ),
        "current_owner": OwnerRecord(
            owner_name="PETRUS VAN DER MERWE",
            owner_type="Individual",
            id_or_reg_number="790515****082",
            transfer_date="2021-03-22",
            purchase_price="R 4 100 000",
        ),
        "ownership_history": [
            OwnerRecord(
                owner_name="GARDENS PROPERTY TRUST",
                owner_type="Trust",
                transfer_date="2015-09-14",
                purchase_price="R 2 800 000",
            ),
        ],
        "bonds": [
            BondRecord(
                bond_number="B987654/2021",
                registered_amount="R 3 200 000",
                bond_holder_bank="FirstRand Bank Limited (FNB)",
                registration_date="2021-03-22",
                status="Active",
            ),
            BondRecord(
                bond_number="B654321/2015",
                registered_amount="R 2 100 000",
                bond_holder_bank="Nedbank Limited",
                registration_date="2015-09-14",
                cancellation_date="2021-03-22",
                status="Cancelled",
            ),
        ],
        "interdicts": [],
        "servitudes": [],
    },
}

_ADDRESS_INDEX = {
    "sandton": "GP-JHB-ERF-12345",
    "sandton drive": "GP-JHB-ERF-12345",
    "johannesburg": "GP-JHB-ERF-12345",
    "kloof": "WC-CPT-ERF-78901",
    "gardens": "WC-CPT-ERF-78901",
    "cape town": "WC-CPT-ERF-78901",
}


class MockDeedsClient(DeedsClient):

    def _find_keys(self, query: str) -> list[str]:
        q = query.lower()
        matches = list({v for k, v in _ADDRESS_INDEX.items() if k in q})
        return matches or list(_MOCK_DB.keys())[:1]

    def _to_result(self, key: str) -> dict:
        rec = _MOCK_DB[key]
        return {
            "erf_key": key,
            "address": rec["property"].street_address,
            "township": rec["property"].township,
            "erf_number": rec["property"].erf_number,
            "lpi_code": rec["property"].lpi_code,
        }

    def search_by_address(self, address: str) -> list[dict]:
        return [self._to_result(k) for k in self._find_keys(address)]

    def search_by_erf(self, erf_number: str, township: str, deeds_office: str = "") -> list[dict]:
        return [self._to_result(k) for k in self._find_keys(f"{township} {erf_number}")]

    def search_by_owner(self, id_number: str) -> list[dict]:
        # In mock, just return all
        return [self._to_result(k) for k in _MOCK_DB]

    def get_full_record(self, erf_key: str) -> DeedsData:
        rec = _MOCK_DB.get(erf_key, _MOCK_DB["GP-JHB-ERF-12345"])
        return DeedsData(
            property=rec["property"],
            title_deed=rec["title_deed"],
            current_owner=rec["current_owner"],
            ownership_history=rec["ownership_history"],
            bonds=rec["bonds"],
            interdicts=rec["interdicts"],
            servitudes=rec["servitudes"],
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
