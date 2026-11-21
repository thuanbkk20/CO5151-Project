import httpx
from console_fakes import TRACE, FakeBackend

from co5151_console.adapters.backend_agent import HttpAnswerAgent


def agent(backend: FakeBackend, password: str = "demo") -> HttpAnswerAgent:
    return HttpAnswerAgent("http://backend", password, transport=backend.transport())


def test_asks_as_the_tasks_user_in_a_new_conversation():
    backend = FakeBackend(answers={"Em còn bao nhiêu tín chỉ?": "Còn 15 tín chỉ."})
    first = agent(backend).answer("Em còn bao nhiêu tín chỉ?", user="sv001")
    second = agent(backend).answer("Học phí?", user=None)
    assert (first.text, first.trace["trace_id"], first.error) == ("Còn 15 tín chỉ.", TRACE["trace_id"], None)
    assert backend.logins == ["sv001", "khach"] and first.trace["conversation_id"] != second.trace["conversation_id"]
    asked = [r for r in backend.requests if r.url.path.endswith("/messages")][0]
    assert asked.headers["authorization"] == "Bearer user-sv001"


def test_failures_come_back_as_errors():
    failed = agent(FakeBackend(fail_questions=("x",))).answer("x", user="sv001")
    assert failed.error.startswith("backend 500") and failed.trace["trace_id"] == "t-failed"
    assert "đăng nhập sv001 thất bại" in agent(FakeBackend(), password="sai").answer("x", user="sv001").error

    def down(request):
        raise httpx.ConnectError("refused")

    offline = HttpAnswerAgent("http://backend", "demo", transport=httpx.MockTransport(down)).answer("x", user=None)
    assert offline.error.startswith("backend: ConnectError") and offline.trace is None
