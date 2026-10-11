"""Access log for every tool call, allowed or denied.

Actor and target are stored as keyed pseudonyms (HMAC), never as raw usernames / MSSV, so the log
can be kept for audit without becoming another copy of personal data.
"""

import hashlib
import hmac
import json
import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass

logger = logging.getLogger("student_server.audit")


@dataclass(frozen=True)
class AccessEvent:
    ts: float
    tool: str
    actor: str | None
    role: str | None
    target: str | None
    allowed: bool
    error: str | None = None


class AccessLog:
    def __init__(self, key: bytes, maxlen: int = 10_000):
        self._key = key
        self._events: deque[AccessEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def pseudonym(self, value: str | None) -> str | None:
        if value is None:
            return None
        return hmac.new(self._key, b"audit:" + value.encode(), hashlib.sha256).hexdigest()[:12]

    def record(self, tool: str, *, actor: str | None, role: str | None, target: str | None, allowed: bool,
               error: str | None = None) -> AccessEvent:  # fmt: skip
        ev = AccessEvent(time.time(), tool, self.pseudonym(actor), role, self.pseudonym(target), allowed, error)
        with self._lock:
            self._events.append(ev)
        logger.info(json.dumps(asdict(ev)))
        return ev

    def events(self) -> list[AccessEvent]:
        with self._lock:
            return list(self._events)
