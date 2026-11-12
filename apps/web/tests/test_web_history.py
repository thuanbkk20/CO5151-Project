import os

import pytest
from chainlit.context import ChainlitContext, context_var
from chainlit.session import HTTPSession
from chainlit.types import Feedback, Pagination, ThreadFilter
from chainlit.user import User

from co5151_chat_store import ChatStore, Turn
from co5151_web import history

pytestmark = pytest.mark.anyio


@pytest.fixture
async def layer(tmp_path):
    # Outside a websocket session Chainlit runs data-layer calls at once instead of queueing them
    context_var.set(ChainlitContext(HTTPSession(id="s", thread_id="t", client_type="webapp")))
    layer = history.ChatHistoryDataLayer(ChatStore.from_url(f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}"))
    yield layer
    await layer.close()


def message(step_id, thread_id, type_, text, created, **kw):
    return {"id": step_id, "threadId": thread_id, "type": type_, "name": "sv001", "output": text, "input": "",
            "createdAt": created, "metadata": {}, "showInput": False, **kw}  # fmt: skip


async def chat(layer, user_id, thread_id="c1", question="Em đủ điều kiện làm luận văn chưa?"):
    await layer.create_step(message(f"{thread_id}-q", thread_id, "user_message", question, "2026-11-12T08:00:00Z"))
    await layer.update_thread(thread_id, name=question, user_id=user_id)
    await layer.create_step(
        message(f"{thread_id}-a", thread_id, "assistant_message", "Bạn đã tích lũy 92/128 tín chỉ.",
                "2026-11-12T08:00:05.250Z", metadata={"trace_id": "ab" * 16})
    )  # fmt: skip


async def test_users_are_created_on_first_sign_in(layer):
    created = await layer.create_user(User(identifier="sv001", metadata={"guest": False}))
    found = await layer.get_user("sv001")
    assert created.id == found.id and found.identifier == "sv001" and found.createdAt.endswith("Z")
    assert await layer.get_user("sv002") is None


async def test_a_conversation_comes_back_with_its_messages(layer):
    user = await layer.create_user(User(identifier="sv001"))
    await chat(layer, user.id)
    thread = await layer.get_thread("c1")
    assert (thread["name"], thread["userIdentifier"], thread["userId"]) == (
        "Em đủ điều kiện làm luận văn chưa?",
        "sv001",
        user.id,
    )
    assert [(s["type"], s["output"]) for s in thread["steps"]] == [
        ("user_message", "Em đủ điều kiện làm luận văn chưa?"),
        ("assistant_message", "Bạn đã tích lũy 92/128 tín chỉ."),
    ]
    answer = thread["steps"][1]
    assert answer["metadata"] == {"trace_id": "ab" * 16}
    assert answer["createdAt"] == "2026-11-12T08:00:05.250000Z" and answer["showInput"] is False
    assert await layer.get_thread_author("c1") == "sv001"
    assert await layer.get_thread("missing") is None


async def test_each_user_sees_only_their_own_conversations(layer):
    sv1 = await layer.create_user(User(identifier="sv001"))
    sv2 = await layer.create_user(User(identifier="sv002"))
    await chat(layer, sv1.id, "c1")
    await chat(layer, sv1.id, "c2", "Em có bị cảnh báo học tập không?")
    await chat(layer, sv2.id, "c3")

    page = await layer.list_threads(Pagination(first=1), ThreadFilter(userId=sv1.id))
    assert [t["id"] for t in page.data] == ["c2"] and page.pageInfo.hasNextPage and page.pageInfo.endCursor == "c2"
    rest = await layer.list_threads(Pagination(first=5, cursor="c2"), ThreadFilter(userId=sv1.id))
    assert [t["id"] for t in rest.data] == ["c1"] and not rest.pageInfo.hasNextPage
    found = await layer.list_threads(Pagination(first=5), ThreadFilter(userId=sv1.id, search="cảnh báo"))
    assert [t["id"] for t in found.data] == ["c2"]
    assert (await layer.list_threads(Pagination(first=5), ThreadFilter())).data == []


async def test_only_chat_settings_are_kept_from_the_session(layer):
    user = await layer.create_user(User(identifier="sv001"))
    await chat(layer, user.id)
    session = {"chat_settings": {"provider": "gemini", "model": ""}, "client_type": "webapp",
               "history": [{"role": "user", "content": "điểm của em"}], "advisor": "<object>", "id": "s"}  # fmt: skip
    await layer.update_thread("c1", metadata=session)
    assert (await layer.get_thread("c1"))["metadata"] == {
        "chat_settings": {"provider": "gemini", "model": ""},
        "client_type": "webapp",
    }


async def test_rename_feedback_and_delete(layer):
    user = await layer.create_user(User(identifier="sv001"))
    await chat(layer, user.id)
    await layer.update_thread("c1", name="Luận văn")
    feedback_id = await layer.upsert_feedback(Feedback(forId="c1-a", value=0, comment="Thiếu trích dẫn"))
    thread = await layer.get_thread("c1")
    assert thread["name"] == "Luận văn"
    assert thread["steps"][1]["feedback"] == {"id": feedback_id, "forId": "c1-a", "value": 0,
                                              "comment": "Thiếu trích dẫn"}  # fmt: skip
    assert await layer.delete_feedback(feedback_id)
    await layer.delete_thread("c1")
    assert await layer.get_thread("c1") is None


def test_importing_chainlit_did_not_load_any_env_file():
    import chainlit

    from co5151_advisor.llm import PROVIDERS

    assert chainlit.env_found is False
    assert not any(os.environ.get(p.key_env) for p in PROVIDERS.values())


def test_history_is_stored_in_the_web_data_folder_unless_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("CHAT_DATABASE_URL", raising=False)
    assert str(history.open_store().engine.url).endswith("apps/web/.data/chat.db")
    monkeypatch.setenv("CHAT_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    assert str(history.open_store().engine.url).endswith("x.db")
    monkeypatch.setenv("CHAT_DATABASE_URL", "off")
    assert history.open_store() is None


async def test_a_resumed_conversation_gives_the_advisor_its_earlier_turns(layer):
    user = await layer.create_user(User(identifier="sv001"))
    await chat(layer, user.id)
    await layer.create_step(message("c1-tool", "c1", "tool", "- **Kết cục:** answer", "2026-11-12T08:00:04Z"))
    assert history.chat_history(await layer.get_thread("c1")) == [
        {"role": "user", "content": "Em đủ điều kiện làm luận văn chưa?"},
        {"role": "assistant", "content": "Bạn đã tích lũy 92/128 tín chỉ."},
    ]


def test_every_guest_sign_in_is_a_separate_identity():
    first, second = history.guest_identifier(), history.guest_identifier()
    assert first != second and first.startswith("khach-")


async def test_notices_are_not_saved_and_old_saved_ones_are_not_shown(layer, tmp_path):
    user = await layer.create_user(User(identifier="sv001"))
    await chat(layer, user.id)
    await layer.create_step(message("c1-n", "c1", "system_message", "Chưa có key LLM", "2026-11-12T08:00:06Z"))
    # A notice saved by an earlier version of the app, straight into the store
    from co5151_chat_store import Step, utcnow

    await layer.store.upsert_step(Step(id="old-n", conversation_id="c1", type="system_message", created_at=utcnow(),
                                       output="Server vừa khởi động lại nên phiên đã hết."))  # fmt: skip
    steps = (await layer.get_thread("c1"))["steps"]
    assert [s["type"] for s in steps] == ["user_message", "assistant_message"]
    assert "c1-n" not in [s.id for s in (await layer.store.get_conversation("c1")).steps]


def signed_in(user):
    """Run the next data-layer calls as if they came from `user`'s chat session."""
    context_var.set(ChainlitContext(HTTPSession(id="s2", thread_id="t", user=user, client_type="webapp")))


async def test_deleting_an_open_thread_and_chatting_on_keeps_it_owned(layer):
    """What the user hit: Chainlit does not set the owner again, so the next connection was refused."""
    user = await layer.create_user(User(identifier="sv001"))
    signed_in(user)
    await chat(layer, user.id)
    await layer.delete_thread("c1")
    await layer.create_step(message("c1-q2", "c1", "user_message", "Còn ngoại ngữ thì sao?", "2026-11-12T08:01:00Z"))
    thread = await layer.get_thread("c1")
    assert thread["userIdentifier"] == "sv001"
    assert await layer.get_thread_author("c1") == "sv001"


async def test_the_owner_comes_from_the_session_even_for_a_plain_user(layer):
    signed_in(User(identifier="sv002"))  # not yet a PersistedUser
    await layer.create_step(message("q", "c9", "user_message", "Xin chào", "2026-11-12T08:00:00Z"))
    assert await layer.get_thread_author("c9") == "sv002"


async def test_a_trace_is_saved_in_the_sessions_conversation_with_its_owner(layer):
    user = await layer.create_user(User(identifier="sv001"))
    signed_in(user)
    await layer.record_turn(Turn(trace_id="cd" * 16, conversation_id="c7", outcome="answer"))
    assert await layer.get_thread_author("c7") == "sv001"
    assert (await layer.store.get_turn("cd" * 16)).outcome == "answer"


async def test_an_ownerless_thread_left_by_an_older_version_is_hidden(layer):
    from co5151_chat_store import Step, utcnow

    await (await layer.ready()).upsert_step(
        Step(id="q", conversation_id="orphan", type="user_message", created_at=utcnow())
    )
    assert await layer.get_thread("orphan") is None
    assert await layer.get_thread_author("orphan") == ""
