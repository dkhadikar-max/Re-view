"""Service cost & account ownership for Revisit V1.

Platform (Yours) owns AI + data plane.
Client hotel owns PMS, messaging, email, payments, and Google credentials.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


AccountOwner = Literal["platform", "client"]
BillingNote = str


class ServiceOwnership(BaseModel):
    service: str
    category: str
    free_tier: str
    paid: str
    account_owner: AccountOwner
    account_label: str  # "Yours" | "Client"
    notes: str = ""
    v1_required: bool = False
    implemented: bool = True


# Canonical commercial model for first hotel / sales conversations.
SERVICE_OWNERSHIP: list[ServiceOwnership] = [
    ServiceOwnership(
        service="GPT-5.5 API",
        category="AI",
        free_tier="None",
        paid="Pay per token",
        account_owner="platform",
        account_label="Yours (initially)",
        notes="Platform OpenAI key; never ask the hotel to bring an OpenAI account for V1.",
        v1_required=True,
        implemented=True,
    ),
    ServiceOwnership(
        service="PostgreSQL",
        category="Infrastructure",
        free_tier="Local / self-hosted",
        paid="Hosted managed DB",
        account_owner="platform",
        account_label="Yours",
        notes="Tenant data lives in our DB; hotels do not bring their own Postgres.",
        v1_required=True,
        implemented=True,
    ),
    ServiceOwnership(
        service="Redis",
        category="Infrastructure",
        free_tier="Local",
        paid="Hosted Redis",
        account_owner="platform",
        account_label="Yours",
        notes="Job queue only — no Kafka until throughput requires it.",
        v1_required=True,
        implemented=True,
    ),
    ServiceOwnership(
        service="Cloudbeds API",
        category="PMS",
        free_tier="Included with eligible Cloudbeds accounts",
        paid="Included with eligible accounts",
        account_owner="client",
        account_label="Client",
        notes="Hotel connects their Cloudbeds property via OAuth or API key.",
        v1_required=True,
        implemented=True,
    ),
    ServiceOwnership(
        service="Mews API",
        category="PMS",
        free_tier="Included with eligible accounts",
        paid="Included with eligible accounts",
        account_owner="client",
        account_label="Client",
        notes="Roadmap PMS — same ownership pattern as Cloudbeds.",
        v1_required=False,
        implemented=False,
    ),
    ServiceOwnership(
        service="Guesty API",
        category="PMS",
        free_tier="Included with eligible accounts",
        paid="Included with eligible accounts",
        account_owner="client",
        account_label="Client",
        notes="Roadmap PMS — vacation rental path.",
        v1_required=False,
        implemented=False,
    ),
    ServiceOwnership(
        service="WhatsApp Business API",
        category="Messaging",
        free_tier="None",
        paid="Meta conversation charges",
        account_owner="client",
        account_label="Client",
        notes="Hotel's Meta WABA + phone number ID; we send on their behalf.",
        v1_required=True,
        implemented=True,
    ),
    ServiceOwnership(
        service="Resend",
        category="Email",
        free_tier="Limited free tier",
        paid="Paid plans",
        account_owner="client",
        account_label="Client (preferred)",
        notes="Preferred email provider for V1 outbound.",
        v1_required=True,
        implemented=True,
    ),
    ServiceOwnership(
        service="Postmark",
        category="Email",
        free_tier="Trial",
        paid="Paid plans",
        account_owner="client",
        account_label="Client",
        notes="Alternative to Resend; same client-owned credential model.",
        v1_required=False,
        implemented=True,
    ),
    ServiceOwnership(
        service="Stripe",
        category="Payments",
        free_tier="No monthly fee",
        paid="Transaction fees",
        account_owner="client",
        account_label="Client",
        notes="Upsell Checkout goes to the hotel's Stripe account.",
        v1_required=True,
        implemented=True,
    ),
    ServiceOwnership(
        service="Google Business Profile",
        category="Reviews",
        free_tier="Free API access (quotas + permissions)",
        paid="—",
        account_owner="client",
        account_label="Client",
        notes="Official API only. No scraping.",
        v1_required=False,
        implemented=True,
    ),
]


def ownership_by_service() -> dict[str, ServiceOwnership]:
    return {s.service: s for s in SERVICE_OWNERSHIP}


def platform_services() -> list[ServiceOwnership]:
    return [s for s in SERVICE_OWNERSHIP if s.account_owner == "platform"]


def client_services() -> list[ServiceOwnership]:
    return [s for s in SERVICE_OWNERSHIP if s.account_owner == "client"]
