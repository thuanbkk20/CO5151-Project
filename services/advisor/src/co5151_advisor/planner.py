import re
import unicodedata
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Action(str, Enum):
    SUMMARY = "SUMMARY"
    WARNINGS = "WARNINGS"
    REGULATIONS = "REGULATIONS"
    CLARIFY = "CLARIFY"
    REFUSE = "REFUSE"
    RESPOND = "RESPOND"


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Action
    reason: str | None = None


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ctdt: str | None = None
    program_credits: int | None = None
    credits_earned: int | None = None
    remaining_credits: int | None = None
    cgpa: float | None = None
    capstone_project_passed: bool | None = None
    gdtc_completed: bool | None = None
    gdqp_completed: bool | None = None
    currently_warned: bool | None = None
    consecutive_warnings: int | None = None
    warnings_checked: bool = False
    regulations_checked: bool = False
    regulations: list[str] = Field(default_factory=list)

    @property
    def has_academic_summary(self) -> bool:
        return self.credits_earned is not None

    @property
    def has_warnings(self) -> bool:
        return self.warnings_checked

    @property
    def has_regulations(self) -> bool:
        return self.regulations_checked


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().lower()


class DecisionPlanner:
    """Plans the next advisor action based on student intent and collected evidence."""

    REFUSE_PATTERNS = [
        re.compile(r"\b\d{7}\b"),
        re.compile(r"sinh\s+viên\s+khác", re.IGNORECASE),
        re.compile(r"bạn\s+khác", re.IGNORECASE),
        re.compile(r"người\s+khác", re.IGNORECASE),
    ]

    VAGUE_PATTERNS = [
        re.compile(
            r"^(tư\s+vấn(\s+giúp)?(\s+em|\s+cho\s+em)?|cần\s+tư\s+vấn|giúp\s+em(\s+với)?|xin\s+chào|hello|hi)[.!?]*$",
            re.IGNORECASE,
        ),
    ]

    WARNING_KEYWORDS = ["cảnh báo", "cảnh cáo", "buộc thôi học", "thoát cảnh báo"]
    GRADUATION_KEYWORDS = ["tốt nghiệp", "luận văn", "lvtn", "đủ điều kiện", "xét tốt nghiệp"]
    SUMMARY_KEYWORDS = ["tín chỉ", "tc", "điểm trung bình", "dtbtl", "gpa", "bảng điểm", "học kỳ"]

    def next_action(
        self,
        question: str,
        evidence: Evidence | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> Action:
        norm_q = _normalize(question)

        # Rule 1: Refuse if asking about another student
        if any(p.search(question) for p in self.REFUSE_PATTERNS):
            return Action.REFUSE

        # Rule 2: Vague questions must clarify
        if any(p.match(norm_q) for p in self.VAGUE_PATTERNS):
            return Action.CLARIFY

        # Rule 3: Warning questions select WARNINGS then RESPOND
        if any(k in norm_q for k in self.WARNING_KEYWORDS):
            if evidence is None or not evidence.has_warnings:
                return Action.WARNINGS
            return Action.RESPOND

        # Rule 4: Graduation/eligibility questions select SUMMARY -> REGULATIONS -> RESPOND
        if any(k in norm_q for k in self.GRADUATION_KEYWORDS):
            if evidence is None or not evidence.has_academic_summary:
                return Action.SUMMARY
            if not evidence.has_regulations:
                return Action.REGULATIONS
            return Action.RESPOND

        # Rule 5: Credit/GPA/condition questions select SUMMARY first, then RESPOND
        if any(k in norm_q for k in self.SUMMARY_KEYWORDS):
            if evidence is None or not evidence.has_academic_summary:
                return Action.SUMMARY
            return Action.RESPOND

        # Fallback for unrecognized/vague requests
        return Action.CLARIFY


class LayaDecisionPlanner:
    """Option: Non-autoregressive System 1 decision engine using Laya (https://github.com/NandhaKishorM/laya).

    Design Rationale:
    -----------------
    Instead of relying on an autoregressive LLM (e.g., GPT/Kimi) or hardcoded regex rules for decision
    planning, Laya operates as a fast, calibrated, non-autoregressive decision engine that maps textual
    inputs directly into typed enum choices (Action) in a single forward pass (~20-40ms, < 1GB RAM).

    How Laya is used for Decision-driven RAG routing:
    ------------------------------------------------
    1. Input Context Framing:
       Construct a structured context string encoding:
       - user_query: student's question
       - evidence_state: [has_summary: bool, has_regulations: bool, has_warnings: bool]
       - privacy_flags: detected external student_id or cross-student intent

    2. Typed Action Decision (Single Forward Pass):
       choices = [Action.SUMMARY, Action.WARNINGS, Action.REGULATIONS, Action.CLARIFY, Action.REFUSE, Action.RESPOND]
       result = laya_model.predict_choice(
           text=context_string,
           choices=choices,
       )
       -> Returns predicted Action with calibrated confidence score (e.g., Action.SUMMARY: 0.94)

    3. Fast-path Guardrails:
       Laya also acts as an ultra-fast guardrail (predict_yes_no for prompt injection / leak risks).

    Note:
    -----
    This class is provided as an architectural stub / option specification and does not require installing
    `laya` in the core runtime environment until activated.
    """

    def __init__(self, model_name: str = "laya/router-v1", confidence_threshold: float = 0.75):
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self._fallback_planner = DecisionPlanner()

    def next_action(
        self,
        question: str,
        evidence: Evidence | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> Action:
        """Route to Action using Laya model if installed, otherwise fallback to deterministic rules."""
        try:
            # When laya is installed:
            # from laya import Laya
            # model = Laya(self.model_name)
            # return self._predict_with_laya(model, question, evidence, history)
            pass
        except ImportError:
            pass

        return self._fallback_planner.next_action(question, evidence, history)
