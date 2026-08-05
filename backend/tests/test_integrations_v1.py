from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_integrations_status(client: TestClient, auth_header: dict):
    res = client.get("/api/integrations/status", headers=auth_header)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["version"]
    assert body["queue_backend"] in ("memory", "redis")
    providers = {i["provider"] for i in body["integrations"]}
    assert {
        "Cloudbeds",
        "WhatsApp",
        "Email",
        "OpenAI",
        "Google Reviews",
        "Stripe",
    }.issubset(providers)
    assert body["ready_for_first_hotel"] is True  # non-production clears blockers
    assert body["platform"] == "Argus OS"
    assert "argus" in body["platform_url"].lower()
    assert "GPT-5.5 API" in body["platform_pays"]
    assert "PostgreSQL" in body["platform_pays"]
    assert "Redis" in body["platform_pays"]
    assert "Cloudbeds API" in body["client_connects"]
    assert "WhatsApp Business API" in body["client_connects"]
    assert "Stripe" in body["client_connects"]
    openai = next(i for i in body["integrations"] if i["provider"] == "OpenAI")
    assert openai["account_owner"] == "platform"
    cloudbeds = next(i for i in body["integrations"] if i["provider"] == "Cloudbeds")
    assert cloudbeds["account_owner"] == "client"


def test_integrations_ownership_matrix(client: TestClient, auth_header: dict):
    res = client.get("/api/integrations/ownership", headers=auth_header)
    assert res.status_code == 200, res.text
    rows = res.json()
    by_name = {r["service"]: r for r in rows}
    assert by_name["GPT-5.5 API"]["account_owner"] == "platform"
    assert by_name["Cloudbeds API"]["account_owner"] == "client"
    assert by_name["Mews API"]["implemented"] is False
    assert by_name["Guesty API"]["implemented"] is False
    assert by_name["Resend"]["account_label"].startswith("Client")
    assert by_name["Stripe"]["account_owner"] == "client"
    assert by_name["Google Business Profile"]["account_owner"] == "client"


def test_sales_analytics(client: TestClient, auth_header: dict):
    res = client.get("/api/analytics/sales", headers=auth_header)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "review_rate" in body
    assert "repeat_guests" in body
    assert "revenue_generated" in body
    assert "ai_messages" in body
    assert "upsell_conversion" in body
    assert "guest_satisfaction" in body


def test_cloudbeds_mock_sync(client: TestClient, auth_header: dict):
    res = client.post("/api/connectors/cloudbeds/sync", headers=auth_header)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "mock"
    assert body["imported"] >= 1


def test_whatsapp_webhook_verify_and_inbound(client: TestClient, auth_header: dict):
    verify = client.get(
        "/api/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "revisit-whatsapp-verify",
            "hub.challenge": "12345",
        },
    )
    assert verify.status_code == 200
    assert verify.text == "12345"

    # Seed guest phone match — use a known seeded guest phone if present
    guests = client.get("/api/guests", headers=auth_header)
    assert guests.status_code == 200
    guest_list = guests.json()
    phone = None
    for g in guest_list:
        if g.get("phone"):
            phone = g["phone"]
            break
    assert phone, "seed should include a guest with phone"

    digits = "".join(ch for ch in phone if ch.isdigit())
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"wa_id": digits, "profile": {"name": "Test Guest"}}
                            ],
                            "messages": [
                                {
                                    "id": "wamid.inbound.test",
                                    "from": digits,
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Yes please book the airport pickup"},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }
    res = client.post("/api/webhooks/whatsapp", json=payload)
    assert res.status_code == 200, res.text
    assert res.json()["events"] == 1


def test_stripe_payment_link_and_webhook(client: TestClient, auth_header: dict):
    offers = client.get("/api/offers", headers=auth_header)
    assert offers.status_code == 200
    offered = [o for o in offers.json() if o["status"] == "offered"]
    assert offered, "need an offered upsell"
    offer_id = offered[0]["id"]

    link = client.post(f"/api/offers/{offer_id}/payment-link", headers=auth_header)
    assert link.status_code == 200, link.text
    body = link.json()
    assert body["mode"] == "mock"
    assert body["url"]
    session_id = body["id"]

    webhook = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "metadata": {
                    "offer_id": offer_id,
                    "tenant_id": "demo-hotel",
                },
            }
        },
    }
    paid = client.post(
        "/api/webhooks/stripe",
        content=json.dumps(webhook),
        headers={"Content-Type": "application/json"},
    )
    assert paid.status_code == 200, paid.text

    refreshed = client.get("/api/offers", headers=auth_header)
    match = next(o for o in refreshed.json() if o["id"] == offer_id)
    assert match["status"] == "accepted"
    assert match.get("paid_at")


def test_google_reviews_no_scrape(client: TestClient, auth_header: dict):
    res = client.post("/api/connectors/google-reviews/sync", headers=auth_header)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "mock"
    assert "scraping is not supported" in body["message"].lower() or body["fetched"] == 0
