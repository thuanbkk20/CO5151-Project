"""What one answer did and cost: kept per answer, shown in the UI and used by the evaluation."""

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


def new_trace_id() -> str:
    """32 lowercase hex characters, the trace-id format of W3C trace context (also used by OpenTelemetry)."""
    return os.urandom(16).hex()


class Outcome(str, Enum):
    ANSWER = "answer"
    CLARIFY = "clarify"
    REFUSE = "refuse"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


@dataclass(frozen=True)
class Trace:
    """`outcome` is None when the LLM wrote the answer: what it amounts to is read from the text."""

    trace_id: str
    conversation_id: str
    user_message_id: str | None = None
    answer_message_id: str | None = None
    outcome: Outcome | None = None
    steps: list[str] = field(default_factory=list)  # planner actions, then VERIFY_<status>
    tool_calls: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    verifier_rounds: int | None = None
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    llm: str | None = None  # provider/model
    llm_error: str | None = None  # an LLM call failed and a fallback was used
    error: str | None = None  # the answer could not be produced
    created_at: datetime | None = None
