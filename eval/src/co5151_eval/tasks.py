import json
from enum import Enum
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATA = resources.files("co5151_eval") / "data"


class Group(str, Enum):
    BASIC = "basic"
    PERSONAL = "personal"
    MISSING_INFO = "missing_info"
    OUT_OF_SCOPE = "out_of_scope"


class Outcome(str, Enum):
    ANSWER = "answer"
    CLARIFY = "clarify"
    REFUSE = "refuse"


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    value: str | int | float | bool
    mention: list[str]


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[A-Z]+[0-9]{2}$")
    group: Group
    question: str
    user: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)
    expected: Outcome
    also_accept: list[Outcome] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    citations_verified: bool = False
    forbidden: list[str] = Field(default_factory=list)
    reference_answer: str = ""
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self):
        if self.facts and self.user is None:
            raise ValueError(f"{self.id}: facts need a logged-in user")
        if self.citations_verified and not self.citations:
            raise ValueError(f"{self.id}: citations_verified without citations")
        return self


SUITES = {"tasks": "tasks.json", "injection": "prompt_injection.json"}


def load_tasks(path: str | Path | None = None, suite: str = "tasks") -> list[Task]:
    raw = Path(path).read_text("utf-8") if path else (DATA / SUITES[suite]).read_text("utf-8")
    tasks = [Task.model_validate(t) for t in json.loads(raw)]
    ids = [t.id for t in tasks]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"duplicate task ids: {sorted(dup)}")
    return tasks
