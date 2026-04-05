import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
import aiosqlite

from bondly.database import get_db
from bondly.middleware.auth import require_active_subscription
from bondly.models.property import PropertyReport
from bondly.services import property_service

router = APIRouter(prefix="/property", tags=["property"])


@router.get("/search")
async def search_property(
    q: str = Query(..., description="Address, or 'erf,township' for erf search"),
    type: str = Query("address", description="address | erf | owner"),
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Search the Deeds Registry for a property.

    Examples:
    - `?q=12+Sandton+Drive` (address)
    - `?q=12345,Sandton&type=erf` (erf number + township)
    - `?q=8501015009083&type=owner` (find all properties by SA ID number)

    Returns a list of matches with erf_key values.
    Use the erf_key in GET /property/report to get the full record.
    """
    try:
        results = property_service.search_properties(q, search_type=type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Deeds query failed: {exc}")

    await db.execute(
        "INSERT INTO search_log (user_id, query, result_found) VALUES (?, ?, ?)",
        (user["id"], f"[{type}] {q}", int(len(results) > 0)),
    )
    await db.commit()

    return {"results": results, "count": len(results)}


@router.get("/report", response_model=PropertyReport)
async def get_report(
    erf_key: str = Query(..., description="erf_key from /property/search"),
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Full deeds report for a property (no statement).

    Returns all available deeds data:
    - Property details (erf, title deed, address, size)
    - All bonds (active + cancelled)
    - Current owner + ownership history
    - Servitudes, interdicts
    """
    try:
        report = property_service.build_report(erf_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await db.execute(
        "INSERT INTO search_log (user_id, query, result_found) VALUES (?, ?, 1)",
        (user["id"], f"report:{erf_key}"),
    )
    await db.commit()

    return report


@router.post("/report/full", response_model=PropertyReport)
async def get_full_report(
    erf_key: str = Query(..., description="erf_key from /property/search"),
    statement: UploadFile = File(..., description="Home loan statement PDF"),
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Full report combining deeds data + bank statement.

    Upload your latest home loan statement PDF (any major SA bank).
    The statement is parsed locally — it is never stored after this request.

    Returns everything:
    - All deeds data (property, bonds, ownership, title deed)
    - Live loan data (outstanding balance, rate, repayment, arrears)
    """
    if not statement.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Write to a temp file, parse, then delete
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await statement.read())
        tmp_path = tmp.name

    try:
        report = property_service.build_report(erf_key, statement_path=tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        os.unlink(tmp_path)

    await db.execute(
        "INSERT INTO search_log (user_id, query, result_found) VALUES (?, ?, 1)",
        (user["id"], f"full_report:{erf_key}"),
    )
    await db.commit()

    return report


@router.post("/statement/parse")
async def parse_statement_only(
    statement: UploadFile = File(..., description="Home loan statement PDF"),
    user=Depends(require_active_subscription),
):
    """
    Parse a bank statement PDF and return the extracted loan data.
    Useful for testing or when you already have the deeds data.

    Statement is never stored after this request.
    """
    if not statement.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    from bondly.sources.statements.parser import parse_statement

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await statement.read())
        tmp_path = tmp.name

    try:
        result = parse_statement(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse statement: {exc}")
    finally:
        os.unlink(tmp_path)

    return result
