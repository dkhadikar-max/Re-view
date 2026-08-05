from __future__ import annotations

import logging
import uuid
from typing import Optional

import httpx

from app.core.config import settings
from app.integrations.base import SendResult

logger = logging.getLogger(__name__)


class ResendClient:
    name = "resend"

    def __init__(self) -> None:
        self.api_key = settings.resend_api_key
        self.from_email = settings.resend_from_email

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def send(self, *, to: str, body: str, subject: Optional[str] = None) -> SendResult:
        if not self.configured:
            mid = f"email_mock_{uuid.uuid4().hex[:12]}"
            logger.info("Resend MOCK to=%s subject=%s", to, subject)
            return SendResult(provider=self.name, provider_message_id=mid, status="sent")
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": self.from_email,
                    "to": [to],
                    "subject": subject or "Message from your hotel",
                    "text": body,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return SendResult(
            provider=self.name,
            provider_message_id=str(data.get("id") or uuid.uuid4()),
            status="sent",
            raw=data,
        )


class PostmarkClient:
    name = "postmark"

    def __init__(self) -> None:
        self.token = settings.postmark_server_token
        self.from_email = settings.postmark_from_email or "noreply@example.com"

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def send(self, *, to: str, body: str, subject: Optional[str] = None) -> SendResult:
        if not self.configured:
            mid = f"pm_mock_{uuid.uuid4().hex[:12]}"
            logger.info("Postmark MOCK to=%s subject=%s", to, subject)
            return SendResult(provider=self.name, provider_message_id=mid, status="sent")
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "X-Postmark-Server-Token": self.token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "From": self.from_email,
                    "To": to,
                    "Subject": subject or "Message from your hotel",
                    "TextBody": body,
                    "MessageStream": "outbound",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return SendResult(
            provider=self.name,
            provider_message_id=str(data.get("MessageID") or uuid.uuid4()),
            status="sent",
            raw=data,
        )


def get_email_client():
    if settings.email_provider == "postmark":
        return PostmarkClient()
    return ResendClient()


email_client = get_email_client()
