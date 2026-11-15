"""Asks the backend over its public API, exactly like the chat app: so an evaluation run tests the whole system
(API, MCP servers, LLM) and its traces land in the backend's database, where the Traces page shows them."""

import uuid

import httpx

from ..ports import AgentAnswer

GUEST = "khach"
# One answer may take several LLM calls (plan, write, verify, rewrite)
TIMEOUT = httpx.Timeout(10.0, read=180.0)


class HttpAnswerAgent:
    def __init__(self, base_url: str, demo_password: str, transport: httpx.BaseTransport | None = None):
        self._password = demo_password
        self._http = httpx.Client(base_url=base_url, timeout=TIMEOUT, transport=transport)

    def answer(self, question: str, *, user: str | None) -> AgentAnswer:
        try:
            return self._answer(question, user or GUEST)
        except httpx.HTTPError as e:
            return AgentAnswer("", None, f"backend: {type(e).__name__}: {e}")

    def _answer(self, question: str, username: str) -> AgentAnswer:
        login = self._http.post("/auth/login", json={"username": username, "password": self._password})
        if login.status_code != 200:
            return AgentAnswer("", None, f"đăng nhập {username} thất bại ({login.status_code})")
        auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
        conversation_id = str(uuid.uuid4())
        self._http.post("/conversations", json={"id": conversation_id}, headers=auth).raise_for_status()
        res = self._http.post(f"/conversations/{conversation_id}/messages", json={"content": question}, headers=auth)
        body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        if res.status_code == 200:
            return AgentAnswer(body["message"]["content"], body["trace"])
        trace = {"trace_id": body["trace_id"], "conversation_id": conversation_id} if body.get("trace_id") else None
        return AgentAnswer("", trace, f"backend {res.status_code}: {body.get('detail', res.text[:200])}")
