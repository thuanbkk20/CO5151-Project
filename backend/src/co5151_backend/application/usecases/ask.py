"""AskQuestion: one turn of a conversation, from the question to the verified answer.

Order: save the question -> the Advisor collects evidence -> the Advisor writes a draft -> the Verifier checks it
(at most one rewrite) -> save the answer and its trace. Progress is reported through `emit` as it happens; the
answer itself is only returned once it has passed the Verifier.
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from co5151_contracts import RegulationExcerpt, VerdictStatus, VerificationRequest

from ...domain.conversation import Message, MessageRole, title_from, utcnow
from ...domain.errors import AnswerFailed, InvalidRequest, NotFound
from ...domain.evidence import Evidence
from ...domain.principal import Principal, Role
from ...domain.trace import Outcome, Trace, Usage, new_trace_id
from .. import events
from ..agents.advisor import prompts
from ..agents.advisor.advisor import Advisor, Draft
from ..agents.advisor.planner import Planner
from ..agents.verifier import ComplianceVerifier
from ..ports import (
    AccountDirectory,
    ActionRouter,
    ChatModel,
    ChatModels,
    ChatTurn,
    ConversationRepository,
    EventSink,
    StudentTokenIssuer,
    TraceRepository,
)

logger = logging.getLogger(__name__)

# The Verifier checks a draft at most this many times, so the Advisor rewrites at most once before refusing.
MAX_VERIFIER_ROUNDS = 2
MAX_QUESTION_CHARS = 4000


@dataclass(frozen=True)
class Answer:
    message: Message
    trace: Trace


async def _no_events(_event) -> None:
    return None


class AskQuestion:
    def __init__(
        self,
        *,
        chats: ConversationRepository,
        traces: TraceRepository,
        accounts: AccountDirectory,
        student_tokens: StudentTokenIssuer,
        models: ChatModels,
        advisor: Advisor,
        router_for: Callable[[ChatModel | None], ActionRouter | None],
        verifier_for: Callable[[ChatModel | None], ComplianceVerifier | None],
        history_messages: int = 10,
    ):
        self._chats = chats
        self._traces = traces
        self._accounts = accounts
        self._student_tokens = student_tokens
        self._models = models
        self._advisor = advisor
        self._router_for = router_for
        self._verifier_for = verifier_for
        self._history_messages = history_messages

    def _student_token(self, principal: Principal) -> str | None:
        """A fresh short-lived Student Record token, or None for a guest (no record to read)."""
        if principal.role is Role.GUEST:
            return None
        account = self._accounts.get(principal.user_id)
        return self._student_tokens.issue(account) if account else None

    async def execute(
        self, principal: Principal, conversation_id: str, question: str, *, emit: EventSink = _no_events
    ) -> Answer:
        question = question.strip()
        if not question or len(question) > MAX_QUESTION_CHARS:
            raise InvalidRequest(f"question must have 1 to {MAX_QUESTION_CHARS} characters")
        conversation = await self._chats.get(conversation_id, principal.user_id)
        if conversation is None:
            raise NotFound(conversation_id)
        history = [
            ChatTurn(m.role.value, m.content)
            for m in await self._chats.recent_messages(conversation_id, self._history_messages)
        ]
        asked = Message(str(uuid.uuid4()), conversation_id, MessageRole.USER, question, utcnow())
        await self._chats.add_message(asked)
        if conversation.title is None:
            await self._chats.update(conversation_id, principal.user_id, title=title_from(question))

        trace_id, start = new_trace_id(), time.perf_counter()
        model = self._models.create(conversation.settings.provider, conversation.settings.model)
        llm = f"{model.provider}/{model.model}" if model else None
        try:
            turn = await self._answer(question, history, model, self._student_token(principal), emit)
        except Exception as e:
            logger.exception("trace=%s failed", trace_id)
            failed = Trace(trace_id=trace_id, conversation_id=conversation_id, user_message_id=asked.id,
                           latency_ms=_ms(start), llm=llm, error=f"{type(e).__name__}: {e}")  # fmt: skip
            await self._traces.save(failed)
            raise AnswerFailed(trace_id) from e

        answer = Message(str(uuid.uuid4()), conversation_id, MessageRole.ASSISTANT, turn.text, utcnow(), trace_id)
        await self._chats.add_message(answer)
        trace = Trace(
            trace_id=trace_id,
            conversation_id=conversation_id,
            user_message_id=asked.id,
            answer_message_id=answer.id,
            outcome=turn.outcome,
            steps=turn.steps,
            tool_calls=turn.tool_calls,
            citations=turn.citations,
            verifier_rounds=turn.verifier_rounds,
            usage=turn.usage,
            latency_ms=_ms(start),
            llm=llm,
            llm_error="; ".join(turn.llm_errors) or None,
            created_at=answer.created_at,
        )
        await self._traces.save(trace)
        logger.info("trace=%s outcome=%s tools=%s verifier_rounds=%s tokens=%s ms=%s", trace_id,
                    trace.outcome.value if trace.outcome else "llm", ",".join(trace.tool_calls) or "-",
                    trace.verifier_rounds, trace.usage.total, trace.latency_ms)  # fmt: skip
        return Answer(answer, trace)

    async def _answer(
        self, question: str, history: list[ChatTurn], model: ChatModel | None, token: str | None, emit: EventSink
    ) -> "_Turn":
        gathered = await self._advisor.gather(question, token=token, planner=Planner(self._router_for(model)),
                                              emit=emit)  # fmt: skip
        turn = _Turn(gathered.steps, gathered.tool_calls, gathered.citations, gathered.usage, list(gathered.llm_errors))
        if gathered.final_text is not None:  # refusal or clarification of the planner: nothing to verify
            turn.text, turn.outcome = gathered.final_text, gathered.final_outcome
            return turn

        evidence = gathered.evidence
        await emit(events.step("write"))
        draft = await self._advisor.write(question, evidence, model=model, history=history, token=token)
        turn.add_draft(draft)
        verifier = self._verifier_for(model)
        if verifier is None:
            return turn

        turn.verifier_rounds = 0
        while True:
            verdict = await verifier.verify(_verification_request(question, turn.text, evidence))
            turn.verifier_rounds += 1
            turn.usage += Usage(verdict.input_tokens, verdict.output_tokens)
            turn.steps.append(f"VERIFY_{verdict.status.name}")
            await emit(events.step("verify", status=verdict.status.value, round=turn.verifier_rounds))
            if verdict.status is VerdictStatus.PASS:
                return turn
            rewrite = None
            if verdict.status is VerdictStatus.REVISE and turn.verifier_rounds < MAX_VERIFIER_ROUNDS:
                await emit(events.step("write", revision=True))
                rewrite = await self._advisor.write(question, evidence, model=model, history=history, token=token,
                                                    revise=(turn.text, verdict))  # fmt: skip
            if rewrite is None:
                turn.text, turn.outcome = prompts.refusal(verdict), Outcome.REFUSE
                return turn
            turn.add_draft(rewrite)


@dataclass
class _Turn:
    steps: list[str]
    tool_calls: list[str]
    citations: list[str]
    usage: Usage
    llm_errors: list[str]
    text: str = ""
    outcome: Outcome | None = None
    verifier_rounds: int | None = None

    def add_draft(self, draft: Draft) -> None:
        self.text, self.outcome = draft.text, draft.outcome
        self.usage += draft.usage
        if draft.llm_error:
            self.llm_errors.append(f"answer: {draft.llm_error}")


def _verification_request(question: str, draft: str, evidence: Evidence) -> VerificationRequest:
    """Exactly the evidence the draft was written from; no token, no student id, no chat history."""
    excerpts = {d.id: RegulationExcerpt(id=d.id, title=d.title, content=d.content) for d in evidence.regulations}
    return VerificationRequest(
        question=question, draft=draft, student_facts=evidence.student_facts(), regulations=list(excerpts.values())
    )


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)
