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
from co5151_backend.domain.trace import Trace
from co5151_backend.infrastructure.config import Settings
from co5151_backend.infrastructure.identity import DemoAccountDirectory
from co5151_backend.infrastructure.persistence.memory import InMemoryChatRepository, InMemoryTraceRepository
from co5151_contracts import ToolResult
from co5151_contracts.security import AuthError
from regulation_server.regulation_service_v2 import RegulationServiceV2

from .agent import AgentResponse, Usage
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


def _settings(**overrides: Any) -> Settings:
    """The API's settings, with the Student Record secret of the in-process service and no chat database."""
    secret = _oracle().settings.token_secret
    return dataclasses.replace(Settings.from_env(), student_token_secret=secret, database_url=None, **overrides)


def _response(trace: Trace, text: str) -> AgentResponse:
    return AgentResponse(
        text=text,
        outcome=Outcome(trace.outcome.value) if trace.outcome else Outcome.ANSWER,
        citations=list(trace.citations),
        tool_calls=list(trace.tool_calls),
        usage=Usage(input_tokens=trace.usage.input_tokens, output_tokens=trace.usage.output_tokens),
        verifier_rounds=trace.verifier_rounds,
    )


class BackendAgent:
    """One evaluation session: a new conversation per answer, seeded with the task's history."""

    def __init__(self, name: str, settings: Settings):
        self.name = name
        self._settings = settings

    def _container(self) -> Container:
        chats = InMemoryChatRepository()
        adapters = Adapters(chats=chats, traces=InMemoryTraceRepository(chats),
                            accounts=_accounts(), student=InProcessStudentRecord(_oracle().service),
                            regulations=InProcessRegulations(_regulations()))  # fmt: skip
        return build_container(self._settings, adapters)

    def describe(self) -> dict[str, Any]:
        return {**self._container().describe(), "regulation_source": "regulation-service (in-process)"}

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
        return _response(answer.trace, answer.message.content)


def make_agent(seed: int = 0) -> BackendAgent:
    """The Advisor with the Compliance Verifier configured by `ADVISOR_VERIFIER` (default `llm`)."""
    return BackendAgent("advisor", _settings())


def make_agent_no_verifier(seed: int = 0) -> BackendAgent:
    """Baseline of the proposal: the same Advisor as a single agent, whatever `ADVISOR_VERIFIER` says."""
    return BackendAgent("advisor-no-verifier", _settings(verifier_mode="off"))


def regulation_ids(question: str) -> list[str]:
    """Ids the Advisor's regulation search returns for a question (for `report --regulation-lookup`)."""
    from co5151_backend.application.agents.advisor.tools import RegulationSearch

    search = RegulationSearch(InProcessRegulations(_regulations()))
    return [r.id for r in asyncio.run(search.search(question))]
