import stripe
from bondly.config import get_settings

_settings = get_settings()
stripe.api_key = _settings.stripe_secret_key


def create_checkout_session(email: str) -> str:
    session = stripe.checkout.Session.create(
        customer_email=email,
        payment_method_types=["card"],
        line_items=[{"price": _settings.stripe_price_id, "quantity": 1}],
        mode="payment",
        success_url=f"{_settings.base_url}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{_settings.base_url}/subscribe/cancel",
        metadata={"email": email},
    )
    return session.url


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    return stripe.Webhook.construct_event(
        payload, sig_header, _settings.stripe_webhook_secret
    )
