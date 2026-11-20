"""Evidence the Advisor collects before it answers, and the actions that collect it."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Action(str, Enum):
    SUMMARY = "SUMMARY"  # academic summary from Student Record
    WARNINGS = "WARNINGS"  # academic warnings from Student Record
    REGULATIONS = "REGULATIONS"  # regulation search
    CLARIFY = "CLARIFY"
    REFUSE = "REFUSE"
    RESPOND = "RESPOND"


class Regulation(BaseModel):
    """One retrieved provision, as shown to the LLM and to the Verifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    content: str
    ctdt: str | None = None


SUMMARY_FACTS = (
    "ctdt",
    "program_credits",
    "credits_earned",
    "remaining_credits",
    "cgpa",
    "capstone_project_passed",
    "toeic",
    "english_cert",
    "gdtc_completed",
    "gdqp_completed",
)
WARNING_FACTS = ("currently_warned", "consecutive_warnings")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ctdt: str | None = None
    program_credits: int | None = None
    credits_earned: int | None = None
    remaining_credits: int | None = None
    cgpa: float | None = None
    capstone_project_passed: bool | None = None
    toeic: int | None = None
    english_cert: str | None = None
    gdtc_completed: bool | None = None
    gdqp_completed: bool | None = None
    currently_warned: bool | None = None
    consecutive_warnings: int | None = None
    warnings_checked: bool = False
    regulations_checked: bool = False
    regulations: list[Regulation] = Field(default_factory=list)

    @property
    def has_academic_summary(self) -> bool:
        return self.credits_earned is not None

    @property
    def has_warnings(self) -> bool:
        return self.warnings_checked

    @property
    def has_regulations(self) -> bool:
        return self.regulations_checked

    def collected(self, action: Action) -> bool:
        """Whether the evidence `action` collects is already here."""
        return {
            Action.SUMMARY: self.has_academic_summary,
            Action.WARNINGS: self.has_warnings,
            Action.REGULATIONS: self.has_regulations,
        }.get(action, False)

    def student_facts(self) -> dict:
        """The record facts collected so far, by name (what the Verifier checks the draft against)."""
        names = (SUMMARY_FACTS if self.has_academic_summary else ()) + (WARNING_FACTS if self.has_warnings else ())
        return self.model_dump(include=set(names)) if names else {}
