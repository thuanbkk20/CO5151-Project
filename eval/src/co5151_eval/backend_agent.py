"""The backend's answer pipeline as an evaluation agent: the AskQuestion use case, called in-process.

This module is a composition root for the evaluation. It builds the backend container with the same use cases,
agents, planner, Verifier and LLM providers as the API, and swaps only the I/O adapters: an in-memory chat store,
and gateways that call the Student Record and Regulation services as Python objects instead of over MCP HTTP (no
server to start, no network latency in the measurements). Configuration comes from the same environment variables
as `co5151-api` (`LLM_PROVIDER`, `ADVISOR_PLANNER_MODE`, `ADVISOR_VERIFIER`, ...).
"""

import asyncio
import dataclasses
import os
import uuid
from functools import cache
from pathlib import Path
from typing import Any

import regulation_server
from co5151_backend.container import Adapters, Container, build_container
from co5151_backend.domain.conversation import Message, MessageRole, utcnow
from co5151_backend.domain.principal import Principal, Role
from co5151_backend.domain.trace import Span, Trace
from co5151_backend.infrastructure.config import Settings
from co5151_backend.infrastructure.identity import DemoAccountDirectory
from co5151_backend.infrastructure.llm import ProviderChatModels
from co5151_backend.infrastructure.persistence.memory import InMemoryChatRepository, InMemoryTraceRepository
from co5151_contracts import ToolResult
from co5151_contracts.security import AuthError
from regulation_server.regulation_service_v2 import RegulationServiceV2

from .agent import AgentResponse, RoleUsage, Usage
from .gold import RecordOracle
from .tasks import Outcome

REGULATION_BASE = Path(regulation_server.__file__).resolve().parents[2]
TRUE_VALUES = {"1", "true", "yes", "on"}
GUEST = Principal(user_id="eval-guest", role=Role.GUEST, display_name="Khách")


class InProcessStudentRecord:
    """StudentRecordGateway over the Student Record service object (same checks as student-mcp, no HTTP)."""

    def __init__(self, service: Any):
        self._service = service

    async def call(self, tool: str, token: str, args: dict[str, Any] | None = None) -> ToolResult:
        return self._service.call(tool, token, args)


class InProcessRegulations:
    def __init__(self, service: RegulationServiceV2):
        self._service = service

    async def call(self, tool: str, args: dict[str, Any]) -> ToolResult:
        res = self._service.call(tool, args)
        if res.ok and hasattr(res.data, "model_dump"):  # the MCP server sends JSON: give the agent the same shape
            return ToolResult(ok=True, data=res.data.model_dump(mode="json"))
        return res


INJECTED_ID = "QD2933-2021-CL99.9"  # looks like a provision id, so no rule singles it out


class PoisonedRegulations:
    """Regulation gateway whose search results end with a poisoned provision (indirect prompt injection, E3): the
    attacker controls a document of the corpus, not the question."""

    def __init__(self, inner: InProcessRegulations, text: str):
        self._inner = inner
        self._text = text

    async def call(self, tool: str, args: dict[str, Any]) -> ToolResult:
        res = await self._inner.call(tool, args)
        if tool != "search_regulations" or not res.ok:
            return res
        poisoned = {"id": INJECTED_ID, "evidence": {"provision_id": INJECTED_ID, "title": "Khoản 99.9",
                                                    "source_text": self._text}}  # fmt: skip
        return ToolResult(ok=True, data={**res.data, "results": [*res.data.get("results", []), poisoned]})


@cache
def _oracle() -> RecordOracle:
    return RecordOracle()


@cache
def _accounts() -> DemoAccountDirectory:
    return DemoAccountDirectory()


@cache
def _regulations() -> RegulationServiceV2:
    allow_draft = os.environ.get("REGULATION_ALLOW_DRAFT", "true").strip().lower() in TRUE_VALUES
    return RegulationServiceV2(REGULATION_BASE, allow_draft=allow_draft)


def _engine() -> str:
    """`REGULATION_ENGINE` (bm25 / graph), as on the deployment."""
    return os.environ.get("REGULATION_ENGINE", "bm25").strip().lower() or "bm25"


def regulation_service(engine: str = "bm25"):
    """The regulation service the in-process agent searches: `bm25` is the Regulation MCP of `regulation-server`,
    `graph` the one of `regulation-graph`."""
    if engine == "bm25":
        return _regulations()
    if engine == "graph":
        return _graph_regulations()
    raise ValueError(f"unknown regulation engine: {engine}")


@cache
def _graph_regulations():
    from regulation_graph.service import RegulationGraphService

    return RegulationGraphService()


def _settings(**overrides: Any) -> Settings:
    """The API's settings, with the Student Record secret of the in-process service and no chat database."""
    secret = _oracle().settings.token_secret
    return dataclasses.replace(Settings.from_env(), student_token_secret=secret, database_url=None, **overrides)


ROLE_OF_NODE = {"planner": "router", "writer": "writer", "verifier": "judge"}


def usage_by_role(trace: Trace, spans: list[Span]) -> list[RoleUsage]:
    """Tokens per role and model, from the spans of the answer (the judge may run on its own model)."""
    rows: dict[tuple[str, str], RoleUsage] = {}
    for span in spans:
        role = ROLE_OF_NODE.get(span.node)
        if role is None or not span.usage.total:
            continue
        judge = (span.input.get("checks") or {}).get("judge") if role == "judge" else None
        model = f"{judge['provider']}/{judge['model']}" if judge else (trace.llm or "unknown")
        row = rows.setdefault((role, model), RoleUsage(role=role, model=model))
        row.input_tokens += span.usage.input_tokens
        row.output_tokens += span.usage.output_tokens
    return list(rows.values())


