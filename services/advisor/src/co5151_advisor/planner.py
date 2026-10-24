import json
import logging
import os
import re
import unicodedata
import urllib.error
import urllib.request
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

DEFAULT_LAYA_SERVER_URL = "http://127.0.0.1:8000/v1/systemone"


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
    """Non-autoregressive System 1 decision engine using Laya (https://github.com/NandhaKishorM/laya).

    Design Rationale:
    -----------------
    Instead of relying on an autoregressive LLM (e.g., GPT/Kimi) or hardcoded regex rules for decision
    planning, Laya operates as a fast, calibrated, non-autoregressive decision engine that maps textual
    inputs directly into typed enum choices (Action) in a single forward pass (~20-40ms, < 1GB RAM).

    How Laya is used for Decision-driven RAG routing:
    ------------------------------------------------
    1. Input Context Framing:
       Construct a structured context string/dict encoding:
       - user_query: student's question
       - evidence_state: [has_summary: bool, has_regulations: bool, has_warnings: bool]
       - privacy_flags: detected external student_id or cross-student intent

    2. Typed Action Decision (Single Forward Pass):
       Sends POST request to Laya /v1/systemone Jev API endpoint.
       Laya evaluates typed choices over Action enum and returns the selected action with confidence.

    3. Fast-path Guardrails & Fallback:
       - Instantly enforces privacy guardrails on cross-student requests.
       - Gracefully falls back to deterministic rules if Laya server is unreachable.
    """

    def __init__(
        self,
        server_url: str | None = None,
        timeout: float = 1.0,
        fallback_planner: DecisionPlanner | None = None,
    ):
        self.server_url = server_url or os.environ.get("LAYA_SERVER_URL") or DEFAULT_LAYA_SERVER_URL
        self.timeout = timeout
        self._fallback_planner = fallback_planner or DecisionPlanner()

    def next_action(
        self,
        question: str,
        evidence: Evidence | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> Action:
        """Route to Action using Laya System 1 model over HTTP, falling back to deterministic rules."""
        # Fast-path Guardrail: refuse cross-student queries immediately
        if any(p.search(question) for p in self._fallback_planner.REFUSE_PATTERNS):
            return Action.REFUSE

        # Sequential state transitions:
        norm_q = _normalize(question)
        if any(k in norm_q for k in self._fallback_planner.GRADUATION_KEYWORDS):
            if evidence and evidence.has_academic_summary and not evidence.has_regulations:
                return Action.REGULATIONS
            if evidence and evidence.has_regulations:
                return Action.RESPOND

        if any(k in norm_q for k in self._fallback_planner.WARNING_KEYWORDS):
            if evidence and evidence.has_warnings:
                return Action.RESPOND

        if any(k in norm_q for k in self._fallback_planner.SUMMARY_KEYWORDS):
            if evidence and evidence.has_academic_summary:
                return Action.RESPOND

        # Call Laya System 1 decision engine over HTTP
        predicted_action = self._call_laya_api(question, evidence)
        if predicted_action is not None:
            return predicted_action

        return self._fallback_planner.next_action(question, evidence, history)

    def _call_laya_api(self, question: str, evidence: Evidence | None = None) -> Action | None:
        state_data = {
            "body": question,
            "has_summary": bool(evidence and evidence.has_academic_summary),
            "has_regulations": bool(evidence and evidence.has_regulations),
            "has_warnings": bool(evidence and evidence.has_warnings),
        }
        payload = {
            "state": state_data,
            "questions": {
                "action": {
                    "type": "choice",
                    "instructions": "Determine the next action for student academic advising",
                    "criteria": {
                        "SUMMARY": "query academic summary, credits earned, gpa",
                        "WARNINGS": "academic warnings, probation",
                        "REGULATIONS": "search training regulations",
                        "CLARIFY": "vague questions needing clarification",
                        "REFUSE": "asking about other students or disallowed requests",
                        "RESPOND": "synthesize final answer",
                    },
                }
            },
        }

        try:
            req = urllib.request.Request(
                self.server_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    choice = data.get("answers", {}).get("action", {}).get("choice")
                    if choice and choice in Action.__members__:
                        return Action[choice]
        except Exception as e:
            logger.debug("Laya decision call failed (falling back): %s", e)
            return None

        return None
