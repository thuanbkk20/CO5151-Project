from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from .tasks import Outcome


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    outcome: Outcome | None = None
    citations: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    verifier_rounds: int | None = None


@runtime_checkable
class Agent(Protocol):
    name: str

    def answer(self, question: str, *, session_token: str | None, history: list[dict[str, str]]) -> AgentResponse: ...
