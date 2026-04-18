"""
Customer financial profiling endpoints.

Flow:
  1. POST /profile/analyse  — upload a current/cheque account statement PDF
                              → returns full profile + affordability analysis
  2. GET  /profile/affordability — recalculate affordability from the latest profile
  3. POST /profile/compare  — compare the two most recent profiles for behaviour changes
  4. GET  /profile/history  — list all stored profiles for the authenticated user
"""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from bondly.database import get_db
from bondly.middleware.auth import require_active_subscription
from bondly.models.profile import CustomerProfile, ExpenseBreakdown, Transaction
from bondly.services.affordability import calculate_affordability
from bondly.services.behaviour_tracker import detect_changes
from bondly.sources.statements.transactional_parser import parse_transactional_statement

router = APIRouter(prefix="/profile", tags=["profile"])


# ---------------------------------------------------------------------------
# DB helpers — use the injected connection (consistent with other routers)
# ---------------------------------------------------------------------------

async def _save_profile(db: aiosqlite.Connection, profile: CustomerProfile) -> int:
    cursor = await db.execute(
        """
        INSERT INTO financial_profiles
            (user_id, period, statement_period, gross_income, net_income,
             total_expenses, net_cash_flow, expense_breakdown, transactions,
             bank_detected, parse_confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile.user_id,
            profile.period,
            profile.statement_period,
            profile.gross_monthly_income,
            profile.net_monthly_income,
            profile.expense_breakdown.total_expenses,
            profile.expense_breakdown.net_cash_flow,
            json.dumps(profile.expense_breakdown.by_category),
            json.dumps([t.model_dump() for t in profile.transactions]),
            profile.bank_detected,
            profile.parse_confidence,
            profile.created_at,
        ),
    )
    await db.commit()
    return cursor.lastrowid


def _row_to_profile(row: aiosqlite.Row) -> CustomerProfile:
    by_cat = json.loads(row["expense_breakdown"] or "{}")
    raw_txns = json.loads(row["transactions"] or "[]")

    breakdown = ExpenseBreakdown(
        total_income=row["gross_income"] or 0.0,
        total_expenses=row["total_expenses"] or 0.0,
        net_cash_flow=row["net_cash_flow"] or 0.0,
        by_category=by_cat,
    )
    transactions = []
    for t in raw_txns:
        try:
            transactions.append(Transaction(**t))
        except Exception:
            pass

    return CustomerProfile(
        user_id=row["user_id"],
        period=row["period"],
        statement_period=row["statement_period"],
        gross_monthly_income=row["gross_income"] or 0.0,
        net_monthly_income=row["net_income"] or 0.0,
        expense_breakdown=breakdown,
        transactions=transactions,
        bank_detected=row["bank_detected"],
        parse_confidence=row["parse_confidence"] or 0.0,
        created_at=row["created_at"],
    )


async def _latest_profiles(
    db: aiosqlite.Connection, user_id: int, limit: int = 2
) -> list[CustomerProfile]:
    rows = await db.execute_fetchall(
        """SELECT * FROM financial_profiles
           WHERE user_id = ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (user_id, limit),
    )
    return [_row_to_profile(r) for r in rows]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/analyse")
