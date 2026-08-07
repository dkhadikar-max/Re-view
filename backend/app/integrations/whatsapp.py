from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.integrations.base import SendResult

logger = logging.getLogger(__name__)


class WhatsAppCloudClient:
    """Meta WhatsApp Business Cloud API adapter.

    Flow:
      Reservation → AI → Approval → Send WhatsApp → delivery status →
      read receipt → reply webhook → Guest Memory
    """

    name = "whatsapp"

    def __init__(self) -> None:
        # Platform-level credentials only — one ReVisit-owned WABA can
        # send through any phone number registered under it with the
        # same access token, so the token stays global. The number
        # itself never does (see `send`'s `phone_number_id` parameter).
        self.token = settings.whatsapp_access_token
        self.api_version = settings.whatsapp_api_version

    @property
    def configured(self) -> bool:
        """Whether ReVisit's platform-level WhatsApp integration has
        credentials at all — independent of any specific tenant's
        phone_number_id, which `send()` requires per call instead."""
        return bool(self.token)

    @property
    def mode(self) -> str:
        return "live" if self.configured else "mock"

    def send(
        self, *, phone_number_id: Optional[str], to: str, body: str, subject: Optional[str] = None
    ) -> SendResult:
        """Send through a specific WhatsApp Business number.

        `phone_number_id` identifies which of ReVisit's WABA-hosted
        numbers to send from — the caller (messaging.py) resolves this
        from the recipient's own property. This client never falls back
        to a shared/global number: a reply must leave from the same
        number the conversation is actually associated with
        (CONCIERGE.md §3 — multi-tenant routing applies to outbound
        exactly as much as inbound).
        """
        if not phone_number_id:
            raise ValueError(
                "No WhatsApp phone_number_id supplied — the caller must "
                "resolve this from the recipient's own property, not fall "
                "back to a shared default"
            )
        to_digits = "".join(ch for ch in to if ch.isdigit())
        if not self.configured:
            mid = f"wa_mock_{uuid.uuid4().hex[:12]}"
            logger.info(
                "WhatsApp MOCK send phone_number_id=%s to=%s id=%s",
                phone_number_id,
                to_digits,
                mid,
            )
            return SendResult(provider=self.name, provider_message_id=mid, status="sent")

        url = f"https://graph.facebook.com/{self.api_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to_digits,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        messages = data.get("messages") or []
        mid = messages[0]["id"] if messages else f"wa_{uuid.uuid4().hex[:12]}"
        return SendResult(
            provider=self.name,
            provider_message_id=mid,
            status="sent",
            raw=data,
        )

    def verify_webhook_challenge(
        self, *, mode: str, token: str, challenge: str
    ) -> Optional[str]:
        if mode == "subscribe" and token == settings.whatsapp_verify_token:
            return challenge
        return None

    def verify_signature(self, raw_body: bytes, signature_header: Optional[str]) -> bool:
        if not settings.whatsapp_app_secret:
            # Allow in non-production when secret unset
            return not settings.is_production
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(
            settings.whatsapp_app_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature_header)

    def parse_webhook(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize Meta webhook into status/inbound events.

        Every event carries `phone_number_id` — the number the message
        arrived at, present on every Meta webhook under
        `value.metadata.phone_number_id` — so the caller can resolve
        which tenant it belongs to (CONCIERGE.md §3) instead of
        defaulting to a single hardcoded tenant.
        """
        events: list[dict[str, Any]] = []
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
                for status in value.get("statuses") or []:
                    events.append(
                        {
                            "type": "status",
                            "phone_number_id": phone_number_id,
                            "provider_message_id": status.get("id"),
                            "status": status.get("status"),  # sent|delivered|read|failed
                            "recipient_id": status.get("recipient_id"),
                            "timestamp": status.get("timestamp"),
                            "errors": status.get("errors"),
                        }
                    )
                contacts = {
                    c.get("wa_id"): (c.get("profile") or {}).get("name")
                    for c in (value.get("contacts") or [])
                }
                for msg in value.get("messages") or []:
                    text = ""
                    if msg.get("type") == "text":
                        text = (msg.get("text") or {}).get("body") or ""
                    events.append(
                        {
                            "type": "inbound",
                            "phone_number_id": phone_number_id,
                            "provider_message_id": msg.get("id"),
                            "from": msg.get("from"),
                            "contact_name": contacts.get(msg.get("from")),
                            "timestamp": msg.get("timestamp"),
                            "body": text,
                            "raw_type": msg.get("type"),
                        }
                    )
        return events


whatsapp_client = WhatsAppCloudClient()
