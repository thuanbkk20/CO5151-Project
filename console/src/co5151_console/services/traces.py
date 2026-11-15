"""Traces page: the backend's traces as rows of a table, and one trace as its flow of nodes.

Pure functions over the admin API's JSON; the page templates only print what these return.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from ..ports import BackendAdmin

NODE_LABELS = {
    "planner": "Planner",
    "student_record": "MCP Student Record",
    "regulation": "MCP Regulation",
    "writer": "Advisor viết câu trả lời",
    "verifier": "Verifier",
}
VERIFIER_TONES = {"pass": "ok", "revise": "warn", "refuse": "error"}


@dataclass(frozen=True)
class TraceRow:
    trace_id: str
    session: str
    created_at: str
    owner: str
    question: str
    result: str  # what the answer amounts to: outcome, "lỗi", or "LLM viết"
    tone: str  # ok | warn | error
    tools: str
    tokens: int
    seconds: float


@dataclass(frozen=True)
class Node:
    label: str
    name: str
    summary: str
    tone: str
    ms: int
    tokens: int
    input: str  # pretty JSON
    output: str
    error: str | None = None


@dataclass(frozen=True)
class TraceDetail:
    row: TraceRow
    question: str | None
    answer: str | None
    llm: str | None
    llm_error: str | None
    error: str | None
    nodes: list[Node] = field(default_factory=list)


class TraceBrowser:
    def __init__(self, admin: BackendAdmin):
        self._admin = admin

    def recent(self, session: str | None = None, limit: int = 50) -> list[TraceRow]:
        """Raises BackendError."""
        return [_row(item) for item in self._admin.traces(conversation_id=session or None, limit=limit)]

    def detail(self, trace_id: str) -> TraceDetail | None:
        """Raises BackendError."""
        item = self._admin.trace(trace_id)
        if item is None:
            return None
        t = item["trace"]
        return TraceDetail(
            row=_row(item),
            question=item.get("question"),
            answer=item.get("answer"),
            llm=t.get("llm"),
            llm_error=t.get("llm_error"),
            error=t.get("error"),
            nodes=[_node(s) for s in item.get("spans") or []],
        )


def _short(text: Any, limit: int = 100) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _row(item: dict[str, Any]) -> TraceRow:
    t = item["trace"]
    if t.get("error"):
        result, tone = "lỗi", "error"
    elif t.get("outcome"):
        result, tone = t["outcome"], "warn" if t["outcome"] != "answer" else "ok"
    else:
        result, tone = "LLM viết", "ok"
    return TraceRow(
        trace_id=t["trace_id"],
        session=t["conversation_id"],
        created_at=(item.get("created_at") or "")[:19].replace("T", " "),
        owner=item.get("owner_id", ""),
        question=_short(item.get("question")),
        result=result,
        tone=tone,
        tools=", ".join(t.get("tool_calls") or []) or "—",
        tokens=(t.get("input_tokens") or 0) + (t.get("output_tokens") or 0),
        seconds=round((t.get("latency_ms") or 0) / 1000, 2),
    )


def _summary(span: dict[str, Any]) -> tuple[str, str]:
    """One line saying what the node returned, and its tone: ok | warn | error."""
    node, out = span["node"], span.get("output") or {}
    if span.get("error"):
        return _short(span["error"]), "error"
    if node == "planner":
        by = f" (bởi {out.get('by')})" if out.get("by") else ""
        return f"→ {out.get('action', '?')}{by}", "warn" if out.get("error") else "ok"
    if node in ("student_record", "regulation"):
        if not out.get("ok"):
            error = out.get("error") or {}
            return _short(f"Lỗi {error.get('code', '')}: {error.get('message', '')}"), "error"
        data = out.get("data") or {}
        if node == "student_record":
            return f"Trả về {len(data)} trường hồ sơ", "ok"
        ids = [(r.get("evidence") or {}).get("provision_id") or r.get("id", "?") for r in data.get("results") or []]
        return (_short(f"{len(ids)} điều khoản: {', '.join(ids)}"), "ok") if ids else ("Không có kết quả", "warn")
    if node == "writer":
        if out.get("text") is None:
            return out.get("note") or "Không viết được", "error"
        return _short(f"[{out.get('by')}] {out['text']}"), "ok"
    if node == "verifier":
        status, issues = out.get("status", "?"), out.get("issues") or []
        detail = f" · {_short(issues[0].get('message', ''), 80)}" if issues else ""
        return f"{status.upper()}{detail}", VERIFIER_TONES.get(status, "warn")
    return "", "ok"


def _node(span: dict[str, Any]) -> Node:
    summary, tone = _summary(span)
    return Node(
        label=NODE_LABELS.get(span["node"], span["node"]),
        name=span.get("name", ""),
        summary=summary,
        tone=tone,
        ms=span.get("duration_ms", 0),
        tokens=(span.get("input_tokens") or 0) + (span.get("output_tokens") or 0),
        input=json.dumps(span.get("input") or {}, ensure_ascii=False, indent=2),
        output=json.dumps(span.get("output") or {}, ensure_ascii=False, indent=2),
        error=span.get("error"),
    )
