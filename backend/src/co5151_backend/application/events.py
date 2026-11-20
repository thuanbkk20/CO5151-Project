"""Events of one answer, in order: `step`* then `answer` or `error`. The API streams them as SSE.

No event carries a draft: the answer is only sent once the Verifier has passed it.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EventType = Literal["step", "answer", "error"]


@dataclass(frozen=True)
class AnswerEvent:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def step(name: str, **detail: Any) -> AnswerEvent:
    """`name`: plan, tool, write, verify."""
    return AnswerEvent("step", {"name": name, **detail})
