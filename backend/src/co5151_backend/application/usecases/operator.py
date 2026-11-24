"""What the operator console reads: every user's traces, newest first, and one trace with its spans.

Only the admin API calls these, after `AuthenticateOperator`; nothing here is reachable with a user's token.
"""

from ...domain.errors import InvalidRequest, NotFound
from ...domain.trace import SessionRecord, TraceRecord
from ..ports import TraceLog

MAX_LIMIT = 200


class OperatorTraces:
    def __init__(self, traces: TraceLog):
        self._traces = traces

    async def recent(self, *, conversation_id: str | None = None, limit: int = 50) -> list[TraceRecord]:
        if not 1 <= limit <= MAX_LIMIT:
            raise InvalidRequest(f"limit must be 1 to {MAX_LIMIT}")
        return await self._traces.recent(conversation_id=conversation_id or None, limit=limit)

    async def sessions(self, *, limit: int = 50) -> list[SessionRecord]:
        if not 1 <= limit <= MAX_LIMIT:
            raise InvalidRequest(f"limit must be 1 to {MAX_LIMIT}")
        return await self._traces.sessions(limit=limit)

    async def detail(self, trace_id: str) -> TraceRecord:
        found = await self._traces.find(trace_id)
        if found is None:
            raise NotFound(trace_id)
        return found
