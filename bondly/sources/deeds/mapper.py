"""
Config-driven field mapper for deeds API responses.

Each provider has a JSON field map under field_maps/<provider>.json.
The mapper tries each candidate key in order and returns the first hit,
so when the real API response arrives and differs from our guesses,
you only need to update the JSON — no Python changes required.

Usage:
    from bondly.sources.deeds.mapper import DeedsMapper
    m = DeedsMapper("afrigis")
    value = m.get(response_dict, "property_detail", "erf_number")
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAPS_DIR = Path(__file__).parent / "field_maps"


def _load_map(provider: str) -> dict:
    path = _MAPS_DIR / f"{provider}.json"
    if not path.exists():
        raise FileNotFoundError(f"No field map for provider '{provider}' at {path}")
    with open(path) as f:
        return json.load(f)


def _resolve(data: dict, candidates: list[str]) -> Any:
    """
    Try each candidate key (supports dot-notation for nested keys).
    Returns the first value found, or None.
    Logs a debug message showing which key matched.
    """
    for key in candidates:
        parts = key.split(".")
        val = data
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part)
            else:
                val = None
                break
        if val is not None:
            if key != candidates[0]:
                logger.debug(
                    "Field resolved via fallback key %r (primary %r was absent)",
                    key, candidates[0],
                )
            return val
    logger.warning(
        "No field matched for candidates %r in keys %s",
        candidates, list(data.keys())[:10],
    )
    return None


class DeedsMapper:
    """
    Wraps a provider's field map and exposes a .get() method that resolves
    field names from a raw API response dict.
    """

    def __init__(self, provider: str):
        self.provider = provider
        self._map = _load_map(provider)

    def get(self, data: dict, section: str, field: str) -> Any:
        """
        Resolve `field` from `data` using the candidate list in map[section][field].
        Raises KeyError if the section or field is not in the map.
        """
        section_map = self._map.get(section)
        if section_map is None:
            raise KeyError(f"Section '{section}' not in {self.provider} field map")
        candidates = section_map.get(field)
        if candidates is None:
            raise KeyError(f"Field '{field}' not in section '{section}' of {self.provider} map")
        if isinstance(candidates, str):
            candidates = [candidates]
        return _resolve(data, candidates)

    def section_key(self, section: str, key: str) -> str:
        """Return a simple string key (not a candidate list) from a section."""
        return self._map.get(section, {}).get(key, key)

    def results_key(self, section: str) -> str:
        return self.section_key(section, "results_key")

    def unmapped_fields(self, data: dict, section: str) -> list[str]:
        """
        Return fields present in `data` that have no mapping in the config.
        Useful for discovering new fields after getting real API access.
        """
        known = set(self._map.get(section, {}).keys())
        return [k for k in data if k not in known and not k.startswith("_")]
