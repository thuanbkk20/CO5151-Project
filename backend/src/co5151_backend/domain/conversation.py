"""Conversations of one user and their messages."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

MAX_TITLE = 255


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class Feedback:
    value: int  # 1 helpful, 0 not helpful
    comment: str | None = None


@dataclass(frozen=True)
class ChatSettings:
    """LLM chosen for a conversation; None means the server default."""

    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class Message:
    id: str
    conversation_id: str
    role: MessageRole
    content: str
    created_at: datetime
    trace_id: str | None = None  # the answer's trace (assistant messages)
    feedback: Feedback | None = None


@dataclass(frozen=True)
class Conversation:
    id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    settings: ChatSettings = field(default_factory=ChatSettings)
    messages: tuple[Message, ...] = ()


@dataclass(frozen=True)
class ConversationPage:
    items: list[Conversation]
    next_cursor: str | None = None


def title_from(question: str) -> str:
    """A conversation is named after its first question."""
    title = " ".join(question.split())
    return title if len(title) <= MAX_TITLE else title[: MAX_TITLE - 1] + "…"