async def analyse_statement(
    file: UploadFile = File(..., description="Current/cheque account bank statement PDF"),
    current_bond_amount: float | None = Query(
        None, description="Your outstanding bond balance in ZAR (optional, improves affordability gap calc)"
    ),
    interest_rate: float = Query(11.75, description="Annual interest rate % (defaults to current SA prime)"),
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Upload a current/cheque account statement PDF.

    The API will:
    - Detect your bank
    - Extract and categorise every transaction (groceries, fuel, alcohol, gambling, subscriptions…)
    - Calculate your gross income from salary credits
    - Run a full NCA-aligned affordability analysis
    - Show which spending categories are hurting your bond capacity
    - Store the profile for month-on-month comparison via POST /profile/compare

    The PDF is processed in memory and never stored on disk after this request.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        profile = parse_transactional_statement(tmp_path, user_id=user["id"])
    except Exception as exc:
        raise HTTPException(422, f"Could not parse statement: {exc}")
    finally:
        os.unlink(tmp_path)

    profile.affordability = calculate_affordability(
        profile.expense_breakdown,
        current_bond_amount=current_bond_amount,
        annual_interest_rate=interest_rate,
    )

    profile_id = await _save_profile(db, profile)

    return {
        "profile_id": profile_id,
        "period": profile.period,
        "statement_period": profile.statement_period,
        "bank_detected": profile.bank_detected,
        "parse_confidence": profile.parse_confidence,
        "transaction_count": len(profile.transactions),
        "income": {
            "gross_monthly": profile.gross_monthly_income,
            "net_monthly": profile.net_monthly_income,
            "sources": profile.income_sources,
        },
        "expense_breakdown": profile.expense_breakdown.model_dump(
            exclude={"transactions", "salary_credits"}
        ),
        "affordability": profile.affordability.model_dump(),
    }


@router.get("/affordability")
async def get_affordability(
    current_bond_amount: float | None = Query(None),
    interest_rate: float = Query(11.75),
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Re-run the affordability calculation against your most recent profile.

    Useful for modelling 'what if' scenarios — e.g. try a lower interest rate
    or input your remaining bond balance to see your affordability gap.
    """
    profiles = await _latest_profiles(db, user["id"], limit=1)
    if not profiles:
        raise HTTPException(
            404,
            "No financial profile found. Upload a current account statement first via POST /profile/analyse.",
        )

    result = calculate_affordability(
        profiles[0].expense_breakdown,
        current_bond_amount=current_bond_amount,
        annual_interest_rate=interest_rate,
    )
    return result.model_dump()


@router.post("/compare")
async def compare_periods(
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Compare your two most recent monthly profiles to detect behaviour changes.

    Upload statements for two different months via POST /profile/analyse first.
    Returns a ranked list of changes — alerts (gambling, income drop) first,
    then warnings, then positive trends (savings up, education spend increasing).
    """
    profiles = await _latest_profiles(db, user["id"], limit=2)
    if len(profiles) < 2:
        raise HTTPException(
            400,
            f"Need at least 2 profiles to compare — you have {len(profiles)}. "
            "Upload statements for two different months via POST /profile/analyse.",
        )

    current, previous = profiles[0], profiles[1]
    changes = detect_changes(previous, current)

    alerts = [c for c in changes if c.severity == "alert"]
    warnings = [c for c in changes if c.severity == "warning"]
    positives = [c for c in changes if c.severity == "info"]

    return {
        "comparing": {
            "from_period": previous.period,
            "to_period": current.period,
        },
        "summary": {
            "total_changes_detected": len(changes),
            "alerts": len(alerts),
            "warnings": len(warnings),
            "positive_trends": len(positives),
        },
        "income": {
            "previous_month": previous.gross_monthly_income,
            "current_month": current.gross_monthly_income,
            "change_pct": round(
                (current.gross_monthly_income - previous.gross_monthly_income)
                / max(previous.gross_monthly_income, 1)
                * 100,
                1,
            ),
        },
        "total_spend": {
            "previous_month": previous.expense_breakdown.total_expenses,
            "current_month": current.expense_breakdown.total_expenses,
        },
        "changes": [c.model_dump() for c in changes],
    }


@router.get("/history")
async def get_history(
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    List all financial profiles stored for your account, newest first.
    Each entry shows the period, income, total expenses, and net cash flow.
    """
    rows = await db.execute_fetchall(
        """SELECT id, period, statement_period, gross_income, total_expenses,
                  net_cash_flow, bank_detected, parse_confidence, created_at
           FROM financial_profiles
           WHERE user_id = ?
           ORDER BY created_at DESC""",
        (user["id"],),
    )
    return [dict(r) for r in rows]
