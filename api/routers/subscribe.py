from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from api.config import get_settings
from api.services import stripe_service

router = APIRouter(prefix="/subscribe", tags=["subscription"])

_settings = get_settings()

TIER_PRICE_MAP = {
    "basic": lambda s: s.stripe_price_id_basic,
    "pro": lambda s: s.stripe_price_id_pro,
}

TIER_INFO = {
    "basic": {"price_zar": 99, "requests_per_day": 500, "description": "500 API calls/day"},
    "pro":   {"price_zar": 299, "requests_per_day": 5000, "description": "5 000 API calls/day"},
}


class SubscribeRequest(BaseModel):
    email: EmailStr
    tier: str = "basic"


@router.get("/plans")
def list_plans():
    """Return available subscription tiers and pricing."""
    return {
        "plans": [
            {"tier": tier, **info}
            for tier, info in TIER_INFO.items()
        ]
    }


@router.post("")
def create_subscription(body: SubscribeRequest):
    """Create a Stripe Checkout session and return the payment URL."""
    tier = body.tier.lower()
    if tier not in TIER_PRICE_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown tier '{tier}'. Choose: basic, pro")

    price_id = TIER_PRICE_MAP[tier](_settings)
    try:
        checkout_url = stripe_service.create_checkout_session(body.email, price_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}")

    return {
        "checkout_url": checkout_url,
        "tier": tier,
        "message": "Complete payment to receive your API key via email confirmation.",
    }


@router.get("/success")
def subscribe_success(session_id: str):
    return {
        "message": "Payment successful! Your API key has been issued.",
        "next_step": "Check your email for your API key, then use it in the X-API-Key header.",
        "docs_url": "/docs",
    }


@router.get("/cancel")
def subscribe_cancel():
    return {"message": "Payment cancelled. No charge was made."}
