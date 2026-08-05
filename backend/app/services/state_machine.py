from __future__ import annotations

from fastapi import HTTPException, status

from app.models.entities import (
    ApprovalStatus,
    MessageStatus,
    OfferStatus,
    ReservationStatus,
    TaskStatus,
)

MESSAGE_TRANSITIONS: dict[MessageStatus, set[MessageStatus]] = {
    MessageStatus.draft: {MessageStatus.pending_approval, MessageStatus.queued, MessageStatus.failed},
    MessageStatus.pending_approval: {
        MessageStatus.queued,
        MessageStatus.draft,
        MessageStatus.failed,
    },
    MessageStatus.queued: {MessageStatus.sent, MessageStatus.failed, MessageStatus.draft},
    MessageStatus.sent: {MessageStatus.delivered, MessageStatus.failed},
    MessageStatus.delivered: set(),
    MessageStatus.failed: {MessageStatus.draft, MessageStatus.queued},
}

OFFER_TRANSITIONS: dict[OfferStatus, set[OfferStatus]] = {
    OfferStatus.available: {OfferStatus.offered, OfferStatus.expired},
    OfferStatus.offered: {
        OfferStatus.accepted,
        OfferStatus.declined,
        OfferStatus.expired,
    },
    OfferStatus.accepted: set(),
    OfferStatus.declined: set(),
    OfferStatus.expired: set(),
}

APPROVAL_TRANSITIONS: dict[ApprovalStatus, set[ApprovalStatus]] = {
    ApprovalStatus.pending: {ApprovalStatus.approved, ApprovalStatus.rejected},
    ApprovalStatus.approved: set(),
    ApprovalStatus.rejected: set(),
}

RESERVATION_TRANSITIONS: dict[ReservationStatus, set[ReservationStatus]] = {
    ReservationStatus.confirmed: {
        ReservationStatus.checked_in,
        ReservationStatus.checked_out,
        ReservationStatus.cancelled,
    },
    ReservationStatus.checked_in: {
        ReservationStatus.checked_out,
        ReservationStatus.cancelled,
    },
    ReservationStatus.checked_out: set(),
    ReservationStatus.cancelled: set(),
}

TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.open: {TaskStatus.in_progress, TaskStatus.done, TaskStatus.cancelled},
    TaskStatus.in_progress: {TaskStatus.done, TaskStatus.cancelled, TaskStatus.open},
    TaskStatus.done: set(),
    TaskStatus.cancelled: set(),
}


def transition(current, target, table: dict, entity: str):
    allowed = table.get(current, set())
    if target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid {entity} transition: {getattr(current, 'value', current)} → {getattr(target, 'value', target)}",
        )
    return target
