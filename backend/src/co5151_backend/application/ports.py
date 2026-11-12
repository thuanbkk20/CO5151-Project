"""Interfaces the application needs from the outside world. Adapters in `infrastructure/` implement them.

Use cases and agents only see these: swapping SQLite for PostgreSQL, the MCP transport, or the LLM provider never
changes them.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from co5151_contracts import ToolResult

from ..domain.conversation import ChatSettings, Conversation, ConversationPage, Feedback, Message
from ..domain.principal import Account, Principal
from ..domain.trace import Trace
from .events import AnswerEvent

# Persistence ---------------------------------------------------------------------------------------------------


class ConversationRepository(Protocol):
    async def create(self, conversation: Conversation) -> Conversation:
        """Insert it, or return the stored one if a conversation with that id and owner already exists.

        Raises NotFound when the id belongs to another owner."""

    async def get(self, conversation_id: str, owner_id: str) -> Conversation | None:
        """With its messages, oldest first."""

    async def list_by_owner(
        self, owner_id: str, *, limit: int = 20, cursor: str | None = None, search: str | None = None
    ) -> ConversationPage:
        """Most recently active first; `cursor` is the `next_cursor` of the previous page."""

    async def update(
        self, conversation_id: str, owner_id: str, *, title: str | None = None, settings: ChatSettings | None = None
    ) -> Conversation | None: ...

    async def delete(self, conversation_id: str, owner_id: str) -> bool: ...

    async def add_message(self, message: Message) -> None:
        """Append a message to an existing conversation and mark the conversation active."""

    async def recent_messages(self, conversation_id: str, limit: int) -> list[Message]:
        """The last `limit` messages, oldest first."""

    async def set_feedback(self, message_id: str, owner_id: str, feedback: Feedback | None) -> bool:
        """Replace (or with None remove) the feedback on an assistant message of `owner_id`."""


class TraceRepository(Protocol):
    async def save(self, trace: Trace) -> None: ...

    async def get(self, trace_id: str, owner_id: str) -> Trace | None: ...


# Identity ------------------------------------------------------------------------------------------------------


class AccountDirectory(Protocol):
    """The identity provider (university SSO; here the demo account table)."""

    def authenticate(self, username: str, password: str) -> Account | None: ...

    def get(self, username: str) -> Account | None: ...


class AccessTokens(Protocol):
    """Tokens the backend gives its clients (the frontend)."""

    def issue(self, principal: Principal) -> tuple[str, int]:
        """The token and its lifetime in seconds."""

    def verify(self, token: str) -> Principal:
        """Raises Unauthenticated."""


class StudentTokenIssuer(Protocol):
    """Short-lived Student Record tokens, signed for one request and never sent to the client."""

    def issue(self, account: Account) -> str: ...


# Tools (MCP) ---------------------------------------------------------------------------------------------------


class StudentRecordGateway(Protocol):
    async def call(self, tool: str, token: str, args: dict[str, Any] | None = None) -> ToolResult:
        """Never raises: transport failures come back as an INTERNAL error result."""


class RegulationGateway(Protocol):
    async def call(self, tool: str, args: dict[str, Any]) -> ToolResult:
        """Never raises: transport failures come back as an INTERNAL error result."""


# LLM -----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatTurn:
    role: str  # user | assistant
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class ChatModel(Protocol):
    provider: str
    model: str

    async def complete(
        self,
        prompt: str,
        *,
        system: str,
        history: Sequence[ChatTurn] = (),
        max_output_tokens: int,
        json_schema: dict[str, Any] | None = None,
    ) -> Completion:
        """One call. `json_schema` asks for structured output when the provider supports it. Raises LLMError."""


class ChatModels(Protocol):
    """The LLMs this server has keys for."""

    def providers(self) -> list[str]: ...

    def default_provider(self) -> str: ...

    def create(self, provider: str | None, model: str | None) -> ChatModel | None:
        """None when that provider has no key; raises InvalidRequest for an unknown provider."""


# Streaming -----------------------------------------------------------------------------------------------------

EventSink = Callable[[AnswerEvent], Awaitable[None]]
