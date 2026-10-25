import time
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from co5151_advisor.agent import AdvisorAgent
from co5151_advisor.eval_adapter import regulation_source
from co5151_advisor.llm import DEFAULT_PROVIDER, PROVIDERS, LLMClient
from student_server.auth import AuthError, login
from student_server.config import Settings
from student_server.server import build_service

GUEST_USERNAME = "khach"
HISTORY_TURNS = 10


@cache
def student_service():
    return build_service(Settings.from_env())


def sign_in(username: str, password: str) -> tuple[bool, str | None]:
    if username == GUEST_USERNAME:
        return True, None
    service = student_service()
    try:
        return True, login(service.db, service.signer, username, password)
    except AuthError:
        return False, None


def configured_providers() -> list[str]:
    return [name for name in PROVIDERS if LLMClient(provider=name).is_available]


def default_provider(providers: list[str]) -> str:
    return DEFAULT_PROVIDER if DEFAULT_PROVIDER in providers or not providers else providers[0]


def new_advisor(provider: str | None = None, model: str | None = None) -> AdvisorAgent:
    llm = LLMClient(provider=provider, model=model or None)
    return AdvisorAgent(student_service(), regulation_source(), llm_client=llm)


@dataclass
class Reply:
    text: str
    details: dict[str, Any] = field(default_factory=dict)


def ask(advisor: AdvisorAgent, question: str, *, token: str | None, history: list[dict[str, str]]) -> Reply:
    start = time.perf_counter()
    resp = advisor.answer(question, session_token=token, history=history[-HISTORY_TURNS:])
    llm = advisor.llm_client.describe() if advisor.llm_client else {}
    return Reply(
        text=resp.text,
        details={
            "outcome": resp.outcome.value if resp.outcome else "do LLM viết",
            "tool_calls": resp.tool_calls,
            "citations": resp.citations,
            "tokens": resp.usage.total,
            "seconds": round(time.perf_counter() - start, 2),
            "llm": f"{llm.get('provider', '-')}/{llm.get('model', '-')}",
        },
    )


def details_markdown(details: dict[str, Any]) -> str:
    rows = [
        ("Kết cục", details["outcome"]),
        ("Tool đã gọi", ", ".join(details["tool_calls"]) or "không"),
        ("Trích dẫn", ", ".join(details["citations"]) or "không"),
        ("Token", details["tokens"]),
        ("Thời gian", f"{details['seconds']} s"),
        ("LLM", details["llm"]),
    ]
    return "\n".join(f"- **{label}:** {value}" for label, value in rows)
