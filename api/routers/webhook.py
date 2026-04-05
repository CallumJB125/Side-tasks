import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
import aiosqlite

from api.database import get_db
from api.services import key_service, stripe_service

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("")
async def stripe_webhook(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("customer_email") or session.get("metadata", {}).get("email", "")
        price_id = (session.get("metadata") or {}).get("price_id", "")

        if not email:
            # Fallback: look up the line items
            return {"status": "ignored", "reason": "no email found"}

        tier = stripe_service.price_id_to_tier(price_id)
        raw_key = await key_service.provision_key(db, email, tier)

        # In production you'd email the key here.
        # For now it's returned in the webhook response (visible in Stripe dashboard logs).
        return {
            "status": "key_provisioned",
            "email": email,
            "tier": tier,
            "api_key": raw_key,   # remove this in production; send via email instead
        }

    if event["type"] in ("customer.subscription.deleted", "invoice.payment_failed"):
        customer_email = (
            event.get("data", {}).get("object", {}).get("customer_email", "")
        )
        if customer_email:
            await key_service.deactivate_keys_for_email(db, customer_email)
        return {"status": "key_deactivated"}

    return {"status": "ignored"}
