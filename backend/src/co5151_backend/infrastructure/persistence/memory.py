"""Chat history in process memory: for the evaluation (one fresh store per question) and for tests."""

from dataclasses import replace

from ...domain.conversation import ChatSettings, Conversation, ConversationPage, Feedback, Message, MessageRole, utcnow
from ...domain.errors import NotFound
from ...domain.trace import Trace


class InMemoryChatRepository:
    def __init__(self):
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[Message]] = {}
        self._traces: dict[str, Trace] = {}

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

    async def save(self, trace: Trace) -> None:
        self._traces[trace.trace_id] = trace

    async def get_trace(self, trace_id: str, owner_id: str) -> Trace | None:
        trace = self._traces.get(trace_id)
        return trace if trace and self._owned(trace.conversation_id, owner_id) else None


class InMemoryTraceRepository:
    def __init__(self, chats: InMemoryChatRepository):
        self._chats = chats

    async def save(self, trace: Trace) -> None:
        await self._chats.save(trace)

    async def get(self, trace_id: str, owner_id: str) -> Trace | None:
        return await self._chats.get_trace(trace_id, owner_id)
