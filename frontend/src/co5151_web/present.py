"""How backend data is shown in Chainlit: the processing details of an answer, and threads for the sidebar."""

import json
from typing import Any

PROGRESS = {
    "plan": "Lập kế hoạch: {action}",
    "tool": "Gọi tool `{tool}`",
    "write": "Soạn câu trả lời",
    "verify": "Verifier kiểm lượt {round}: {status}",
}


def progress_line(step: dict[str, Any]) -> str:
    template = PROGRESS.get(step.get("name", ""), "{name}")
    line = template.format_map({"action": "", "tool": "", "round": "", "status": "", **step})
    return line + (" (viết lại)" if step.get("revision") else "")


def _verifier_label(rounds: int | None) -> str:
    if rounds is None:
        return "không kiểm (tắt, hoặc câu trả lời không qua bước soạn)"
    return f"{rounds} lượt kiểm" + (", có viết lại" if rounds > 1 else "")


def details_markdown(trace: dict[str, Any]) -> str:
    rows = [
        ("Kết cục", trace.get("outcome") or "do LLM viết"),
        ("Tool đã gọi", ", ".join(trace.get("tool_calls") or []) or "không"),
        ("Trích dẫn", ", ".join(trace.get("citations") or []) or "không"),
        ("Verifier", _verifier_label(trace.get("verifier_rounds"))),
        ("Token", trace.get("input_tokens", 0) + trace.get("output_tokens", 0)),
        ("Thời gian", f"{trace.get('latency_ms', 0) / 1000:.2f} s"),
        ("LLM", trace.get("llm") or "không có (trả lời bằng mẫu)"),
        ("Trace ID", f"`{trace['trace_id']}`"),
    ]
    if trace.get("llm_error"):
        rows.append(("Lỗi LLM", trace["llm_error"]))
    return "\n".join(f"- **{label}:** {value}" for label, value in rows)


def thread_dict(conversation: dict[str, Any], identifier: str) -> dict[str, Any]:
    """A backend conversation as a Chainlit ThreadDict; messages keep their backend ids (feedback targets them)."""
    steps = []
    for m in conversation.get("messages", []):
        user = m["role"] == "user"
        feedback = m.get("feedback")
        if feedback:
            feedback = {"id": m["id"], "forId": m["id"], "value": feedback["value"], "comment": feedback.get("comment")}
        steps.append(
            {
                "id": m["id"],
                "threadId": conversation["id"],
                "parentId": None,
                "type": "user_message" if user else "assistant_message",
                "name": identifier if user else "Assistant",
                "input": "",
                "output": m["content"],
                "createdAt": m["created_at"],
                "start": m["created_at"],
                "end": m["created_at"],
                "isError": False,
                "metadata": {"trace_id": m.get("trace_id")} if m.get("trace_id") else {},
                "feedback": feedback or None,
            }
        )
    settings = conversation.get("settings") or {}
    return {
        "id": conversation["id"],
        "createdAt": conversation["created_at"],
        "name": conversation.get("title"),
        "userId": identifier,
        "userIdentifier": identifier,
        "tags": [],
        "metadata": {"chat_settings": {k: v for k, v in settings.items() if v}},
        "steps": steps,
        "elements": [],
    }


def chat_settings_body(settings: dict[str, Any] | None) -> dict[str, Any]:
    """The Chainlit settings form as backend conversation settings (empty model = provider default)."""
    settings = settings or {}
    return {"provider": settings.get("provider") or None, "model": (settings.get("model") or "").strip() or None}


def pick_provider(saved: str | None, providers: list[str], default: str) -> str:
    """The conversation's provider if it still has a key on the backend, else the backend default, else the first."""
    if saved in providers:
        return saved
    return default if default in providers else providers[0]


# Agent flow (right sidebar) ------------------------------------------------------------------------------------

NODE_LABELS = {
    "planner": "Planner",
    "student_record": "MCP Student Record",
    "regulation": "MCP Regulation",
    "writer": "Advisor viết câu trả lời",
    "verifier": "Verifier",
}
VERIFIER_TONES = {"pass": "ok", "revise": "warn", "refuse": "error"}


def _short(text: Any, limit: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


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
        detail = f" · {_short(issues[0].get('message', ''), 70)}" if issues else ""
        return f"{status.upper()}{detail}", VERIFIER_TONES.get(status, "warn")
    return "", "ok"


def _pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) if value else "{}"


def flow_props(question: str, answer: str | None, spans: list[dict[str, Any]], trace: dict[str, Any] | None) -> dict:
    """Props of the `AgentFlow` custom element: the question, one entry per node in order, then the answer."""
    nodes = []
    for i, span in enumerate(spans):
        summary, tone = _summary(span)
        nodes.append(
            {
                "id": i,
                "node": span["node"],
                "label": NODE_LABELS.get(span["node"], span["node"]),
                "name": span.get("name", ""),
                "summary": summary,
                "tone": tone,
                "ms": span.get("duration_ms", 0),
                "tokens": span.get("input_tokens", 0) + span.get("output_tokens", 0),
                "input": _pretty(span.get("input")),
                "output": _pretty(span.get("output")),
            }
        )
    trace = trace or {}
    return {
        "question": question,
        "answer": answer,
        "nodes": nodes,
        "total_ms": trace.get("latency_ms"),
        "total_tokens": (trace.get("input_tokens") or 0) + (trace.get("output_tokens") or 0) if trace else None,
        "llm": trace.get("llm"),
    }


def answers_of_thread(thread: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Trace id -> the question, the answer and the answer's message id, oldest first, for every answer of a
    reopened thread that has a trace (the ones whose agent flow can be shown)."""
    answers: dict[str, dict[str, Any]] = {}
    question = ""
    for step in thread.get("steps") or []:
        if step.get("type") == "user_message":
            question = step.get("output") or ""
        trace_id = (step.get("metadata") or {}).get("trace_id")
        if step.get("type") == "assistant_message" and trace_id:
            answers[trace_id] = {"question": question, "answer": step.get("output"), "message_id": step["id"]}
    return answers


def answer_choices(flows: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """The answers of the conversation for the picker in the panel, oldest first, labelled by their question."""
    return [{"trace_id": t, "label": f"#{i} {_short(f['question'], 60)}"} for i, (t, f) in enumerate(flows.items(), 1)]


def empty_flow_props(flows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The panel before an answer is picked: a hint, and the picker when the conversation has answers."""
    return {"empty": True, "question": None, "answer": None, "nodes": [], "answers": answer_choices(flows)}
