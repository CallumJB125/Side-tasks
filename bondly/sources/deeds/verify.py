"""
Field mapping verification script.

Run this after obtaining real API credentials to see the exact raw response
from the deeds provider, compare it to the current field map, and identify
what needs updating.

Usage:
    python -m bondly.sources.deeds.verify afrigis GP-JHB-ERF-12345
    python -m bondly.sources.deeds.verify datanamix <erf_key>
    python -m bondly.sources.deeds.verify afrigis --search "12 Sandton Drive"

Output:
    - Raw JSON from each endpoint
    - Side-by-side comparison with current field map
    - List of fields in the response with no mapping
    - List of mapped fields that weren't found in the response
    - Suggested corrections to paste into the field map JSON
"""
from __future__ import annotations

import argparse
import json
import sys
import os

# Allow running as `python -m bondly.sources.deeds.verify`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


def _flatten_keys(d: dict, prefix: str = "") -> list[str]:
    keys = []
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        keys.append(full)
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, full))
    return keys


def _resolve_candidate(data: dict, candidates: list[str]):
    for c in candidates:
        parts = c.split(".")
        val = data
        for p in parts:
            val = val.get(p) if isinstance(val, dict) else None
        if val is not None:
            return c, val
    return None, None


def verify_section(raw: dict, section_map: dict, section_name: str):
    print(f"\n{'='*60}")
    print(f"Section: {section_name}")
    print(f"{'='*60}")

    all_keys = _flatten_keys(raw)
    print(f"\nAll keys in raw response ({len(all_keys)}):")
    for k in all_keys:
        print(f"  {k}")

    print(f"\nField mapping check:")
    found_count = 0
    missing = []
    for field, candidates in section_map.items():
        if field.startswith("_"):
            continue
        if isinstance(candidates, str):
            candidates = [candidates]
        if not isinstance(candidates, list):
            continue
        matched_key, matched_val = _resolve_candidate(raw, candidates)
        if matched_val is not None:
            found_count += 1
            print(f"  ✓ {field:30} <- {matched_key!r:30} = {str(matched_val)[:40]!r}")
        else:
            missing.append(field)
            print(f"  ✗ {field:30}   tried: {candidates}")

    unmapped = [k for k in raw if not k.startswith("_") and k not in {
        c for candidates in section_map.values()
        if isinstance(candidates, list)
        for c in candidates
    }]

    if missing:
        print(f"\n⚠ {len(missing)} mapped fields NOT found in response: {missing}")
        print("  → Update the JSON candidates list with the actual key names above.")

    if unmapped:
        print(f"\n📦 {len(unmapped)} response fields with NO mapping yet:")
        for k in unmapped:
            v = raw.get(k)
            print(f"  {k!r:30} = {str(v)[:50]!r}")
        print("  → Consider adding these to the field map if they contain useful data.")

    print(f"\nConfidence: {found_count}/{len([k for k in section_map if not k.startswith('_') and isinstance(section_map[k], list)])} fields matched")


def run_afrigis(erf_key: str, search_query: str | None):
    from bondly.config import get_settings
    s = get_settings()

    if not s.afrigis_client_id or not s.afrigis_client_secret:
        print("ERROR: AFRIGIS_CLIENT_ID and AFRIGIS_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    from bondly.sources.deeds.afrigis import AfriGISClient
    from bondly.sources.deeds.mapper import DeedsMapper

    client = AfriGISClient(s.afrigis_client_id, s.afrigis_client_secret)
    mapper = DeedsMapper("afrigis")
    fmap   = mapper._map

    if search_query:
        print(f"\nFetching: /property/search?query={search_query!r}")
        raw = client._get("/property/search", {"query": search_query, "limit": 3})
        print("Raw response:"); print(json.dumps(raw, indent=2))
        return

    endpoints = {
        "property_detail": f"/property/{erf_key}",
        "title_deed":      f"/deeds/{erf_key}",
        "ownership":       f"/deeds/{erf_key}/ownership",
        "bonds":           f"/deeds/{erf_key}/bonds",
    }

    for section, path in endpoints.items():
        print(f"\nFetching: {path}")
        raw = client._get(path)
        print("Raw response:"); print(json.dumps(raw, indent=2))
        if section in fmap:
            verify_section(raw, fmap[section], section)


def run_datanamix(erf_key: str, search_query: str | None):
    from bondly.config import get_settings
    s = get_settings()

    if not s.datanamix_api_key:
        print("ERROR: DATANAMIX_API_KEY must be set in .env")
        sys.exit(1)

    from bondly.sources.deeds.datanamix import DatanamixClient
    from bondly.sources.deeds.mapper import DeedsMapper

    client = DatanamixClient(s.datanamix_api_key)
    mapper = DeedsMapper("datanamix")
    fmap   = mapper._map

    if search_query:
        print(f"\nFetching: /v1/deeds/search (address={search_query!r})")
        raw = client._post("/v1/deeds/search", {"searchType": "address", "query": search_query})
        print("Raw response:"); print(json.dumps(raw, indent=2))
        return

    print(f"\nFetching: /v1/deeds/full (erfKey={erf_key!r})")
    raw = client._post("/v1/deeds/full", {"erfKey": erf_key})
    print("Raw response:"); print(json.dumps(raw, indent=2))

    fr = fmap.get("full_record", {})
    for section_key in ["property", "title_deed", "ownership", "bond"]:
        top_key = fr.get(f"{section_key}_key", section_key)
        section_raw = raw.get(top_key, {})
        if section_raw and isinstance(section_raw, dict):
            verify_section(section_raw, fr.get(section_key, {}), section_key)


def main():
    parser = argparse.ArgumentParser(description="Verify deeds API field mappings")
    parser.add_argument("provider", choices=["afrigis", "datanamix"], help="API provider")
    parser.add_argument("erf_key", nargs="?", default="", help="erf_key to look up")
    parser.add_argument("--search", metavar="ADDRESS", help="Run address search instead")
    args = parser.parse_args()

    if not args.erf_key and not args.search:
        parser.error("Provide an erf_key or --search ADDRESS")

    if args.provider == "afrigis":
        run_afrigis(args.erf_key, args.search)
    else:
        run_datanamix(args.erf_key, args.search)


if __name__ == "__main__":
    main()
