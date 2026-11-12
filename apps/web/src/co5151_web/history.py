"""Chainlit data layer backed by the chat store: conversation list per user, resume, rename, delete and feedback.

Chainlit decides when to save; this module only translates between its dicts and the store's records. It never
stores the Student Record session token or the Advisor object: thread metadata keeps the chat settings only.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chainlit.data.base import BaseDataLayer
from chainlit.data.utils import queue_until_user_message
from chainlit.types import Feedback as ChainlitFeedback
from chainlit.types import PageInfo, PaginatedResponse, Pagination, ThreadDict, ThreadFilter
from chainlit.user import PersistedUser, User

from co5151_chat_store import ChatStore, Conversation, Feedback, Step, database_url, utcnow

DEFAULT_DATABASE_FILE = Path(__file__).resolve().parents[2] / ".data" / "chat.db"
# The only session values worth restoring with a conversation. Chainlit would otherwise save the whole user session.
KEPT_METADATA = ("chat_settings", "chat_profile", "client_type")
DISPLAY_FIELDS = ("showInput", "language", "defaultOpen", "autoCollapse", "tags", "generation", "command", "modes")


def open_store() -> ChatStore | None:
    """The store named by `CHAT_DATABASE_URL`, or None when chat history is turned off."""
    url = database_url(DEFAULT_DATABASE_FILE)
    return ChatStore.from_url(url) if url else None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _kept_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    return {k: metadata[k] for k in KEPT_METADATA if metadata.get(k) is not None}


def step_from_dict(step_dict: dict[str, Any]) -> Step:
    return Step(
        id=step_dict["id"],
        conversation_id=step_dict["threadId"],
        parent_id=step_dict.get("parentId"),
        type=step_dict.get("type") or "undefined",
        name=step_dict.get("name") or "",
        input=step_dict.get("input") or "",
        output=step_dict.get("output") or "",
        is_error=bool(step_dict.get("isError")),
        metadata=step_dict.get("metadata") or {},
        display={k: step_dict[k] for k in DISPLAY_FIELDS if step_dict.get(k) is not None},
        created_at=_parse_time(step_dict.get("createdAt")) or utcnow(),
        start_at=_parse_time(step_dict.get("start")),
        end_at=_parse_time(step_dict.get("end")),
    )


def step_to_dict(step: Step) -> dict[str, Any]:
    feedback = step.feedback
    return {
        **step.display,
        "id": step.id,
        "threadId": step.conversation_id,
        "parentId": step.parent_id,
        "type": step.type,
        "name": step.name,
        "input": step.input,
        "output": step.output,
        "isError": step.is_error,
        "metadata": step.metadata,
        "createdAt": _iso(step.created_at),
        "start": _iso(step.start_at),
        "end": _iso(step.end_at),
        "feedback": (
            {"id": feedback.id, "forId": step.id, "value": feedback.value, "comment": feedback.comment}
            if feedback
            else None
        ),
    }


def thread_to_dict(conversation: Conversation) -> ThreadDict:
    return {
        "id": conversation.id,
        "createdAt": _iso(conversation.created_at),
        "name": conversation.title,
        "userId": conversation.user_id,
        "userIdentifier": conversation.user_identifier,
        "tags": conversation.tags,
        "metadata": conversation.metadata,
        "steps": [step_to_dict(step) for step in conversation.steps],
        "elements": [],
    }


def _persisted(user) -> PersistedUser:
    return PersistedUser(
        id=user.id, identifier=user.identifier, metadata=user.metadata, createdAt=_iso(user.created_at)
    )


class ChatHistoryDataLayer(BaseDataLayer):
    def __init__(self, store: ChatStore):
        self.store = store
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def ready(self) -> ChatStore:
        """The store, with its tables created on first use."""
        if not self._schema_ready:
            async with self._schema_lock:
                if not self._schema_ready:
                    await self.store.create_schema()
                    self._schema_ready = True
        return self.store

    # Users

    async def get_user(self, identifier: str) -> PersistedUser | None:
        user = await (await self.ready()).get_user(identifier)
        return _persisted(user) if user else None

    async def create_user(self, user: User) -> PersistedUser | None:
        return _persisted(await (await self.ready()).get_or_create_user(user.identifier, user.metadata))

    # Threads

    async def get_thread_author(self, thread_id: str) -> str:
        return await (await self.ready()).conversation_owner(thread_id) or ""

    async def get_thread(self, thread_id: str) -> ThreadDict | None:
        conversation = await (await self.ready()).get_conversation(thread_id)
        return thread_to_dict(conversation) if conversation else None

    async def list_threads(self, pagination: Pagination, filters: ThreadFilter) -> PaginatedResponse[ThreadDict]:
        if not filters.userId:  # Chainlit always sets it to the signed-in user; never list everybody's chats
            return PaginatedResponse(PageInfo(hasNextPage=False, startCursor=None, endCursor=None), [])
        page = await (await self.ready()).list_conversations(
            filters.userId, limit=pagination.first, cursor=pagination.cursor, search=filters.search
        )
        threads = [thread_to_dict(c) for c in page.conversations]
        return PaginatedResponse(
            PageInfo(
                hasNextPage=page.has_next,
                startCursor=threads[0]["id"] if threads else None,
                endCursor=threads[-1]["id"] if threads else None,
            ),
            threads,
        )

    async def update_thread(
        self,
        thread_id: str,
        name: str | None = None,
        user_id: str | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ):
        await (await self.ready()).upsert_conversation(
            thread_id, user_id=user_id, title=name, metadata=_kept_metadata(metadata), tags=tags
        )

    async def delete_thread(self, thread_id: str):
        await (await self.ready()).delete_conversation(thread_id)

    # Steps

    @queue_until_user_message()
    async def create_step(self, step_dict: dict[str, Any]):
        await (await self.ready()).upsert_step(step_from_dict(step_dict))

    @queue_until_user_message()
    async def update_step(self, step_dict: dict[str, Any]):
        await (await self.ready()).upsert_step(step_from_dict(step_dict))

    @queue_until_user_message()
    async def delete_step(self, step_id: str):
        await (await self.ready()).delete_step(step_id)

    # Feedback

    async def upsert_feedback(self, feedback: ChainlitFeedback) -> str:
        return await (await self.ready()).upsert_feedback(
            Feedback(
                id=feedback.id or str(uuid.uuid4()),
                step_id=feedback.forId,
                value=feedback.value,
                comment=feedback.comment,
            )  # fmt: skip
        )

    async def delete_feedback(self, feedback_id: str) -> bool:
        return await (await self.ready()).delete_feedback(feedback_id)

    # Not used by this app: no file upload, no favorites, no external debug UI

    @queue_until_user_message()
    async def create_element(self, element):
        return None

    async def get_element(self, thread_id: str, element_id: str):
        return None

    @queue_until_user_message()
    async def delete_element(self, element_id: str, thread_id: str | None = None):
        return None

    async def get_favorite_steps(self, user_id: str) -> list:
        return []

    async def build_debug_url(self) -> str:
        return ""

    async def close(self) -> None:
        await self.store.close()


def chat_history(thread: ThreadDict) -> list[dict[str, str]]:
    """The question / answer turns of a saved conversation, in the form the Advisor takes as `history`."""
    roles = {"user_message": "user", "assistant_message": "assistant"}
    return [
        {"role": roles[step["type"]], "content": step["output"]}
        for step in thread.get("steps", [])
        if step.get("type") in roles and step.get("output")
    ]


def guest_identifier() -> str:
    """Guests share one login, so each guest sign-in gets its own identity and never sees another guest's chats."""
    return f"khach-{uuid.uuid4().hex[:12]}"
