import pytest
from web_fakes import CONVERSATION, TOKEN, FakeBackend

from co5151_web.client import SessionExpired

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
