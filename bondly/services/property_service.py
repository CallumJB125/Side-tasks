"""
Orchestrates deeds + statement data into a unified PropertyReport.
"""
from datetime import datetime, timezone
from pathlib import Path

from bondly.models.property import PropertyReport
from bondly.sources.deeds.base import DeedsClient
from bondly.sources.statements.parser import parse_statement
from bondly.config import get_settings

_settings = get_settings()


def get_deeds_client() -> DeedsClient:
    provider = getattr(_settings, "deeds_provider", "mock")

    if provider == "afrigis":
        from bondly.sources.deeds.afrigis import AfriGISClient
        return AfriGISClient(
            client_id=_settings.afrigis_client_id,
            client_secret=_settings.afrigis_client_secret,
        )
    if provider == "datanamix":
        from bondly.sources.deeds.datanamix import DatanamixClient
        return DatanamixClient(api_key=_settings.datanamix_api_key)

    from bondly.sources.deeds.mock import MockDeedsClient
    return MockDeedsClient()


def search_properties(query: str, search_type: str = "address") -> list[dict]:
    client = get_deeds_client()
    if search_type == "erf":
        parts = query.split(",", 1)
        erf = parts[0].strip()
        township = parts[1].strip() if len(parts) > 1 else ""
        return client.search_by_erf(erf, township)
    if search_type == "owner":
        return client.search_by_owner(query)
    return client.search_by_address(query)


def build_report(
    erf_key: str,
    statement_path: str | Path | None = None,
) -> PropertyReport:
    client = get_deeds_client()

    deeds = None
    statement = None
    completeness = {}

    try:
        deeds = client.get_full_record(erf_key)
        completeness["deeds"] = "ok"
    except Exception as e:
        completeness["deeds"] = f"error: {e}"

    if statement_path:
        try:
            statement = parse_statement(statement_path)
            completeness["statement"] = "ok"
        except Exception as e:
            completeness["statement"] = f"error: {e}"
    else:
        completeness["statement"] = "not provided"

    return PropertyReport(
        deeds=deeds,
        statement=statement,
        generated_at=datetime.now(timezone.utc).isoformat(),
        completeness=completeness,
    )
