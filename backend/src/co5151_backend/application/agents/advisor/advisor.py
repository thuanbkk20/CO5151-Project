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
        self, question: str, *, token: str | None, planner: Planner, emit: EventSink = _no_events
    ) -> Gathered:
        g = Gathered()
        for _ in range(MAX_STEPS):
            decision = await planner.next_action(question, g.evidence, logged_in=token is not None)
            g.usage += Usage(decision.input_tokens, decision.output_tokens)
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
                facts = await self._student.read(action, token)
                if facts.fields is None:
                    return self._end(g, facts.error, Outcome.REFUSE)
                g.evidence = g.evidence.model_copy(update=facts.fields)
                continue
            # Action.REGULATIONS
            g.tool_calls.append(REGULATION_TOOL)
            await emit(events.step("tool", tool=REGULATION_TOOL))
            docs = await self._regulations.search(question)
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
    ) -> Draft | None:
        """The answer. Without a usable LLM: the template answer, or None for a rewrite (nothing can rewrite it)."""
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
