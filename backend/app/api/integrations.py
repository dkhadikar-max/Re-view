from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import AuthUser, ManagerUser, StaffUser
from app.db.session import get_db
from app.integrations.cloudbeds import cloudbeds_client
from app.integrations.email_providers import get_email_client
from app.integrations.google_reviews import google_reviews_client
from app.integrations.openai_gateway import ai_gateway
from app.integrations.ownership import SERVICE_OWNERSHIP, ServiceOwnership
from app.integrations.queue import get_queue
from app.integrations.stripe_payments import stripe_payments
from app.integrations.whatsapp import whatsapp_client
from app.models.entities import Guest, Offer, OfferStatus, Reservation
from app.services.analytics import SalesAnalytics, build_sales_analytics
from app.services.audit import write_audit
from app.services.messaging import apply_provider_status, ingest_inbound_whatsapp
from app.services.pms_sync import cloudbeds_check_in, cloudbeds_check_out, sync_cloudbeds
from app.services.tenancy import get_tenant_entity

logger = logging.getLogger(__name__)
router = APIRouter(tags=["integrations-v1"])


class IntegrationStatusOut(BaseModel):
    provider: str
    priority: int
    configured: bool
    mode: str
    detail: str = ""
    account_owner: str = "client"  # platform | client
    account_label: str = "Client"
    free_tier: str = ""
    paid: str = ""


class V1Readiness(BaseModel):
    version: str
    milestone: str
    platform: str = "Argus OS"
    platform_url: str = ""
    queue_backend: str
    integrations: list[IntegrationStatusOut]
    ownership: list[ServiceOwnership]
    platform_pays: list[str]
    client_connects: list[str]
    ready_for_first_hotel: bool
    blockers: list[str]


@router.get("/integrations/status", response_model=V1Readiness)
def integrations_status(user: AuthUser) -> V1Readiness:
    email = get_email_client()
    items = [
        IntegrationStatusOut(
            provider="Cloudbeds",
            priority=1,
            configured=cloudbeds_client.configured,
            mode=cloudbeds_client.mode,
            detail="OAuth/API key · reservation/guest sync · check-in/out",
            account_owner="client",
            account_label="Client",
            free_tier="Included with eligible Cloudbeds accounts",
            paid="Included with eligible accounts",
        ),
        IntegrationStatusOut(
            provider="WhatsApp",
            priority=2,
            configured=whatsapp_client.configured,
            mode=whatsapp_client.mode,
            detail="Meta Cloud API · send · delivery/read · reply webhook",
            account_owner="client",
            account_label="Client",
            free_tier="None",
            paid="Meta conversation charges",
        ),
        IntegrationStatusOut(
            provider="Email",
            priority=3,
            configured=email.configured,
            mode="live" if email.configured else "mock",
            detail=f"Provider: {settings.email_provider} (Resend preferred)",
            account_owner="client",
            account_label="Client (preferred)",
            free_tier="Limited free tier / trial",
            paid="Paid plans",
        ),
        IntegrationStatusOut(
            provider="OpenAI",
            priority=4,
            configured=ai_gateway.configured,
            mode=ai_gateway.mode,
            detail=f"Model: {settings.openai_model} · structured JSON only · platform key",
            account_owner="platform",
            account_label="Yours (initially)",
            free_tier="None",
            paid="Pay per token",
        ),
        IntegrationStatusOut(
            provider="Google Reviews",
            priority=5,
            configured=google_reviews_client.configured,
            mode=google_reviews_client.mode,
            detail="Official Business Profile API only — no scraping",
            account_owner="client",
            account_label="Client",
            free_tier="Free API access (quotas + permissions)",
            paid="—",
        ),
        IntegrationStatusOut(
            provider="Stripe",
            priority=6,
            configured=stripe_payments.configured,
            mode=stripe_payments.mode,
            detail="Checkout payment links for upsells → hotel Stripe account",
            account_owner="client",
            account_label="Client",
            free_tier="No monthly fee",
            paid="Transaction fees",
        ),
    ]
    required = {"Cloudbeds", "WhatsApp", "Email", "OpenAI", "Stripe"}
    blockers = [
        i.provider for i in items if i.provider in required and not i.configured
    ]
    if not settings.is_production:
        blockers = []
    return V1Readiness(
        version=settings.app_version,
        milestone="Revisit V1.0 — one paying hotel",
        platform=settings.argus_product_line,
        platform_url=settings.argus_site_url,
        queue_backend=get_queue().backend,
        integrations=items,
        ownership=SERVICE_OWNERSHIP,
        platform_pays=["GPT-5.5 API", "PostgreSQL", "Redis"],
        client_connects=[
            "Cloudbeds API",
            "Mews API",
            "Guesty API",
            "WhatsApp Business API",
            "Resend",
            "Postmark",
            "Stripe",
            "Google Business Profile",
        ],
        ready_for_first_hotel=len(blockers) == 0,
        blockers=blockers,
    )


