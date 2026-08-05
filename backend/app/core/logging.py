from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id", default="-")
actor_ctx: ContextVar[str] = ContextVar("actor", default="anonymous")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
        record.tenant_id = tenant_id_ctx.get("-")
        record.actor = actor_ctx.get("anonymous")
        return True


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(isinstance(f, ContextFilter) for h in root.handlers for f in h.filters):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] "
            "request_id=%(request_id)s tenant=%(tenant_id)s actor=%(actor)s %(message)s"
        )
    )
    handler.addFilter(ContextFilter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def new_request_id() -> str:
    return str(uuid.uuid4())


def log_extra(**kwargs: Any) -> dict[str, Any]:
    return kwargs


class Timer:
    def __init__(self) -> None:
        self.start = time.perf_counter()

    def ms(self) -> float:
        return round((time.perf_counter() - self.start) * 1000, 2)
