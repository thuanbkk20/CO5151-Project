"""Chat history in process memory: for the evaluation (one fresh store per question) and for tests."""

from collections.abc import Sequence
from dataclasses import replace

from ...domain.conversation import ChatSettings, Conversation, ConversationPage, Feedback, Message, MessageRole, utcnow
from ...domain.errors import NotFound
from ...domain.trace import Span, Trace, TraceRecord


class InMemoryChatRepository:
    def __init__(self):
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[Message]] = {}
        self._traces: dict[str, Trace] = {}
        self._spans: dict[str, list[Span]] = {}

    def _owned(self, conversation_id: str, owner_id: str) -> Conversation | None:
        found = self._conversations.get(conversation_id)
        return found if found and found.owner_id == owner_id else None

    async def create(self, conversation: Conversation) -> Conversation:
        existing = self._conversations.get(conversation.id)
        if existing is not None:
            if existing.owner_id != conversation.owner_id:
                raise NotFound(conversation.id)
            return existing
        self._conversations[conversation.id] = replace(conversation, messages=())
        self._messages[conversation.id] = []
        return self._conversations[conversation.id]

    async def get(self, conversation_id: str, owner_id: str) -> Conversation | None:
        found = self._owned(conversation_id, owner_id)
        return replace(found, messages=tuple(self._messages[conversation_id])) if found else None

    async def list_by_owner(
        self, owner_id: str, *, limit: int = 20, cursor: str | None = None, search: str | None = None
    ) -> ConversationPage:
        items = sorted(
            (c for c in self._conversations.values() if c.owner_id == owner_id),
            key=lambda c: (c.updated_at, c.id),
            reverse=True,
        )
        if search:
            items = [c for c in items if search.lower() in (c.title or "").lower()]
        if cursor:
            ids = [c.id for c in items]
            items = items[ids.index(cursor) + 1 :] if cursor in ids else items
        return ConversationPage(items[:limit], next_cursor=items[limit - 1].id if len(items) > limit else None)

    async def update(
        self, conversation_id: str, owner_id: str, *, title: str | None = None, settings: ChatSettings | None = None
    ) -> Conversation | None:
        found = self._owned(conversation_id, owner_id)
        if found is None:
            return None
        changed = replace(found, title=found.title if title is None else title, settings=settings or found.settings)
        self._conversations[conversation_id] = changed
        return changed

    async def delete(self, conversation_id: str, owner_id: str) -> bool:
        if self._owned(conversation_id, owner_id) is None:
            return False
        del self._conversations[conversation_id], self._messages[conversation_id]
        self._traces = {k: t for k, t in self._traces.items() if t.conversation_id != conversation_id}
        self._spans = {k: s for k, s in self._spans.items() if k in self._traces}
        return True

    async def add_message(self, message: Message) -> None:
        self._messages[message.conversation_id].append(message)
        found = self._conversations[message.conversation_id]
        self._conversations[found.id] = replace(found, updated_at=max(message.created_at, utcnow()))

    async def recent_messages(self, conversation_id: str, limit: int) -> list[Message]:
        return list(self._messages.get(conversation_id, [])[-limit:]) if limit > 0 else []

    async def set_feedback(self, message_id: str, owner_id: str, feedback: Feedback | None) -> bool:
        for conversation_id, messages in self._messages.items():
            if self._owned(conversation_id, owner_id) is None:
                continue
            for i, m in enumerate(messages):
                if m.id == message_id and m.role is MessageRole.ASSISTANT:
                    messages[i] = replace(m, feedback=feedback)
                    return True
        return False

    async def save(self, trace: Trace, spans: Sequence[Span] = ()) -> None:
        self._traces[trace.trace_id] = trace
        self._spans[trace.trace_id] = sorted(spans, key=lambda s: s.start_ms)

    async def get_trace(self, trace_id: str, owner_id: str) -> Trace | None:
        trace = self._traces.get(trace_id)
        return trace if trace and self._owned(trace.conversation_id, owner_id) else None

    def _record(self, trace: Trace, spans: list[Span] | None = None) -> TraceRecord:
        messages = {m.id: m.content for m in self._messages.get(trace.conversation_id, [])}
        return TraceRecord(trace, self._conversations[trace.conversation_id].owner_id,
                           messages.get(trace.user_message_id), messages.get(trace.answer_message_id),
                           spans or [])  # fmt: skip

    async def recent_traces(self, conversation_id: str | None, limit: int) -> list[TraceRecord]:
        traces = [t for t in self._traces.values() if conversation_id in (None, t.conversation_id)]
        traces.sort(key=lambda t: (t.created_at is not None, t.created_at), reverse=True)
        return [self._record(t) for t in traces[:limit]]

    async def find_trace(self, trace_id: str) -> TraceRecord | None:
        trace = self._traces.get(trace_id)
        return self._record(trace, list(self._spans.get(trace_id, []))) if trace else None

    async def get_spans(self, trace_id: str, owner_id: str) -> list[Span] | None:
        if await self.get_trace(trace_id, owner_id) is None:
            return None
        return list(self._spans.get(trace_id, []))


class InMemoryTraceRepository:
    def __init__(self, chats: InMemoryChatRepository):
        self._chats = chats

    async def save(self, trace: Trace, spans: Sequence[Span] = ()) -> None:
        await self._chats.save(trace, spans)

    async def get(self, trace_id: str, owner_id: str) -> Trace | None:
        return await self._chats.get_trace(trace_id, owner_id)

    async def spans(self, trace_id: str, owner_id: str) -> list[Span] | None:
        return await self._chats.get_spans(trace_id, owner_id)

    async def recent(self, *, conversation_id: str | None = None, limit: int = 50) -> list[TraceRecord]:
        return await self._chats.recent_traces(conversation_id, limit)

    async def find(self, trace_id: str) -> TraceRecord | None:
        return await self._chats.find_trace(trace_id)
