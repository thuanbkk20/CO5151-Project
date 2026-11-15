"""A fake backend (admin API and the user API) on httpx.MockTransport, answering like the real one. No network,
no LLM."""

import json

import httpx

TOKEN = "admin-token"
SESSION = "6f1c1f0e-0000-4000-8000-000000000001"
SPANS = [
    {"node": "planner", "name": "rules", "input": {"question": "Điều kiện tốt nghiệp?"},
     "output": {"action": "SUMMARY", "by": "rule", "error": None}, "start_ms": 0, "duration_ms": 0,
     "input_tokens": 0, "output_tokens": 0, "error": None},
    {"node": "regulation", "name": "search_regulations", "input": {"args": {"query": "tốt nghiệp"}},
     "output": {"ok": True, "data": {"results": [{"id": "r", "evidence": {"provision_id": "QD-Đ22"}}]}},
     "start_ms": 1, "duration_ms": 80, "input_tokens": 0, "output_tokens": 0, "error": None},
    {"node": "writer", "name": "draft", "input": {"question": "Điều kiện tốt nghiệp?"},
     "output": {"text": "Theo Điều 22...", "by": "gemini/x"}, "start_ms": 82, "duration_ms": 1500,
     "input_tokens": 900, "output_tokens": 120, "error": None},
    {"node": "verifier", "name": "round 1", "input": {"draft": "Theo Điều 22..."},
     "output": {"status": "revise", "issues": [{"code": "UNGROUNDED_CLAIM", "message": "Sai số tín chỉ."}]},
     "start_ms": 1583, "duration_ms": 800, "input_tokens": 300, "output_tokens": 30, "error": None},
]  # fmt: skip
TRACE = {"trace_id": "t1", "conversation_id": SESSION, "user_message_id": "m1", "answer_message_id": "m2",
         "outcome": None, "steps": ["SUMMARY"], "tool_calls": ["search_regulations"], "citations": ["QD-Đ22"],
         "verifier_rounds": 1, "input_tokens": 1200, "output_tokens": 150, "latency_ms": 2500, "llm": "gemini/x",
         "llm_error": None, "error": None}  # fmt: skip
ITEM = {"trace": TRACE, "owner_id": "sv002", "question": "Điều kiện tốt nghiệp?", "answer": "Theo Điều 22...",
        "created_at": "2026-11-15T08:00:00Z", "spans": []}  # fmt: skip


class FakeBackend:
    def __init__(self, admin_enabled: bool = True, answers: dict[str, str] | None = None,
                 fail_questions: tuple[str, ...] = ()):  # fmt: skip
        self.admin_enabled = admin_enabled
        self.answers = answers or {}
        self.fail_questions = fail_questions
        self.logins: list[str] = []
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.startswith("/admin/") and not self.admin_enabled:
            return httpx.Response(404, json={"detail": "not found"})
        if path.startswith("/admin/") and request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "not signed in"})
        if path == "/auth/login":
            body = json.loads(request.content)
            if body["password"] != "demo":
                return httpx.Response(401, json={"detail": "invalid credentials"})
            self.logins.append(body["username"])
            return httpx.Response(200, json={"access_token": f"user-{body['username']}", "expires_in": 60})
        if path == "/conversations":
            return httpx.Response(201, json={"id": json.loads(request.content)["id"]})
        if path.endswith("/messages"):
            question = json.loads(request.content)["content"]
            if question in self.fail_questions:
                return httpx.Response(500, json={"detail": "answer failed", "trace_id": "t-failed"})
            answer = self.answers.get(question, "Theo Điều 22...")
            conversation = path.split("/")[2]
            return httpx.Response(200, json={"message": {"id": "m2", "content": answer},
                                             "trace": {**TRACE, "conversation_id": conversation}})  # fmt: skip
        if path == "/admin/traces":
            session = request.url.params.get("conversation_id")
            return httpx.Response(200, json={"items": [ITEM] if session in (None, SESSION) else []})
        if path == "/admin/traces/t1":
            return httpx.Response(200, json={**ITEM, "spans": SPANS})
        if path.startswith("/admin/traces/"):
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(500)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)
