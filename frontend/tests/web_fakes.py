"""A fake backend API on httpx.MockTransport: records every request, answers like the real one."""

import json

import httpx

from co5151_web.client import BackendClient

TOKEN = "access-token"
USER = {"id": "sv002", "role": "student", "display_name": "Sinh viên 2"}
CONVERSATION = {
    "id": "6f1c1f0e-0000-4000-8000-000000000001",
    "title": "Điều kiện tốt nghiệp",
    "created_at": "2026-11-12T08:00:00Z",
    "updated_at": "2026-11-12T08:00:05Z",
    "settings": {"provider": "gemini", "model": None},
    "messages": [
        {"id": "m1", "role": "user", "content": "Điều kiện tốt nghiệp?", "created_at": "2026-11-12T08:00:00Z",
         "trace_id": None, "feedback": None},
        {"id": "m2", "role": "assistant", "content": "Theo Điều 22...", "created_at": "2026-11-12T08:00:05Z",
         "trace_id": "t1", "feedback": {"value": 1, "comment": "tốt"}},
    ],
}  # fmt: skip
TRACE = {"trace_id": "t1", "outcome": None, "tool_calls": ["get_my_academic_summary"], "citations": ["QD-Đ22"],
         "verifier_rounds": 1, "input_tokens": 1200, "output_tokens": 150, "latency_ms": 2500, "llm": "gemini/x",
         "llm_error": None}  # fmt: skip
STREAM = (
    'event: step\ndata: {"name": "plan", "action": "SUMMARY"}\n\n'
    'event: step\ndata: {"name": "tool", "tool": "get_my_academic_summary"}\n\n'
    "event: answer\ndata: "
    + json.dumps({"message": CONVERSATION["messages"][1], "trace": TRACE}, ensure_ascii=False)
    + "\n\n"
)


class FakeBackend:
    def __init__(self):
        self.requests: list[tuple[str, str, dict | None]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        path, method = request.url.path, request.method
        if path == "/auth/login":
            if body["password"] != "demo":
                return httpx.Response(401, json={"detail": "sai tên đăng nhập hoặc mật khẩu"})
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 60, "user": USER})
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "token hết hạn"})
        if path == "/llm/providers":
            return httpx.Response(200, json={"providers": ["gemini"], "default": "gemini"})
        if path == "/conversations" and method == "GET":
            item = {k: v for k, v in CONVERSATION.items() if k != "messages"}
            return httpx.Response(200, json={"items": [item], "next_cursor": "c2"})
        if path == "/conversations" and method == "POST":
            return httpx.Response(201, json={**CONVERSATION, "id": body["id"], "messages": []})
        if path.endswith("/messages/stream"):
            return httpx.Response(200, text=STREAM, headers={"content-type": "text/event-stream"})
        if path.startswith("/conversations/"):
            if path.removeprefix("/conversations/") != CONVERSATION["id"]:
                return httpx.Response(404, json={"detail": "không tìm thấy"})
            if method == "DELETE":
                return httpx.Response(204)
            return httpx.Response(200, json=CONVERSATION)
        if path.startswith("/messages/"):
            return httpx.Response(204)
        return httpx.Response(500)

    def client(self) -> BackendClient:
        return BackendClient("http://backend", transport=httpx.MockTransport(self.handle))
