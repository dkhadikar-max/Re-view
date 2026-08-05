from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class JobQueue:
    """Lightweight job queue.

    Uses Redis when available; falls back to in-process list for local/dev/tests.
    V1 does NOT use Kafka — Redis + Postgres workers are enough for first 100 hotels.
    """

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._memory: list[dict[str, Any]] = []
        self._redis = None
        try:
            import redis

            client = redis.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            self._redis = client
            logger.info("JobQueue connected to Redis")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis unavailable (%s) — using in-memory job queue", exc)

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def enqueue(self, job_type: str, payload: dict[str, Any]) -> str:
        job = {"type": job_type, "payload": payload}
        if self._redis is not None:
            self._redis.lpush("revisit:jobs", json.dumps(job))
            return "redis"
        self._memory.append(job)
        return "memory"

    def dequeue(self, timeout: int = 1) -> Optional[dict[str, Any]]:
        if self._redis is not None:
            item = self._redis.brpop("revisit:jobs", timeout=timeout)
            if not item:
                return None
            return json.loads(item[1])
        if not self._memory:
            return None
        return self._memory.pop(0)

    def depth(self) -> int:
        if self._redis is not None:
            return int(self._redis.llen("revisit:jobs"))
        return len(self._memory)


_queue: Optional[JobQueue] = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        from app.core.config import settings

        _queue = JobQueue(settings.redis_url)
    return _queue
