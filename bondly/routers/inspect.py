"""
Raw API response inspector — only available when DEEDS_PROVIDER != 'mock'.

Use this after obtaining real credentials to see exactly what the API
returns, then update the field map JSON accordingly.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite

from bondly.config import get_settings
from bondly.database import get_db
from bondly.middleware.auth import require_active_subscription

router = APIRouter(prefix="/inspect", tags=["inspect"])
_settings = get_settings()


def _require_real_provider():
    if _settings.deeds_provider == "mock":
        raise HTTPException(
            status_code=403,
            detail=(
                "Inspector only available when DEEDS_PROVIDER is 'afrigis' or 'datanamix'. "
                "Set real credentials in .env first."
            ),
        )


@router.get("/deeds/raw")
async def raw_deeds_response(
    erf_key: str = Query(..., description="erf_key to fetch raw response for"),
    endpoint: str = Query(
        "property",
        description="Which endpoint to hit: property | deed | ownership | bonds | search",
    ),
    user=Depends(require_active_subscription),
):
    """
    Fetch a raw (unmapped) API response from the configured deeds provider.

    Use this to discover the real field names after getting API credentials,
    then update bondly/sources/deeds/field_maps/<provider>.json accordingly.

    Also shows which fields in the response have no mapping yet.
    """
    _require_real_provider()

    from bondly.services.property_service import get_deeds_client
    from bondly.sources.deeds.mapper import DeedsMapper

    client = get_deeds_client()
    mapper = DeedsMapper(_settings.deeds_provider)

    # Hit the right endpoint
    try:
        if hasattr(client, "_get"):
            paths = {
                "property":  f"/property/{erf_key}",
                "deed":      f"/deeds/{erf_key}",
                "ownership": f"/deeds/{erf_key}/ownership",
                "bonds":     f"/deeds/{erf_key}/bonds",
                "search":    "/property/search",
            }
            if endpoint not in paths:
                raise HTTPException(status_code=400, detail=f"Unknown endpoint '{endpoint}'")
            params = {"query": erf_key, "limit": 3} if endpoint == "search" else None
            raw = client._get(paths[endpoint], params)
        else:
            raise HTTPException(status_code=501, detail="Client does not support raw inspection")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"API error: {exc}")

    # Show unmapped fields
    section_map = {
        "property":  "property_detail",
        "deed":      "title_deed",
        "ownership": "ownership",
        "bonds":     "bonds",
        "search":    "search",
    }
    unmapped = mapper.unmapped_fields(raw, section_map.get(endpoint, endpoint))

    return {
        "provider":        _settings.deeds_provider,
        "erf_key":         erf_key,
        "endpoint":        endpoint,
        "raw_response":    raw,
        "unmapped_fields": unmapped,
        "field_map_path":  f"bondly/sources/deeds/field_maps/{_settings.deeds_provider}.json",
        "next_step": (
            "Compare 'raw_response' keys against 'field_map_path' and update "
            "the JSON to match the real field names."
        ),
    }


@router.get("/deeds/field-map")
async def show_field_map(
    user=Depends(require_active_subscription),
):
    """Return the current field map for the active deeds provider."""
    from bondly.sources.deeds.mapper import DeedsMapper
    mapper = DeedsMapper(_settings.deeds_provider)
    return {
        "provider":  _settings.deeds_provider,
        "field_map": mapper._map,
    }
