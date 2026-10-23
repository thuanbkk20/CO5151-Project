"""The interface the harness uses to drive any system under test (Advisor, baselines, ...).

A system plugs in by exposing a factory `make_agent(seed: int) -> Agent`; the CLI loads it with
`--agent package.module:make_agent`. The harness owns login: it hands the agent the session token of
the task's demo account, exactly like the host app would, and never puts it in the question.
"""

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
    outcome: Outcome | None = Field(None, description="Agent tự khai báo; null thì harness tự phân loại từ text.")
    citations: list[str] = Field(default_factory=list, description="Ví dụ ['QC2023 Điều 12 Khoản 2'].")
    tool_calls: list[str] = Field(default_factory=list, description="Tên các tool đã gọi, theo thứ tự.")
    usage: Usage = Field(default_factory=Usage)
    verifier_rounds: int | None = Field(None, description="Số vòng Verifier yêu cầu tìm lại (nếu có Verifier).")


@runtime_checkable
class Agent(Protocol):
    name: str

    def answer(self, question: str, *, session_token: str | None, history: list[dict[str, str]]) -> AgentResponse:
        """Answer one question for the logged-in user (`session_token` is None when nobody is logged in)."""
        ...
