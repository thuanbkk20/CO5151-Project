"""The test conversations (docs/design/test-conversations.md): 20 conversations of 3–4 turns, graded turn by turn.

A conversation passes when every gradable turn passes. Turns carry the grading fields of a `Task`, so `scoring.score`
grades a turn exactly like a single question.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .tasks import DATA, Fact, Outcome

USE_CASES = tuple(f"UC{i}" for i in range(1, 10))


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^H[0-9]{2}-[0-9]+$")
    question: str
    expected: Outcome
    also_accept: list[Outcome] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    citations_verified: bool = False
    forbidden: list[str] = Field(default_factory=list)
    reference_answer: str = ""
    notes: str = ""
    # Starts a new conversation from this turn on (H18: after the question limit)
    new_conversation: bool = False


class PrefillTurn(BaseModel):
    """A question and answer already in the conversation before the graded turns; written to the store, no LLM."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str
    answer: str


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^H[0-9]{2}$")
    user: str = Field(min_length=1, description="Demo account; the set has no guest conversations")
    title: str
    use_cases: list[str] = Field(min_length=1)
    prefill_turns: list[PrefillTurn] = Field(default_factory=list)
    turns: list[Turn] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self):
        for turn in self.turns:
            if not turn.id.startswith(f"{self.id}-"):
                raise ValueError(f"{turn.id}: turn of another conversation than {self.id}")
            if turn.citations_verified and not turn.citations:
                raise ValueError(f"{turn.id}: citations_verified without citations")
        unknown = set(self.use_cases) - set(USE_CASES)
        if unknown:
            raise ValueError(f"{self.id}: unknown use cases {sorted(unknown)}")
        return self


def load_conversations(path: str | Path | None = None) -> list[Conversation]:
    raw = Path(path).read_text("utf-8") if path else (DATA / "conversations.json").read_text("utf-8")
    conversations = [Conversation.model_validate(c) for c in json.loads(raw)]
    ids = [c.id for c in conversations] + [t.id for c in conversations for t in c.turns]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"duplicate ids: {dup}")
    return conversations
