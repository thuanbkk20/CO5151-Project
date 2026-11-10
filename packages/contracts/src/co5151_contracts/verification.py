"""Data exchanged between the Advisor and the Compliance Verifier.

The Advisor sends its draft answer together with the evidence the draft was written from; the Verifier replies
with a verdict. Neither side imports the other: both depend only on these models.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

FactValue = bool | int | float | str | None


class VerdictStatus(str, Enum):
    PASS = "pass"  # the draft may be sent as is
    REVISE = "revise"  # fixable: the Advisor rewrites the draft using `issues`
    REFUSE = "refuse"  # the evidence cannot support an answer: strict refusal


class IssueCode(str, Enum):
    UNSUPPORTED_CITATION = "UNSUPPORTED_CITATION"  # cites a provision that is not in `regulations`
    FACT_MISMATCH = "FACT_MISMATCH"  # states a student fact that differs from `student_facts`
    UNGROUNDED_CLAIM = "UNGROUNDED_CLAIM"  # a conclusion the evidence does not support
    MISSING_EVIDENCE = "MISSING_EVIDENCE"  # nothing was retrieved that could support the conclusion
    LEAK = "LEAK"  # a secret or another person's data appears in the draft


class RegulationExcerpt(BaseModel):
    """One retrieved provision, as the Advisor showed it to the LLM."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str = ""
    content: str


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str
    draft: str
    student_facts: dict[str, FactValue] = Field(default_factory=dict)
    regulations: list[RegulationExcerpt] = Field(default_factory=list)


class VerificationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: IssueCode
    message: str


class Verdict(BaseModel):
    """`pass` carries no issues; `revise` and `refuse` carry at least one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: VerdictStatus
    issues: list[VerificationIssue] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    @model_validator(mode="after")
    def _issues_match_status(self):
        if self.status is VerdictStatus.PASS and self.issues:
            raise ValueError("a passing verdict must not carry issues")
        if self.status is not VerdictStatus.PASS and not self.issues:
            raise ValueError("a revise or refuse verdict must say why")
        return self