def _response(trace: Trace, text: str, spans: list[Span] = ()) -> AgentResponse:
    return AgentResponse(
        usage_by_role=usage_by_role(trace, list(spans)),
        text=text,
        outcome=Outcome(trace.outcome.value) if trace.outcome else Outcome.ANSWER,
        citations=list(trace.citations),
        tool_calls=list(trace.tool_calls),
        usage=Usage(input_tokens=trace.usage.input_tokens, output_tokens=trace.usage.output_tokens),
        verifier_rounds=trace.verifier_rounds,
    )


class BackendAgent:
    """One evaluation session: a new conversation per answer, seeded with the task's history."""

    def __init__(self, name: str, settings: Settings, seed: int | None = None):
        self.name = name
        self._settings = settings
        self._seed = seed
        self._injected: str | None = None

    def inject_regulation(self, text: str | None) -> None:
        """Every later answer of this agent finds `text` among the regulations it searches (E3)."""
        self._injected = text

    def _regulations(self) -> InProcessRegulations | PoisonedRegulations:
        regulations = InProcessRegulations(regulation_service(_engine()))
        return PoisonedRegulations(regulations, self._injected) if self._injected else regulations

    def _container(self) -> Container:
        chats = InMemoryChatRepository()
        # The run's seed goes with every LLM call of a provider that takes one (`LLM_SEED`)
        env = {**os.environ, "LLM_SEED": str(self._seed)} if self._seed is not None else None
        adapters = Adapters(chats=chats, traces=InMemoryTraceRepository(chats),
                            accounts=_accounts(), student=InProcessStudentRecord(_oracle().service),
                            regulations=self._regulations(),
                            models=ProviderChatModels(env))  # fmt: skip
        return build_container(self._settings, adapters)

    def describe(self) -> dict[str, Any]:
        return {
            **self._container().describe(),
            "name": self.name,
            "seed": self._seed,
            "verifier_provider": self._settings.verifier_provider,
            "regulation_source": f"{_engine()} (in-process)",
        }

    @staticmethod
    def _principal(session_token: str | None) -> Principal:
        """The eval harness signs in through the Student Record service; map its session to the account."""
        if session_token is None:
            return GUEST
        try:
            claims = _oracle().service.signer.verify(session_token)
        except AuthError:
            return GUEST
        account = _accounts().get(claims.sub)
        return account.principal() if account else GUEST

    def answer(self, question: str, *, session_token: str | None, history: list[dict[str, str]]) -> AgentResponse:
        return asyncio.run(self._answer(question, session_token, history))

    async def _answer(self, question: str, session_token: str | None, history: list[dict[str, str]]):
        container = self._container()
        principal = self._principal(session_token)
        conversation = await container.conversations.start(principal, conversation_id=str(uuid.uuid4()))
        for turn in history:
            role = MessageRole.USER if turn["role"] == "user" else MessageRole.ASSISTANT
            await container.chats.add_message(Message(str(uuid.uuid4()), conversation.id, role, turn["content"],
                                                      utcnow()))  # fmt: skip
        answer = await container.ask.execute(principal, conversation.id, question)
        spans = await container.conversations.spans(principal, answer.trace.trace_id)
        return _response(answer.trace, answer.message.content, spans)


def make_agent(seed: int = 0) -> BackendAgent:
    """The Advisor with the Compliance Verifier configured by `ADVISOR_VERIFIER` (default `llm`)."""
    return BackendAgent("advisor", _settings(), seed)


def make_agent_no_verifier(seed: int = 0) -> BackendAgent:
    """Baseline of the proposal: the same Advisor as a single agent, whatever `ADVISOR_VERIFIER` says."""
    return BackendAgent("advisor-no-verifier", _settings(verifier_mode="off"), seed)


def make_agent_config(seed: int = 0, *, planner: str = "llm", verifier: str = "llm",
                      judge: str | None = None) -> BackendAgent:  # fmt: skip
    """One ablation cell (E2), whatever the environment says for these three axes:

    - `planner`: `rule` (rules only) or `llm` (rules, then the LLM router where they stop);
    - `verifier`: `off` (single agent), `rules` (free checks only) or `llm` (checks, then the LLM judge);
    - `judge`: None for a judge on the answer's own model, or `provider/model` for a separate judge.

    The fourth axis, retrieval, is `REGULATION_ENGINE` (bm25 / graph), measured without LLM by `co5151-eval retrieval`.
    """
    provider, _, model = (judge or "").partition("/")
    if judge and not model:
        raise ValueError(f"judge must look like provider/model, got {judge!r}")
    settings = _settings(planner_mode=planner, verifier_mode=verifier, verifier_provider=provider or None,
                         verifier_model=model or None)  # fmt: skip
    return BackendAgent(f"advisor[planner={planner},verifier={verifier},judge={judge or 'same'}]", settings, seed)


# Named cells for `co5151-eval run --agent co5151_eval.backend_agent:<name>`; the full system is `make_agent`
# (judge from VERIFIER_LLM_*), the single agent `make_agent_no_verifier`.
def ablation_rule_planner(seed: int = 0) -> BackendAgent:
    return make_agent_config(seed, planner="rule")


def ablation_rules_verifier(seed: int = 0) -> BackendAgent:
    return make_agent_config(seed, verifier="rules")


def ablation_same_model_judge(seed: int = 0) -> BackendAgent:
    return make_agent_config(seed, verifier="llm", judge=None)


def regulation_ids(question: str) -> list[str]:
    """Ids the Advisor's regulation search returns for a question (for `report --regulation-lookup`)."""
    from co5151_backend.application.agents.advisor.tools import RegulationSearch

    search = RegulationSearch(InProcessRegulations(regulation_service(_engine())))
    return [r.id for r in asyncio.run(search.search(question))]
