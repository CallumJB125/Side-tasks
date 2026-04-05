"""
Orchestrates deeds + statement data into a unified PropertyReport.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path

from bondly.models.property import PropertyReport, ValidationFlag
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
        return client.search_by_erf(parts[0].strip(), parts[1].strip() if len(parts) > 1 else "")
    if search_type == "owner":
        return client.search_by_owner(query)
    return client.search_by_address(query)


def _cross_validate(report: PropertyReport) -> list[ValidationFlag]:
    """
    Compare deeds and statement data and flag any inconsistencies.
    """
    flags: list[ValidationFlag] = []
    deeds = report.deeds
    stmt = report.statement

    if not deeds or not stmt:
        return flags

    active_bonds = [b for b in deeds.bonds if b.status == "Active"]

    # 1. Bank mismatch: statement bank vs deeds bond holder
    if active_bonds and stmt.bank:
        deed_bank = active_bonds[0].bond_holder_bank or ""
        stmt_bank = stmt.bank or ""
        # Normalise to key words for fuzzy comparison
        deed_words = set(re.findall(r"[a-z]+", deed_bank.lower()))
        stmt_words = set(re.findall(r"[a-z]+", stmt_bank.lower()))
        common = {"bank", "limited", "ltd", "south", "africa", "of", "the"}
        deed_key = deed_words - common
        stmt_key = stmt_words - common
        if deed_key and stmt_key and deed_key.isdisjoint(stmt_key):
            flags.append(ValidationFlag(
                field="bond_holder_bank",
                severity="warning",
                message=(
                    f"Statement is from '{stmt.bank}' but the active bond in the "
                    f"Deeds Registry is held by '{deed_bank}'. "
                    "Ensure you uploaded the correct bank's statement."
                ),
            ))

    # 2. No active bond in deeds
    if deeds.bonds and not active_bonds:
        flags.append(ValidationFlag(
            field="bonds",
            severity="warning",
            message="All bonds in the Deeds Registry are marked Cancelled. "
                    "If you still have a home loan, the cancellation may not yet be registered.",
        ))

    # 3. No bonds at all
    if not deeds.bonds:
        flags.append(ValidationFlag(
            field="bonds",
            severity="warning",
            message="No bonds found in the Deeds Registry for this property. "
                    "The property may be unencumbered (bond-free).",
        ))

    # 4. Interdicts on the title
    if deeds.interdicts:
        flags.append(ValidationFlag(
            field="interdicts",
            severity="error",
            message=f"Property has {len(deeds.interdicts)} interdict(s) registered: "
                    + "; ".join(deeds.interdicts),
        ))

    # 5. Low parse confidence on statement
    if stmt.parse_confidence is not None and stmt.parse_confidence < 0.6:
        flags.append(ValidationFlag(
            field="statement",
            severity="warning",
            message=(
                f"Statement parsed with low confidence ({stmt.parse_confidence:.0%}). "
                f"Missing fields: {', '.join(stmt.missing_fields)}. "
                "The PDF layout may not match expected format for this bank."
            ),
        ))

    # 6. Arrears detected
    if stmt.arrears_amount:
        arrears_clean = re.sub(r"[R\s,]", "", stmt.arrears_amount)
        try:
            if float(arrears_clean) > 0:
                flags.append(ValidationFlag(
                    field="arrears_amount",
                    severity="error",
                    message=f"Account is in arrears: {stmt.arrears_amount}. "
                            "Immediate attention required to avoid legal action.",
                ))
        except ValueError:
            pass

    return flags


def build_report(
    erf_key: str,
    statement_path: str | Path | None = None,
) -> PropertyReport:
    client = get_deeds_client()
    deeds = None
    statement = None
    completeness: dict = {}

    try:
        deeds = client.get_full_record(erf_key)
        completeness["deeds"] = "ok"
    except Exception as e:
        completeness["deeds"] = f"error: {e}"

    if statement_path:
        try:
            statement = parse_statement(statement_path)
            completeness["statement"] = f"ok (confidence: {statement.parse_confidence:.0%})"
        except Exception as e:
            completeness["statement"] = f"error: {e}"
    else:
        completeness["statement"] = "not provided"

    report = PropertyReport(
        deeds=deeds,
        statement=statement,
        generated_at=datetime.now(timezone.utc).isoformat(),
        completeness=completeness,
    )
    report.validation_flags = _cross_validate(report)
    return report
