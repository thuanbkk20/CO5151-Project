"""What the store returns: plain dataclasses, independent of SQLAlchemy and of the chat UI."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class User:
    id: str
    identifier: str
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    """`type` follows the chat UI: user_message, assistant_message, tool, run..."""

    id: str
    conversation_id: str
    type: str
    created_at: datetime
    name: str = ""
    input: str = ""
    output: str = ""
    parent_id: str | None = None
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    display: dict[str, Any] = field(default_factory=dict)
    start_at: datetime | None = None
    end_at: datetime | None = None
    feedback: "Feedback | None" = None


@dataclass(frozen=True)
class Feedback:
    id: str
    step_id: str
    value: int  # 1 helpful, 0 not helpful
    comment: str | None = None


@dataclass
class Conversation:
    id: str
    created_at: datetime
    updated_at: datetime
    user_id: str | None = None
    user_identifier: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)


@dataclass(frozen=True)
class Turn:
    """One answered question. `trace_id` is 32 hex characters (W3C trace-context format)."""

    trace_id: str
    conversation_id: str
    user_message_id: str | None = None
    answer_message_id: str | None = None
    outcome: str | None = None
    tool_calls: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    verifier_rounds: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    llm: str | None = None
    error: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class Page:
    conversations: list[Conversation]
    has_next: bool
