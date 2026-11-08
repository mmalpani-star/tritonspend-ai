"""Best-effort Food Chat write limits per participant.

IMPORTANT: this is an in-memory, per-process sliding window. It slows down casual abuse from
one signed-in account on one server process. It is NOT production-grade protection: limits
reset on restart, are not shared between worker processes or instances, and do nothing about
many accounts. Production needs a shared store (e.g. a database table or Redis) and per-IP
limits at the edge.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException

# action -> (max events, window seconds)
FOOD_CHAT_LIMITS: dict[str, tuple[int, int]] = {
    "review": (10, 3600),
    "edit": (60, 600),
    "comment": (30, 600),
    "vote": (120, 600),
    "report": (20, 3600),
    "favorite": (120, 600),
    "rating": (60, 600),
    "message": (20, 60),
}


class SlidingWindowLimiter:
    def __init__(self, limits: dict[str, tuple[int, int]]):
        self.limits = limits
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, participant_id: str, action: str, now: float | None = None) -> None:
        """Record one event, or raise 429 if the participant is over the action's limit."""
        limit, window = self.limits[action]
        now = time.monotonic() if now is None else now
        with self._lock:
            events = self._events[(participant_id, action)]
            while events and events[0] <= now - window:
                events.popleft()
            if len(events) >= limit:
                retry_after = int(events[0] + window - now) + 1
                raise HTTPException(
                    status_code=429,
                    detail="You're doing that too often. Please wait a few minutes and try again.",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


food_chat_limiter = SlidingWindowLimiter(FOOD_CHAT_LIMITS)
