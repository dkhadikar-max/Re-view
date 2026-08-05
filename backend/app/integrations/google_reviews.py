from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class GoogleReviewsClient:
    """Official Google Business Profile / My Business API path only.

    No scraping. Requires OAuth refresh token + location id.
    Workflow: Review → Analyze → Themes → Reply Draft → Approval → Publish
    """

    name = "google_reviews"

    def __init__(self) -> None:
        self.refresh_token = settings.google_refresh_token
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.account_id = settings.google_account_id
        self.location_id = settings.google_location_id

    @property
    def configured(self) -> bool:
        return bool(
            self.refresh_token
            and self.client_id
            and self.client_secret
            and self.location_id
        )

    @property
    def mode(self) -> str:
        return "live" if self.configured else "mock"

    def _access_token(self) -> str:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    def list_reviews(self, page_size: int = 20) -> list[dict[str, Any]]:
        if not self.configured:
            logger.info("Google Reviews not configured — returning empty (no scraping)")
            return []
        token = self._access_token()
        # Google Business Profile API
        name = f"accounts/{self.account_id}/locations/{self.location_id}"
        url = f"https://mybusiness.googleapis.com/v4/{name}/reviews"
        with httpx.Client(timeout=45.0) as client:
            resp = client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"pageSize": page_size},
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("reviews") or []

    def publish_reply(self, review_name: str, comment: str) -> dict[str, Any]:
        if not self.configured:
            return {"ok": True, "mode": "mock", "review": review_name}
        token = self._access_token()
        url = f"https://mybusiness.googleapis.com/v4/{review_name}/reply"
        with httpx.Client(timeout=45.0) as client:
            resp = client.put(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"comment": comment},
            )
            resp.raise_for_status()
            return resp.json()


google_reviews_client = GoogleReviewsClient()
