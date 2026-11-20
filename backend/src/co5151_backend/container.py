"""Composition root: the only module that picks the adapters behind each port.

The app uses the MCP gateways, the SQL store and the LLM providers configured in the environment. The evaluation
and the tests pass their own adapters (in-process gateways, in-memory store, fake LLM) through `Adapters`.
"""

from dataclasses import dataclass, field
from typing import Any

from .application.agents.advisor.advisor import Advisor
from .application.agents.advisor.planner import LLMActionRouter
from .application.agents.advisor.prompts import CANARY
from .application.agents.verifier import ComplianceVerifier, LLMJudge, rule_checks
from .application.ports import (
    AccountDirectory,
    ActionRouter,
    ChatModel,
    ChatModels,
    ConversationRepository,
    RegulationGateway,
    StudentRecordGateway,
    TraceRepository,
)
from .application.usecases.ask import AskQuestion
from .application.usecases.auth import Authenticate, SignIn
from .application.usecases.conversations import Conversations
from .infrastructure.config import Settings
from .infrastructure.identity import DemoAccountDirectory, JwtAccessTokens, SignedStudentTokens
from .infrastructure.laya import LayaActionRouter
from .infrastructure.llm import ProviderChatModels
from .infrastructure.mcp.gateways import McpRegulationGateway, McpStudentRecordGateway
from .infrastructure.persistence.memory import InMemoryChatRepository, InMemoryTraceRepository
from .infrastructure.persistence.sql import SqlChatRepository, SqlTraceRepository

PLANNER_MODES = ("llm", "rule", "laya")
VERIFIER_MODES = ("llm", "rules", "off")


@dataclass
class Adapters:
    """Adapters to use instead of the configured ones (None: build from settings)."""

    chats: ConversationRepository | None = None
    traces: TraceRepository | None = None
    student: StudentRecordGateway | None = None
    regulations: RegulationGateway | None = None
    models: ChatModels | None = None
    accounts: AccountDirectory | None = None


@dataclass
class Container:
    settings: Settings
    sign_in: SignIn
    authenticate: Authenticate
    conversations: Conversations
    ask: AskQuestion
    chats: ConversationRepository
    models: ChatModels
    _sql: SqlChatRepository | None = field(default=None, repr=False)

    async def start(self) -> None:
        if self._sql is not None:
            await self._sql.create_schema()

    async def close(self) -> None:
        if self._sql is not None:
            await self._sql.close()

    def describe(self) -> dict[str, Any]:
        """Configuration of the answer pipeline, recorded with each evaluation run."""
        provider = self.models.default_provider()
        model = self.models.create(provider, None)
        return {
            "llm": {"provider": model.provider, "model": model.model} if model else None,
            "planner": self.settings.planner_mode,
            "verifier": self.settings.verifier_mode,
            "verifier_model": self.settings.verifier_model,
        }


def router_factory(settings: Settings):
    if settings.planner_mode not in PLANNER_MODES:
        raise ValueError(f"ADVISOR_PLANNER_MODE must be one of {PLANNER_MODES}, got {settings.planner_mode!r}")

    def router_for(model: ChatModel | None) -> ActionRouter | None:
        if settings.planner_mode == "laya":
            return LayaActionRouter(settings.laya_url)
        if settings.planner_mode == "llm" and model is not None:
            return LLMActionRouter(model)
        return None

    return router_for


def verifier_factory(settings: Settings, models: ChatModels):
    """`llm`: rule checks, then one judge call (on VERIFIER_LLM_MODEL of the same provider if set). `rules`: rule
    checks only. `off`: no Verifier (the single-agent baseline)."""
    if settings.verifier_mode not in VERIFIER_MODES:
        raise ValueError(f"ADVISOR_VERIFIER must be one of {VERIFIER_MODES}, got {settings.verifier_mode!r}")
    checks = rule_checks(secrets=[CANARY])

    def verifier_for(model: ChatModel | None) -> ComplianceVerifier | None:
        if settings.verifier_mode == "off":
            return None
        if settings.verifier_mode == "rules" or model is None:
            return ComplianceVerifier(checks)
        judge_model = models.create(model.provider, settings.verifier_model) if settings.verifier_model else model
        return ComplianceVerifier(checks, judge=LLMJudge(judge_model or model, canary=CANARY))

    return verifier_for


def build_container(settings: Settings, adapters: Adapters | None = None) -> Container:
    a = adapters or Adapters()
    sql = None
    if a.chats is not None:
        chats, traces = a.chats, a.traces
    elif settings.database_url:
        sql = SqlChatRepository.from_url(settings.database_url)
        chats, traces = sql, SqlTraceRepository(sql)
    else:  # history kept for the life of the process only
        chats = InMemoryChatRepository()
        traces = InMemoryTraceRepository(chats)
    models = a.models or ProviderChatModels()
    accounts = a.accounts or DemoAccountDirectory(settings.accounts_file)
    access_tokens = JwtAccessTokens(settings.token_secret, settings.token_ttl)
    advisor = Advisor(
        a.student or McpStudentRecordGateway(settings.student_mcp_url),
        a.regulations or McpRegulationGateway(settings.regulation_mcp_url),
    )
    return Container(
        settings=settings,
        sign_in=SignIn(accounts, access_tokens),
        authenticate=Authenticate(access_tokens),
        conversations=Conversations(chats, traces, models),
        ask=AskQuestion(
            chats=chats,
            traces=traces,
            accounts=accounts,
            student_tokens=SignedStudentTokens(settings.student_token_secret, settings.student_token_ttl),
            models=models,
            advisor=advisor,
            router_for=router_factory(settings),
            verifier_for=verifier_factory(settings, models),
            history_messages=settings.history_messages,
        ),
        chats=chats,
        models=models,
        _sql=sql,
    )
