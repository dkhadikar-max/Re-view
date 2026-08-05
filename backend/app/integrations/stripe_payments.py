from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class StripePayments:
    """Stripe Checkout Payment Links for upsells.

    Airport Pickup → Payment Link → Paid webhook → Notify hotel → Guest Memory
    """

    name = "stripe"

    def __init__(self) -> None:
        self.secret = settings.stripe_secret_key
        self.currency = settings.stripe_currency

    @property
    def configured(self) -> bool:
        return bool(self.secret)

    @property
    def mode(self) -> str:
        return "live" if self.configured else "mock"

    def create_payment_link(
        self,
        *,
        offer_name: str,
        amount_cents: int,
        guest_email: Optional[str],
        metadata: dict[str, str],
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> dict[str, Any]:
        success = success_url or f"{settings.frontend_base_url}/revenue?paid=1"
        cancel = cancel_url or f"{settings.frontend_base_url}/revenue?paid=0"

        if not self.configured:
            fake_id = f"plink_mock_{uuid.uuid4().hex[:10]}"
            url = f"{settings.frontend_base_url}/revenue?mock_pay={fake_id}"
            logger.info("Stripe MOCK payment link for %s → %s", offer_name, url)
            return {
                "id": fake_id,
                "url": url,
                "mode": "mock",
                "amount_cents": amount_cents,
                "currency": self.currency,
                "metadata": metadata,
            }

        import stripe

        stripe.api_key = self.secret
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success,
            cancel_url=cancel,
            customer_email=guest_email,
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": self.currency,
                        "unit_amount": amount_cents,
                        "product_data": {"name": offer_name},
                    },
                }
            ],
            metadata=metadata,
        )
        return {
            "id": session.id,
            "url": session.url,
            "mode": "live",
            "amount_cents": amount_cents,
            "currency": self.currency,
            "metadata": metadata,
        }

    def construct_event(self, payload: bytes, sig_header: str):
        import stripe

        return stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )


stripe_payments = StripePayments()
