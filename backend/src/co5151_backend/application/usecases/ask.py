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

from ...domain.conversation import ChatSettings, Conversation, Message, MessageRole, title_from, utcnow
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
from ..tracing import SpanRecorder

logger = logging.getLogger(__name__)

# The Verifier checks a draft at most this many times, so the Advisor rewrites at most once before refusing.
MAX_VERIFIER_ROUNDS = 2
MAX_QUESTION_CHARS = 4000
# From this many questions left, the answer says how many remain (questions 8, 9, 10 of 10).
WARN_QUESTIONS_LEFT = 2


@dataclass(frozen=True)
class Answer:
    message: Message
    trace: Trace
    questions_left: int


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
        max_questions: int = 10,
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
        self._max_questions = max_questions

    def questions_left(self, conversation: Conversation) -> int:
        asked = sum(m.role is MessageRole.USER for m in conversation.messages)
        return max(0, self._max_questions - asked)

    def _offered(self, settings: ChatSettings) -> tuple[str | None, str | None]:
        """The conversation's provider and model; a model no longer offered falls back to the provider's default."""
        offered = self._models.models(settings.provider or self._models.default_provider())
        return settings.provider, settings.model if settings.model in offered else None

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
        left = self.questions_left(conversation)  # before this question
        asked = Message(str(uuid.uuid4()), conversation_id, MessageRole.USER, question, utcnow())
        await self._chats.add_message(asked)
        if conversation.title is None:
            await self._chats.update(conversation_id, principal.user_id, title=title_from(question))

        trace_id, start = new_trace_id(), time.perf_counter()
        if left == 0:  # UC9: the fixed reply R1, no planner and no LLM call
            return await self._limit_reached(conversation_id, asked, trace_id, start)
        left -= 1
        spans = SpanRecorder(secrets=[prompts.CANARY])
        model = self._models.create(*self._offered(conversation.settings))
        llm = f"{model.provider}/{model.model}" if model else None
        try:
            turn = await self._answer(question, history, model, self._student_token(principal), emit, spans)
        except Exception as e:
            logger.exception("trace=%s failed", trace_id)
            failed = Trace(trace_id=trace_id, conversation_id=conversation_id, user_message_id=asked.id,
                           latency_ms=_ms(start), llm=llm, error=f"{type(e).__name__}: {e}",
                           created_at=utcnow())  # fmt: skip
            await self._traces.save(failed, spans.spans)
            raise AnswerFailed(trace_id) from e

        text = turn.text
        if left <= WARN_QUESTIONS_LEFT:  # a fixed line after the Verifier, not written by the LLM
            text = f"{text}\n\n{prompts.questions_left_note(left)}"
        answer = Message(str(uuid.uuid4()), conversation_id, MessageRole.ASSISTANT, text, utcnow(), trace_id)
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
        await self._traces.save(trace, spans.spans)
        logger.info("trace=%s outcome=%s tools=%s verifier_rounds=%s tokens=%s ms=%s", trace_id,
                    trace.outcome.value if trace.outcome else "llm", ",".join(trace.tool_calls) or "-",
                    trace.verifier_rounds, trace.usage.total, trace.latency_ms)  # fmt: skip
        return Answer(answer, trace, left)

    async def _limit_reached(self, conversation_id: str, asked: Message, trace_id: str, start: float) -> Answer:
        text = prompts.limit_reached(self._max_questions)
        answer = Message(str(uuid.uuid4()), conversation_id, MessageRole.ASSISTANT, text, utcnow(), trace_id)
        await self._chats.add_message(answer)
        trace = Trace(trace_id=trace_id, conversation_id=conversation_id, user_message_id=asked.id,
                      answer_message_id=answer.id, outcome=Outcome.LIMIT, steps=["LIMIT"], latency_ms=_ms(start),
                      created_at=answer.created_at)  # fmt: skip
        await self._traces.save(trace, [])
        logger.info("trace=%s outcome=limit", trace_id)
        return Answer(answer, trace, 0)

    async def _answer(
        self,
        question: str,
        history: list[ChatTurn],
        model: ChatModel | None,
        token: str | None,
        emit: EventSink,
        spans: SpanRecorder,
    ) -> "_Turn":
        gathered = await self._advisor.gather(question, token=token, planner=Planner(self._router_for(model)),
                                              emit=emit, spans=spans)  # fmt: skip
        turn = _Turn(gathered.steps, gathered.tool_calls, gathered.citations, gathered.usage, list(gathered.llm_errors))
        if gathered.final_text is not None:  # refusal or clarification of the planner: nothing to verify
            turn.text, turn.outcome = gathered.final_text, gathered.final_outcome
            return turn

        evidence = gathered.evidence
        await emit(events.step("write"))
        draft = await self._advisor.write(question, evidence, model=model, history=history, token=token, spans=spans)
        turn.add_draft(draft)
        verifier = self._verifier_for(model)
        if verifier is None:
            return turn

        turn.verifier_rounds = 0
        while True:
            request = _verification_request(question, turn.text, evidence)
            with spans.span(
                "verifier", f"round {turn.verifier_rounds + 1}", _verifier_input(verifier, request)
            ) as span:
                verdict = await verifier.verify(request)
                span.output = verdict.model_dump(mode="json", include={"status", "issues"})
                span.usage = Usage(verdict.input_tokens, verdict.output_tokens)
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
                                                    revise=(turn.text, verdict), spans=spans)  # fmt: skip
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


def _verifier_input(verifier: ComplianceVerifier, request: VerificationRequest) -> dict:
    describe = getattr(verifier, "describe", None)
    return {
        "checks": describe() if callable(describe) else None,
        "draft": request.draft,
        "student_facts": request.student_facts,
        "regulations": [r.id for r in request.regulations],
    }


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)
