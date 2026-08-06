# ReVisit Architecture

Version: 1.0
Status: Living Document
Owner: Engineering

---

# Vision

ReVisit is an AI-powered Guest Revenue Platform.

Our mission is simple:

> Help businesses turn first-time customers into repeat customers.

Hotels are our first vertical.

The architecture must support additional industries without major rewrites.

Future verticals include:

- Restaurants
- Resorts
- Vacation Rentals
- Salons
- Dental Clinics
- Medical Practices
- Car Rentals
- Tour Operators

The core platform should never be tightly coupled to hotels.

---

# Core Principles

## 1. Business First

Customers buy:

- More reviews
- More repeat customers
- More revenue
- Better customer experience
- Less manual work

AI exists to deliver these outcomes.

Never build technology for its own sake.

---

## 2. Modular Architecture

Every domain owns its own logic.

Never create "god services."

Each module should be independently maintainable.

---

## 3. Event Driven

Everything important becomes an event.

Examples

ReservationCreated

ReservationCheckedIn

ReservationCheckedOut

ReviewSubmitted

ReviewReplied

RewardRedeemed

GuestReturned

UpsellPurchased

Events drive automation.

Avoid tightly coupled services.

---

## 4. Multi Tenant

Everything belongs to a tenant.

Every database query must respect tenant isolation.

Never bypass tenant filters.

---

## 5. AI Is A Service

AI is not the application.

AI is a supporting capability.

Rules

↓

Templates

↓

Guest Memory

↓

AI

AI should only be used when it creates measurable value.

---

# Product Domains

Core Platform

- Authentication
- Organization
- Users
- Roles
- Billing
- Notifications
- Analytics
- AI Gateway
- Connectors

Customer

- Customer
- Preferences
- Timeline
- Tags
- Communication
- Lifetime Value
- Loyalty

Journey

- Reservation
- Visit
- Stay
- Appointment
- Order

Engagement

- Messages
- Campaigns
- Rewards
- Reviews
- Suggestions

Revenue

- Upsells
- Cross-sells
- Offers
- Promotions

Insights

- Reports
- Metrics
- Trends
- Recommendations

---

# Hospitality Module

Hotels are implemented as a vertical.

Hospitality-specific concepts

- Room
- Room Type
- Check-in
- Check-out
- Stay
- PMS
- OTA
- Google Reviews

These belong inside the hospitality module.

Never place them in the platform core.

---

# System Architecture

```
                Next.js

                    │

             FastAPI Gateway

                    │

        ┌───────────┼────────────┐

        │           │            │

   Domain API   AI Gateway   Connectors

        │           │            │

        └───────────┼────────────┘

                    │

              Event Bus

                    │

      Background Workers

                    │

 PostgreSQL   Redis   Storage
```

---

# Backend Structure

```
backend/

modules/

auth/

organization/

customer/

reservation/

review/

rewards/

campaigns/

analytics/

messaging/

connectors/

hospitality/

ai/

shared/

core/
```

Every module contains

```
models/

schemas/

repositories/

services/

routers/

events/

tests/
```

Never put unrelated logic into another module.

---

# Frontend Structure

```
frontend/

app/

components/

features/

hooks/

services/

types/

lib/
```

Pages should never contain business logic.

Business logic belongs in services/hooks.

---

# AI Architecture

```
Application

↓

AI Gateway

↓

Prompt Builder

↓

LLM Provider

↓

Structured JSON

↓

Validator

↓

Application
```

Never call the LLM directly from UI components.

Never trust raw LLM output.

Always validate.

---

# Connector Architecture

Every external integration must implement

```
connect()

disconnect()

sync()

webhook()

validate()

health()
```

Examples

Cloudbeds

Mews

Opera

WhatsApp

Stripe

Google

The rest of the application must never depend on a specific provider.

---

# Notification Architecture

Channels

- WhatsApp
- Email
- SMS
- Push (future)

One notification service.

Never duplicate message sending.

---

# Event Flow

Reservation Created

↓

Guest Updated

↓

Schedule Automation

↓

Pre-arrival Message

↓

Check-in

↓

During Stay

↓

Checkout

↓

Review Request

↓

Review Reply

↓

Rewards

↓

Campaign

↓

Repeat Booking

Everything should be traceable.

---

# Database Principles

Every entity

- UUID primary keys
- created_at
- updated_at
- tenant_id
- audit trail where required

Avoid soft deletes unless necessary.

Use foreign keys.

Use indexes.

---

# Security

JWT

RBAC

Tenant Isolation

Rate Limiting

Audit Logging

Secrets in environment

Input validation

Output validation

Never expose internal IDs.

---

# UI Philosophy

ReVisit is premium software.

The interface should feel like

- Stripe
- Linear
- HubSpot
- Notion

Technology disappears.

Business outcomes remain.

Avoid excessive AI branding.

AI should only appear when representing a genuine capability.

Good

Assistant

Insights

Suggestions

Guest Concierge

Avoid

AI Dashboard

AI Revenue

AI Guest

AI Messages

AI Analytics

---

# Performance

Avoid unnecessary database queries.

Use pagination.

Use background workers.

Cache expensive reads.

Prefer events over polling.

---

# Testing

Every feature should include

Unit Tests

Integration Tests

API Tests

Critical business flows must never ship without tests.

---

# Coding Standards

- Strong typing
- Small services
- Repository pattern
- Dependency injection
- No duplicated logic
- No business logic in routes
- No hidden side effects

Readable code is preferred over clever code.

---

# Definition of Done

A feature is complete when

✓ Architecture approved

✓ Code implemented

✓ Tests written

✓ Documentation updated

✓ Metrics added

✓ Tenant isolation verified

✓ Security reviewed

✓ UI reviewed

✓ Logging added

✓ Production ready

---

# Product Roadmap

Phase 1

Hospitality MVP

Cloudbeds

WhatsApp

Google Reviews

Guest Memory

Rewards

Analytics

---

Phase 2

Self-service onboarding

Marketplace integrations

Billing

Campaigns

Guest Concierge

---

Phase 3

Predictive Intelligence

Revenue Optimization

Benchmarking

Enterprise Features

---

# Engineering Philosophy

Every engineering decision should answer:

Does this make ReVisit easier to scale?

Does this make ReVisit easier to maintain?

Does this help customers generate more revenue?

If not, reconsider the implementation.
