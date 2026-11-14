"""Chainlit data layer backed by the backend API: the sidebar, resume, rename, delete and feedback.

The backend stores the messages itself when it answers, so this layer never writes steps. Every call is made with
the backend access token of the signed-in user, which travels in the metadata of Chainlit's signed session cookie:
Chainlit hands it over in `create_user` on every authenticated request (see `get_user`).
"""

import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from chainlit.context import ChainlitContextException, context
from chainlit.data.base import BaseDataLayer
from chainlit.types import Feedback, PageInfo, PaginatedResponse, Pagination, ThreadDict, ThreadFilter
from chainlit.user import PersistedUser, User

from .client import BackendClient, BackendError

logger = logging.getLogger(__name__)

TOKEN_KEY = "backend_token"
# Identifier of the user of the current HTTP request / socket connection, set while Chainlit authenticates it
_current_user: ContextVar[str | None] = ContextVar("current_user", default=None)


class BackendDataLayer(BaseDataLayer):
    def __init__(self, client: BackendClient):
        self.client = client
        self._tokens: dict[str, str] = {}

    # Users and tokens -------------------------------------------------------------------------------------

    def remember(self, identifier: str, token: str | None) -> None:
        if token:
            self._tokens[identifier] = token

    def token_for(self, identifier: str | None) -> str | None:
        return self._tokens.get(identifier) if identifier else None

    def _identifier(self) -> str | None:
        try:
            user = context.session.user
        except ChainlitContextException:
            user = None
        return user.identifier if user else _current_user.get()

    def _token(self) -> str | None:
        return self.token_for(self._identifier())

    async def get_user(self, identifier: str) -> PersistedUser | None:
        """Always None, so Chainlit calls `create_user` with the user decoded from the cookie, token included."""
        return None

    async def create_user(self, user: User) -> PersistedUser | None:
        self.remember(user.identifier, (user.metadata or {}).get(TOKEN_KEY))
        _current_user.set(user.identifier)
        metadata = {k: v for k, v in (user.metadata or {}).items() if k != TOKEN_KEY}
        created = datetime.now(timezone.utc).isoformat()
        return PersistedUser(id=user.identifier, identifier=user.identifier, display_name=user.display_name,
                             metadata=metadata, createdAt=created)  # fmt: skip

    # Threads ----------------------------------------------------------------------------------------------

    async def get_thread_author(self, thread_id: str) -> str:
        identifier, token = self._identifier(), self._token()
        if not token:
            return ""
        return identifier if await self.client.conversation(token, thread_id) else ""

    async def get_thread(self, thread_id: str) -> ThreadDict | None:
        from .present import thread_dict

        identifier, token = self._identifier(), self._token()
        found = await self.client.conversation(token, thread_id) if token else None
        return thread_dict(found, identifier) if found else None

    async def list_threads(self, pagination: Pagination, filters: ThreadFilter) -> PaginatedResponse[ThreadDict]:
        from .present import thread_dict

        token = self.token_for(filters.userId)
        if not token:
            return PaginatedResponse(PageInfo(hasNextPage=False, startCursor=None, endCursor=None), [])
        page = await self.client.conversations(token, limit=pagination.first, cursor=pagination.cursor,
                                               search=filters.search)  # fmt: skip
        threads = [thread_dict(c, filters.userId) for c in page["items"]]
        return PaginatedResponse(
            PageInfo(
                hasNextPage=page["next_cursor"] is not None,
                startCursor=threads[0]["id"] if threads else None,
                endCursor=page["next_cursor"],
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
        """First question (`user_id` given): create the conversation. Rename (`name` only): change its title.
        Session metadata saved on disconnect is ignored: the LLM settings are sent when they change."""
        token = self._token()
        if not token:
            return
        if user_id is not None:
            await self.client.start(token, thread_id)
        elif name is not None:
            await self.client.update(token, thread_id, title=name)

    async def delete_thread(self, thread_id: str):
        if token := self._token():
            await self.client.delete(token, thread_id)

    # Messages are stored by the backend -------------------------------------------------------------------

    async def create_step(self, step_dict: dict[str, Any]):
        return None

    async def update_step(self, step_dict: dict[str, Any]):
        return None

    async def delete_step(self, step_id: str):
        return None

    async def upsert_feedback(self, feedback: Feedback) -> str:
        if token := self._token():
            try:
                await self.client.feedback(token, feedback.forId, feedback.value, feedback.comment)
            except BackendError as e:
                logger.warning("feedback on %s not saved: %s", feedback.forId, e)
        return feedback.forId

    async def delete_feedback(self, feedback_id: str) -> bool:
        """`feedback_id` is the message id (see `upsert_feedback`)."""
        if token := self._token():
            await self.client.feedback(token, feedback_id, None)
            return True
        return False

    # Not used: no file upload, no favorites, no external debug UI -----------------------------------------

    async def create_element(self, element):
        return None

    async def get_element(self, thread_id: str, element_id: str):
        return None

    async def delete_element(self, element_id: str, thread_id: str | None = None):
        return None

    async def get_favorite_steps(self, user_id: str) -> list:
        return []

    async def build_debug_url(self) -> str:
        return ""

    async def close(self) -> None:
        await self.client.close()
