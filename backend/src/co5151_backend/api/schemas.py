"""Request and response bodies of the API, and their mapping from the domain objects."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..application.usecases.ask import Answer
from ..application.usecases.auth import Session
from ..domain.conversation import ChatSettings, Conversation, ConversationPage, Message
from ..domain.principal import Principal
from ..domain.trace import Trace


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(_In):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(default="", max_length=256)


class UserOut(BaseModel):
    id: str
    role: str
    display_name: str

    @classmethod
    def of(cls, p: Principal) -> "UserOut":
        return cls(id=p.user_id, role=p.role.value, display_name=p.display_name)


class SessionOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut

    @classmethod
    def of(cls, s: Session) -> "SessionOut":
        return cls(access_token=s.access_token, expires_in=s.expires_in, user=UserOut.of(s.principal))


class LLMChoicesOut(BaseModel):
    providers: list[str]
    default: str


class SettingsBody(BaseModel):
    provider: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=100)

    def domain(self) -> ChatSettings:
        return ChatSettings(self.provider, self.model)


class ConversationIn(_In):
    id: str | None = Field(default=None, description="UUID chosen by the client; omit to let the server pick one")
    title: str | None = Field(default=None, max_length=255)
    settings: SettingsBody | None = None


class ConversationPatch(_In):
    title: str | None = Field(default=None, max_length=255)
    settings: SettingsBody | None = None


class FeedbackOut(BaseModel):
    value: int
    comment: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    trace_id: str | None = None
    feedback: FeedbackOut | None = None

    @classmethod
    def of(cls, m: Message) -> "MessageOut":
        feedback = FeedbackOut(value=m.feedback.value, comment=m.feedback.comment) if m.feedback else None
        return cls(id=m.id, role=m.role.value, content=m.content, created_at=m.created_at, trace_id=m.trace_id,
                   feedback=feedback)  # fmt: skip


class ConversationOut(BaseModel):
    id: str
    title: str | None
    settings: SettingsBody
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, c: Conversation) -> "ConversationOut":
        return cls(id=c.id, title=c.title, settings=SettingsBody(provider=c.settings.provider, model=c.settings.model),
                   created_at=c.created_at, updated_at=c.updated_at)  # fmt: skip


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]

    @classmethod
    def of(cls, c: Conversation) -> "ConversationDetailOut":
        return cls(**ConversationOut.of(c).model_dump(), messages=[MessageOut.of(m) for m in c.messages])


class ConversationPageOut(BaseModel):
    items: list[ConversationOut]
    next_cursor: str | None

    @classmethod
    def of(cls, p: ConversationPage) -> "ConversationPageOut":
        return cls(items=[ConversationOut.of(c) for c in p.items], next_cursor=p.next_cursor)


class MessageIn(_In):
    content: str = Field(min_length=1, max_length=4000)


class TraceOut(BaseModel):
    trace_id: str
    conversation_id: str
    user_message_id: str | None
    answer_message_id: str | None
    outcome: str | None = Field(description="answer | clarify | refuse; null when the LLM wrote the answer")
    steps: list[str]
    tool_calls: list[str]
    citations: list[str]
    verifier_rounds: int | None
    input_tokens: int
    output_tokens: int
    latency_ms: int
    llm: str | None
    llm_error: str | None
    error: str | None

    @classmethod
    def of(cls, t: Trace) -> "TraceOut":
        return cls(trace_id=t.trace_id, conversation_id=t.conversation_id, user_message_id=t.user_message_id,
                   answer_message_id=t.answer_message_id, outcome=t.outcome.value if t.outcome else None,
                   steps=t.steps, tool_calls=t.tool_calls, citations=t.citations, verifier_rounds=t.verifier_rounds,
                   input_tokens=t.usage.input_tokens, output_tokens=t.usage.output_tokens, latency_ms=t.latency_ms,
                   llm=t.llm, llm_error=t.llm_error, error=t.error)  # fmt: skip


class AnswerOut(BaseModel):
    message: MessageOut
    trace: TraceOut

    @classmethod
    def of(cls, a: Answer) -> "AnswerOut":
        return cls(message=MessageOut.of(a.message), trace=TraceOut.of(a.trace))


class FeedbackIn(_In):
    value: Literal[0, 1]
    comment: str | None = Field(default=None, max_length=2000)


class ErrorOut(BaseModel):
    detail: str
    trace_id: str | None = None
