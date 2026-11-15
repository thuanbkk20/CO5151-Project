import pytest
from web_fakes import CONVERSATION, SPANS, TOKEN, TRACE, FakeBackend

from co5151_web.client import BackendError, SessionExpired

pytestmark = pytest.mark.anyio


async def test_login_returns_the_session_or_none_for_wrong_credentials():
    client = FakeBackend().client()
    assert (await client.login("sv002", "demo"))["access_token"] == TOKEN
    assert await client.login("sv002", "sai") is None


async def test_expired_token_raises_session_expired():
    with pytest.raises(SessionExpired):
        await FakeBackend().client().conversations("old-token")


async def test_missing_conversation_is_none():
    client = FakeBackend().client()
    assert await client.conversation(TOKEN, "khong-co") is None
    assert (await client.conversation(TOKEN, CONVERSATION["id"]))["title"] == CONVERSATION["title"]


async def test_feedback_none_deletes_it():
    backend = FakeBackend()
    client = backend.client()
    await client.feedback(TOKEN, "m2", 1, "tốt")
    await client.feedback(TOKEN, "m2", None)
    assert [(m, p) for m, p, _ in backend.requests] == [("PUT", "/messages/m2/feedback"),
                                                        ("DELETE", "/messages/m2/feedback")]  # fmt: skip


async def test_ask_yields_the_server_sent_events_in_order():
    events = [e async for e in FakeBackend().client().ask(TOKEN, CONVERSATION["id"], "Điều kiện tốt nghiệp?")]
    assert [name for name, _ in events] == ["step", "step", "answer"]
    assert events[1][1]["tool"] == "get_my_academic_summary"
    assert events[2][1]["message"]["id"] == "m2"


async def test_trace_and_spans_of_an_answer_and_404_for_an_unknown_trace():
    client = FakeBackend().client()
    assert await client.spans(TOKEN, "t1") == SPANS
    assert await client.trace(TOKEN, "t1") == TRACE
    with pytest.raises(BackendError) as missing:
        await client.spans(TOKEN, "khong-co")
    assert missing.value.status == 404
