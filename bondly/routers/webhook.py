import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
import aiosqlite

from bondly.database import get_db
from bondly.services import stripe_service, user_service

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("")
async def stripe_webhook(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("customer_email") or (session.get("metadata") or {}).get("email", "")

        if email:
            await user_service.activate_user(db, email)
            await db.execute(
                """
                UPDATE subscriptions SET status = 'active', activated_at = datetime('now')
                WHERE user_id = (SELECT id FROM users WHERE email = ?)
                  AND status = 'pending'
                """,
                (email,),
            )
            await db.commit()

    return {"status": "ok"}