@router.get("/integrations/ownership", response_model=list[ServiceOwnership])
def integrations_ownership(user: AuthUser) -> list[ServiceOwnership]:
    """Commercial ownership matrix — whose account pays / connects."""
    return SERVICE_OWNERSHIP


@router.get("/analytics/sales", response_model=SalesAnalytics)
def sales_analytics(
    user: AuthUser,
    period_days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> SalesAnalytics:
    return build_sales_analytics(db, user.tenant_id, period_days=period_days)


@router.post("/connectors/cloudbeds/sync")
def cloudbeds_sync(user: ManagerUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = sync_cloudbeds(db, user.tenant_id)
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="cloudbeds_sync",
        entity_type="connector",
        entity_id="Cloudbeds",
        details=result,
    )
    db.commit()
    return result


@router.get("/connectors/cloudbeds/oauth/start")
def cloudbeds_oauth_start(user: ManagerUser) -> dict[str, str]:
    if not settings.cloudbeds_client_id:
        raise HTTPException(400, "CLOUDBEDS_CLIENT_ID not configured")
    url = cloudbeds_client.oauth_authorize_url(state=user.tenant_id)
    return {"authorize_url": url}


@router.get("/webhooks/cloudbeds/oauth/callback")
def cloudbeds_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    import json

    from app.models.entities import Connector
    from app.services.connectors import store_connector_secret

    tokens = cloudbeds_client.exchange_code(code)
    connector = (
        db.query(Connector)
        .filter(Connector.tenant_id == state, Connector.provider == "Cloudbeds")
        .first()
    )
    sealed = store_connector_secret(json.dumps(tokens))
    if connector:
        connector.config_encrypted = sealed
        connector.status = "connected"
    else:
        db.add(
            Connector(
                tenant_id=state,
                provider="Cloudbeds",
                status="connected",
                config_encrypted=sealed,
            )
        )
    db.commit()
    return {"ok": True, "tenant_id": state}


@router.post("/connectors/cloudbeds/reservations/{reservation_id}/check-in")
def api_check_in(
    reservation_id: str, user: StaffUser, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        result = cloudbeds_check_in(db, user.tenant_id, reservation_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.commit()
    return result


@router.post("/connectors/cloudbeds/reservations/{reservation_id}/check-out")
def api_check_out(
    reservation_id: str, user: StaffUser, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        result = cloudbeds_check_out(db, user.tenant_id, reservation_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.commit()
    return result


@router.get("/webhooks/whatsapp")
def whatsapp_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    challenge = whatsapp_client.verify_webhook_challenge(
        mode=hub_mode, token=hub_verify_token, challenge=hub_challenge
    )
    if challenge is None:
        raise HTTPException(403, "Verification failed")
    return PlainTextResponse(content=str(challenge))


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None),
):
    raw = await request.body()
    if not whatsapp_client.verify_signature(raw, x_hub_signature_256):
        raise HTTPException(401, "Invalid signature")
    payload = await request.json()
    events = whatsapp_client.parse_webhook(payload)
    tenant_id = "demo-hotel"
    for event in events:
        if event["type"] == "status" and event.get("provider_message_id"):
            apply_provider_status(
                db, event["provider_message_id"], event.get("status") or ""
            )
        elif event["type"] == "inbound" and event.get("from"):
            ingest_inbound_whatsapp(
                db,
                tenant_id=tenant_id,
                from_phone=event["from"],
                body=event.get("body") or "",
                provider_message_id=event.get("provider_message_id"),
                contact_name=event.get("contact_name"),
            )
    db.commit()
    return {"ok": True, "events": len(events)}


@router.post("/offers/{offer_id}/payment-link")
def create_offer_payment_link(
    offer_id: str, user: StaffUser, db: Session = Depends(get_db)
) -> dict[str, Any]:
    offer = get_tenant_entity(db, Offer, offer_id, user.tenant_id, not_found="Offer not found")
    reservation = get_tenant_entity(
        db,
        Reservation,
        offer.reservation_id,
        user.tenant_id,
        not_found="Reservation not found",
    )
    guest = get_tenant_entity(
        db, Guest, reservation.guest_id, user.tenant_id, not_found="Guest not found"
    )
    amount_cents = int(round(float(offer.price) * 100))
    link = stripe_payments.create_payment_link(
        offer_name=offer.name,
        amount_cents=amount_cents,
        guest_email=guest.email,
        metadata={
            "offer_id": offer.id,
            "tenant_id": user.tenant_id,
            "guest_id": guest.id,
            "reservation_id": reservation.id,
        },
    )
    offer.payment_link_url = link["url"]
    offer.payment_session_id = link["id"]
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="create_payment_link",
        entity_type="offer",
        entity_id=offer.id,
        details=link,
    )
    db.commit()
    return link


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if settings.stripe_configured and settings.stripe_webhook_secret:
        try:
            event = stripe_payments.construct_event(payload, sig)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Webhook error: {exc}") from exc
        event_type = event.type
        data_object = event.data.object
        metadata = dict(getattr(data_object, "metadata", {}) or {})
    else:
        import json

        event = json.loads(payload.decode() or "{}")
        event_type = event.get("type")
        data_object = (event.get("data") or {}).get("object") or {}
        metadata = data_object.get("metadata") or {}

    if event_type in (
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    ):
        offer_id = metadata.get("offer_id")
        tenant_id = metadata.get("tenant_id")
        if offer_id and tenant_id:
            offer = (
                db.query(Offer)
                .filter(Offer.id == offer_id, Offer.tenant_id == tenant_id)
                .first()
            )
            if offer:
                offer.status = OfferStatus.accepted
                offer.paid_at = datetime.utcnow()
                offer.accepted_at = offer.accepted_at or datetime.utcnow()
                reservation = db.get(Reservation, offer.reservation_id)
                guest = db.get(Guest, reservation.guest_id) if reservation else None
                if guest:
                    guest.lifetime_spend = float(guest.lifetime_spend or 0) + float(
                        offer.price
                    )
                    guest.upsell_acceptance = min(
                        1.0, float(guest.upsell_acceptance or 0) + 0.15
                    )
                    note = f"Paid upsell via Stripe: {offer.name} ({offer.price})"
                    guest.notes = f"{guest.notes}\n{note}" if guest.notes else note
                write_audit(
                    db,
                    tenant_id=tenant_id,
                    actor="stripe",
                    action="upsell_paid",
                    entity_type="offer",
                    entity_id=offer.id,
                    details={"amount": float(offer.price)},
                )
                db.commit()
    return {"ok": True}


@router.post("/connectors/google-reviews/sync")
def sync_google_reviews(user: ManagerUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    reviews = google_reviews_client.list_reviews()
    return {
        "mode": google_reviews_client.mode,
        "fetched": len(reviews),
        "message": (
            "Synced via official Google Business Profile API"
            if google_reviews_client.configured
            else "Google Reviews not configured — scraping is not supported"
        ),
        "reviews": reviews[:10],
    }
