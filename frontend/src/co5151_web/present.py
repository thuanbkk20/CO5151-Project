"""How backend data is shown in Chainlit: the processing details of an answer, and threads for the sidebar."""

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
