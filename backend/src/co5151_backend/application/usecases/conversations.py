"""Conversation history of the signed-in user: start, list, read, rename, change LLM, delete, feedback, traces."""

import uuid

from ...domain.conversation import ChatSettings, Conversation, ConversationPage, Feedback, utcnow
from ...domain.errors import InvalidRequest, NotFound
from ...domain.principal import Principal
from ...domain.trace import Trace
from ..ports import ChatModels, ConversationRepository, TraceRepository

MAX_PAGE = 100
MAX_MODEL_NAME = 100


class Conversations:
    def __init__(self, chats: ConversationRepository, traces: TraceRepository, models: ChatModels):
        self._chats = chats
        self._traces = traces
        self._models = models

    def llm_choices(self) -> tuple[list[str], str]:
        """Providers with a key on this server, and the default one."""
        return self._models.providers(), self._models.default_provider()

    def _checked(self, settings: ChatSettings) -> ChatSettings:
        if settings.provider is not None and settings.provider not in self._models.providers():
            raise InvalidRequest(f"LLM provider {settings.provider!r} is not configured on this server")
        model = (settings.model or "").strip() or None
        if model is not None and len(model) > MAX_MODEL_NAME:
            raise InvalidRequest("model name too long")
        return ChatSettings(settings.provider, model)

    async def start(
        self,
        principal: Principal,
        *,
        conversation_id: str | None = None,
        title: str | None = None,
        settings: ChatSettings | None = None,
    ) -> Conversation:
        """Idempotent for a client-chosen id: starting it again returns the same conversation."""
        if conversation_id is not None:
            try:
                conversation_id = str(uuid.UUID(conversation_id))
            except ValueError:
                raise InvalidRequest("conversation id must be a UUID") from None
        now = utcnow()
        return await self._chats.create(
            Conversation(
                id=conversation_id or str(uuid.uuid4()),
                owner_id=principal.user_id,
                created_at=now,
                updated_at=now,
                title=title,
                settings=self._checked(settings or ChatSettings()),
            )
        )

    async def list_page(
        self, principal: Principal, *, limit: int = 20, cursor: str | None = None, search: str | None = None
    ) -> ConversationPage:
        limit = max(1, min(limit, MAX_PAGE))
        return await self._chats.list_by_owner(principal.user_id, limit=limit, cursor=cursor, search=search or None)

    async def get(self, principal: Principal, conversation_id: str) -> Conversation:
        found = await self._chats.get(conversation_id, principal.user_id)
        if found is None:
            raise NotFound(conversation_id)
        return found

    async def update(
        self,
        principal: Principal,
        conversation_id: str,
        *,
        title: str | None = None,
        settings: ChatSettings | None = None,
    ) -> Conversation:
        if title is not None and not title.strip():
            raise InvalidRequest("title must not be empty")
        checked = self._checked(settings) if settings is not None else None
        found = await self._chats.update(conversation_id, principal.user_id, title=title, settings=checked)
        if found is None:
            raise NotFound(conversation_id)
        return found

    async def delete(self, principal: Principal, conversation_id: str) -> None:
        if not await self._chats.delete(conversation_id, principal.user_id):
            raise NotFound(conversation_id)

    async def set_feedback(self, principal: Principal, message_id: str, feedback: Feedback | None) -> None:
        if feedback is not None and feedback.value not in (0, 1):
            raise InvalidRequest("feedback value must be 0 or 1")
        if not await self._chats.set_feedback(message_id, principal.user_id, feedback):
            raise NotFound(message_id)

    async def trace(self, principal: Principal, trace_id: str) -> Trace:
        found = await self._traces.get(trace_id, principal.user_id)
        if found is None:
            raise NotFound(trace_id)
        return found
