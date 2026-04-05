from fastapi import APIRouter, Depends, HTTPException
import aiosqlite

from bondly.database import get_db
from bondly.middleware.auth import get_current_user
from bondly.services import stripe_service

router = APIRouter(prefix="/subscribe", tags=["subscription"])


@router.post("")
async def create_subscription(
    user=Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Create a Stripe Checkout session for the authenticated user.
    Returns a payment URL — redirect the user there to complete payment.
    """
    if user["active"]:
        return {"message": "Your account is already active.", "active": True}

    try:
        checkout_url = stripe_service.create_checkout_session(user["email"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}")

    # Record pending subscription
    await db.execute(
        "INSERT INTO subscriptions (user_id, status) VALUES (?, 'pending')",
        (user["id"],),
    )
    await db.commit()

    return {
        "checkout_url": checkout_url,
        "message": "Complete payment to activate your account.",
    }


@router.get("/success")
def subscribe_success():
    return {
        "message": "Payment successful! Your account is now active.",
        "next_step": "Use POST /auth/login to get your token, then search for your bond at /mortgage/search.",
    }


@router.get("/cancel")
def subscribe_cancel():
    return {"message": "Payment cancelled. No charge was made."}
