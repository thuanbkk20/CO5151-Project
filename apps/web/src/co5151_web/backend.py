import logging
import time
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from co5151_advisor.agent import AdvisorAgent
from co5151_advisor.eval_adapter import make_verifier, regulation_source
from co5151_advisor.eval_adapter import student_service as advisor_student_service
from co5151_advisor.llm import DEFAULT_PROVIDER, PROVIDERS, LLMClient
from co5151_chat_store import Turn, new_trace_id
from student_server.auth import AuthError, login
from student_server.config import Settings
from student_server.server import build_service

logger = logging.getLogger(__name__)

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
    return AdvisorAgent(
        advisor_student_service(student_service()),
        regulation_source(),
        llm_client=llm,
        verifier=make_verifier(llm),
    )


@dataclass
class Reply:
    text: str
    details: dict[str, Any] = field(default_factory=dict)


def ask(
    advisor: AdvisorAgent,
    question: str,
    *,
    token: str | None,
    history: list[dict[str, str]],
    trace_id: str | None = None,
) -> Reply:
    """One chat turn. `trace_id` identifies it in the logs, the UI and the chat store; a new one is made if omitted."""
    trace_id = trace_id or new_trace_id()
    start = time.perf_counter()
    resp = advisor.answer(question, session_token=token, history=history[-HISTORY_TURNS:])
    seconds = time.perf_counter() - start
    llm = advisor.llm_client.describe() if advisor.llm_client else {}
    details = {
        "trace_id": trace_id,
        "outcome": resp.outcome.value if resp.outcome else "do LLM viết",
        "tool_calls": resp.tool_calls,
        "citations": resp.citations,
        "verifier_rounds": resp.verifier_rounds,
        "tokens": resp.usage.total,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "seconds": round(seconds, 2),
        "llm": f"{llm.get('provider', '-')}/{llm.get('model', '-')}",
    }
    logger.info(
        "trace=%s outcome=%s tools=%s verifier_rounds=%s tokens=%s seconds=%.2f",
        trace_id, details["outcome"], ",".join(resp.tool_calls) or "-", resp.verifier_rounds, resp.usage.total, seconds,
    )  # fmt: skip
    return Reply(text=resp.text, details=details)


def to_turn(
    details: dict[str, Any],
    *,
    conversation_id: str,
    user_message_id: str | None = None,
    answer_message_id: str | None = None,
    error: str | None = None,
) -> Turn:
    """The trace of one answered question, ready for the chat store."""
    return Turn(
        trace_id=details["trace_id"],
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        answer_message_id=answer_message_id,
        outcome=details.get("outcome"),
        tool_calls=list(details.get("tool_calls", [])),
        citations=list(details.get("citations", [])),
        verifier_rounds=details.get("verifier_rounds"),
        input_tokens=details.get("input_tokens", 0),
        output_tokens=details.get("output_tokens", 0),
        latency_ms=round(details.get("seconds", 0) * 1000),
        llm=details.get("llm"),
        error=error,
    )


def _verifier_label(rounds: int | None) -> str:
    if rounds is None:
        return "không kiểm (tắt, hoặc câu trả lời không qua bước soạn)"
    return f"{rounds} lượt kiểm" + (", có viết lại" if rounds > 1 else "")


def details_markdown(details: dict[str, Any]) -> str:
    rows = [
        ("Kết cục", details["outcome"]),
        ("Tool đã gọi", ", ".join(details["tool_calls"]) or "không"),
        ("Trích dẫn", ", ".join(details["citations"]) or "không"),
        ("Verifier", _verifier_label(details.get("verifier_rounds"))),
        ("Token", details["tokens"]),
        ("Thời gian", f"{details['seconds']} s"),
        ("LLM", details["llm"]),
        ("Trace ID", f"`{details['trace_id']}`" if details.get("trace_id") else "không có"),
    ]
    return "\n".join(f"- **{label}:** {value}" for label, value in rows)
