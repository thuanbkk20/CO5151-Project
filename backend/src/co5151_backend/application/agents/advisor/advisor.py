"""Advisor agent: collects the evidence a question needs, then writes the answer from that evidence only.

It never sees the conversation store or the API; the use case gives it the question, the history, the student's
Student Record token, the LLM of the conversation, and receives a `Gathered` and a `Draft`.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from co5151_contracts import Verdict

from ....domain.errors import LLMError
from ....domain.evidence import Action, Evidence
from ....domain.trace import Outcome, Usage
from ... import events
from ...ports import ChatModel, ChatTurn, EventSink, RegulationGateway, StudentRecordGateway
from ...tracing import DISCARD, SpanRecorder
from . import prompts
from .memory import stated_preferences
from .planner import Planner
from .tools import REGULATION_TOOL, STUDENT_TOOLS, RegulationSearch, StudentTools

logger = logging.getLogger(__name__)

MAX_STEPS = 5
ANSWER_MAX_OUTPUT_TOKENS = 1024


@dataclass
class Gathered:
    """What the collection loop found. `final_text` is set when it ended without an answer to write."""

    evidence: Evidence = field(default_factory=Evidence)
    steps: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    llm_errors: list[str] = field(default_factory=list)
    final_text: str | None = None
    final_outcome: Outcome | None = None

    @property
    def citations(self) -> list[str]:
        return [doc.id for doc in self.evidence.regulations]


@dataclass(frozen=True)
class Draft:
    text: str
    outcome: Outcome | None  # None: written by the LLM
    usage: Usage = field(default_factory=Usage)
    llm_error: str | None = None


async def _no_events(_event) -> None:
    return None


class Advisor:
    def __init__(self, student: StudentRecordGateway, regulations: RegulationGateway):
        self._student = StudentTools(student)
        self._regulations = RegulationSearch(regulations)

    async def gather(
        self,
        question: str,
        *,
        token: str | None,
        planner: Planner,
        emit: EventSink = _no_events,
        spans: SpanRecorder = DISCARD,
    ) -> Gathered:
        g = Gathered()
        for _ in range(MAX_STEPS):
            with spans.span("planner", planner.describe(), _planner_input(question, g.evidence, token)) as span:
                decision = await planner.next_action(question, g.evidence, logged_in=token is not None)
                span.output = {"action": decision.action.value, "by": decision.by, "error": decision.error}
                span.usage = Usage(decision.input_tokens, decision.output_tokens)
            g.usage += span.usage
            if decision.error:
                g.llm_errors.append(f"planner: {decision.error}")
            action = decision.action
            g.steps.append(action.value)
            await emit(events.step("plan", action=action.value, by=decision.by))

            if action is Action.REFUSE:
                return self._end(g, prompts.REFUSAL_OTHER_STUDENT, Outcome.REFUSE)
            if action is Action.CLARIFY:
                return self._end(g, prompts.CLARIFY, Outcome.CLARIFY)
            if action is Action.RESPOND:
                return g
            if action in STUDENT_TOOLS:
                g.tool_calls.append(STUDENT_TOOLS[action])
                await emit(events.step("tool", tool=STUDENT_TOOLS[action]))
                facts = await self._student.read(action, token, spans=spans)
                if facts.fields is None:
                    return self._end(g, facts.error, Outcome.REFUSE)
                g.evidence = g.evidence.model_copy(update=facts.fields)
                continue
            # Action.REGULATIONS
            g.tool_calls.append(REGULATION_TOOL)
            await emit(events.step("tool", tool=REGULATION_TOOL))
            docs = await self._regulations.search(question, spans=spans)
            if not docs:
                return self._end(g, prompts.NO_REGULATION, Outcome.REFUSE)
            g.evidence = g.evidence.model_copy(update={"regulations_checked": True, "regulations": docs})
        return self._end(g, prompts.INCOMPLETE, Outcome.REFUSE)

    @staticmethod
    def _end(g: Gathered, text: str, outcome: Outcome) -> Gathered:
        g.final_text, g.final_outcome = text, outcome
        return g

    async def write(
        self,
        question: str,
        evidence: Evidence,
        *,
        model: ChatModel | None,
        history: Sequence[ChatTurn],
        token: str | None,
        revise: tuple[str, Verdict] | None = None,
        spans: SpanRecorder = DISCARD,
    ) -> Draft | None:
        """The answer. Without a usable LLM: the template answer, or None for a rewrite (nothing can rewrite it)."""
        name = "rewrite" if revise else "draft"
        with spans.span("writer", name, _writer_input(question, evidence, revise)) as span:
            draft = await self._write(question, evidence, model=model, history=history, token=token, revise=revise)
            span.output = _writer_output(draft, model)
            if draft is not None:
                span.usage, span.error = draft.usage, draft.llm_error
        return draft

    async def _write(
        self,
        question: str,
        evidence: Evidence,
        *,
        model: ChatModel | None,
        history: Sequence[ChatTurn],
        token: str | None,
        revise: tuple[str, Verdict] | None,
    ) -> Draft | None:
        preferences = stated_preferences([t.content for t in history if t.role == "user"] + [question])
        prompt = prompts.answer_prompt(question, evidence, logged_in=token is not None, preferences=preferences)
        if revise is not None:
            prompt += prompts.revision_request(*revise)
        error = "no LLM key for this provider" if model is None else None
        if model is not None:
            try:
                done = await model.complete(
                    prompt, system=prompts.SYSTEM_PROMPT, history=history, max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS
                )
                usage = Usage(done.input_tokens, done.output_tokens)
                return Draft(prompts.sanitize(done.text, token), None, usage)
            except LLMError as e:
                error = str(e)
                logger.warning("answer LLM call failed, falling back: %s", e)
        if revise is not None:
            return None
        return Draft(prompts.template_answer(question, evidence), Outcome.ANSWER, llm_error=error)


def _planner_input(question: str, evidence: Evidence, token: str | None) -> dict:
    return {
        "question": question,
        "logged_in": token is not None,
        "collected": {
            "academic_summary": evidence.has_academic_summary,
            "warnings": evidence.has_warnings,
            "regulations": evidence.has_regulations,
        },  # fmt: skip
    }


def _writer_input(question: str, evidence: Evidence, revise: tuple[str, Verdict] | None) -> dict:
    """What the answer is written from; the system prompt is left out (it carries the canary)."""
    data = {
        "question": question,
        "student_facts": evidence.student_facts(),
        "regulations": [{"id": r.id, "title": r.title} for r in evidence.regulations],
    }
    if revise is not None:
        data["previous_draft"] = revise[0]
        data["verifier_issues"] = [{"code": i.code.value, "message": i.message} for i in revise[1].issues]
    return data


def _writer_output(draft: Draft | None, model: ChatModel | None) -> dict:
    if draft is None:
        return {"text": None, "by": "none", "note": "không có LLM để viết lại"}
    by = f"{model.provider}/{model.model}" if draft.outcome is None and model else "template"
    return {"text": draft.text, "by": by}
