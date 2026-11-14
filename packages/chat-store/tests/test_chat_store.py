from datetime import timedelta

import pytest

from co5151_chat_store import ChatStore, Feedback, Step, Turn, database_url, new_trace_id, utcnow

pytestmark = pytest.mark.anyio


def step(step_id: str, conversation_id: str, type_: str = "user_message", seconds: int = 0, **kw) -> Step:
    created_at = utcnow() + timedelta(seconds=seconds)
    return Step(id=step_id, conversation_id=conversation_id, type=type_, created_at=created_at, **kw)


async def test_user_is_created_once_and_found_by_identifier(store):
    first = await store.get_or_create_user("sv001", {"guest": False})
    again = await store.get_or_create_user("sv001")
    assert first.id == again.id and again.metadata == {"guest": False}
    assert (await store.get_user("sv001")).id == first.id
    assert await store.get_user("sv999") is None


async def test_conversation_keeps_its_steps_in_order_with_owner(store):
    user = await store.get_or_create_user("sv001")
    await store.upsert_step(step("m1", "c1", seconds=0, output="Em đủ điều kiện chưa?"))
    await store.upsert_conversation("c1", user_id=user.id, title="Em đủ điều kiện chưa?")
    await store.upsert_step(step("m2", "c1", "assistant_message", seconds=1, output="Bạn đã tích lũy 92 tín chỉ."))

    conversation = await store.get_conversation("c1")
    assert (conversation.title, conversation.user_identifier) == ("Em đủ điều kiện chưa?", "sv001")
    assert [(s.id, s.type) for s in conversation.steps] == [("m1", "user_message"), ("m2", "assistant_message")]
    assert conversation.created_at.tzinfo is not None
    assert await store.conversation_owner("c1") == "sv001"
    assert await store.conversation_owner("missing") is None
    assert await store.get_conversation("missing") is None


async def test_upserting_a_step_replaces_it(store):
    await store.upsert_step(step("m1", "c1", "assistant_message", output="", metadata={"a": 1}))
    await store.upsert_step(step("m1", "c1", "assistant_message", output="xong", metadata={"trace_id": "t"}))
    [saved] = (await store.get_conversation("c1")).steps
    assert (saved.output, saved.metadata) == ("xong", {"trace_id": "t"})


async def test_update_only_changes_the_given_fields(store):
    user = await store.get_or_create_user("sv001")
    await store.upsert_conversation("c1", user_id=user.id, title="Câu đầu", metadata={"chat_settings": {"p": "g"}})
    await store.upsert_conversation("c1", metadata={"client_type": "webapp"})
    conversation = await store.get_conversation("c1")
    assert conversation.title == "Câu đầu" and conversation.user_id == user.id
    assert conversation.metadata == {"chat_settings": {"p": "g"}, "client_type": "webapp"}


async def test_each_user_only_lists_their_own_conversations_newest_first(store):
    sv1, sv2 = await store.get_or_create_user("sv001"), await store.get_or_create_user("sv002")
    for i in range(5):
        await store.upsert_conversation(f"a{i}", user_id=sv1.id, title=f"Câu hỏi {i}")
    await store.upsert_conversation("b0", user_id=sv2.id, title="Của người khác")
    await store.upsert_step(step("m", "a1"))  # activity moves a1 to the top

    first = await store.list_conversations(sv1.id, limit=3)
    assert [c.id for c in first.conversations] == ["a1", "a4", "a3"] and first.has_next
    rest = await store.list_conversations(sv1.id, limit=3, cursor="a3")
    assert [c.id for c in rest.conversations] == ["a2", "a0"] and not rest.has_next
    assert [c.id for c in (await store.list_conversations(sv1.id, search="câu hỏi 2")).conversations] == ["a2"]
    assert [c.id for c in (await store.list_conversations(sv2.id)).conversations] == ["b0"]


async def test_feedback_is_one_per_step_and_comes_back_with_the_step(store):
    await store.upsert_step(step("m2", "c1", "assistant_message"))
    first = await store.upsert_feedback(Feedback(id="f1", step_id="m2", value=1))
    second = await store.upsert_feedback(Feedback(id="f2", step_id="m2", value=0, comment="Sai số tín chỉ"))
    assert first == second == "f1"
    [saved] = (await store.get_conversation("c1")).steps
    assert (saved.feedback.value, saved.feedback.comment) == (0, "Sai số tín chỉ")
    assert await store.delete_feedback("f1") and not await store.delete_feedback("f1")


async def test_turn_trace_is_stored_per_answer(store):
    trace_id = new_trace_id()
    await store.record_turn(
        Turn(trace_id=trace_id, conversation_id="c1", user_message_id="m1", answer_message_id="m2", outcome="answer",
             tool_calls=["get_my_academic_summary"], citations=["QD2933-2021-CL5.5"], verifier_rounds=2,
             input_tokens=1200, output_tokens=150, latency_ms=4200, llm="gemini/gemini-3.1-flash-lite")
    )  # fmt: skip
    saved = await store.get_turn(trace_id)
    assert (saved.verifier_rounds, saved.citations, saved.created_at.tzinfo is not None) == (
        2,
        ["QD2933-2021-CL5.5"],
        True,
    )
    assert [t.trace_id for t in await store.list_turns("c1")] == [trace_id]


async def test_deleting_a_conversation_removes_everything_in_it(store):
    await store.upsert_step(step("m1", "c1"))
    await store.upsert_feedback(Feedback(id="f1", step_id="m1", value=1))
    await store.record_turn(Turn(trace_id=new_trace_id(), conversation_id="c1"))
    await store.delete_conversation("c1")
    assert await store.get_conversation("c1") is None
    assert await store.list_turns("c1") == []


async def test_schema_creation_is_idempotent_and_data_survives_a_restart(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'nested' / 'chat.db'}"
    first = ChatStore.from_url(url)
    await first.create_schema()
    await first.get_or_create_user("sv001")
    await first.close()
    second = ChatStore.from_url(url)
    await second.create_schema()
    assert await second.get_user("sv001") is not None
    await second.close()


def test_database_url_comes_from_the_environment(monkeypatch, tmp_path):
    default = tmp_path / "chat.db"
    monkeypatch.delenv("CHAT_DATABASE_URL", raising=False)
    assert database_url(default) == f"sqlite+aiosqlite:///{default.resolve()}"
    monkeypatch.setenv("CHAT_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/co5151")
    assert database_url(default) == "postgresql+asyncpg://u:p@db:5432/co5151"
    monkeypatch.setenv("CHAT_DATABASE_URL", "off")
    assert database_url(default) is None


def test_trace_ids_are_32_hex_characters_and_unique():
    ids = {new_trace_id() for _ in range(100)}
    assert len(ids) == 100 and all(len(i) == 32 and int(i, 16) >= 0 for i in ids)


async def test_first_message_and_thread_creation_can_race(store):
    """Chainlit saves the first message and creates the thread at the same time; neither write may be lost."""
    import asyncio

    user = await store.get_or_create_user("sv001")
    for i in range(20):
        conversation_id = f"race-{i}"
        await asyncio.gather(
            store.upsert_step(step(f"q{i}", conversation_id, output="Câu hỏi")),
            store.upsert_conversation(conversation_id, user_id=user.id, title="Câu hỏi"),
            store.record_turn(Turn(trace_id=new_trace_id(), conversation_id=conversation_id)),
        )
        conversation = await store.get_conversation(conversation_id)
        assert [s.id for s in conversation.steps] == [f"q{i}"], i
        assert (conversation.user_id, conversation.title) == (user.id, "Câu hỏi"), i


async def test_any_write_with_an_owner_creates_an_owned_conversation(store):
    sv1 = await store.get_or_create_user("sv001")
    await store.upsert_step(step("q", "by-step"), owner_id=sv1.id)
    await store.record_turn(Turn(trace_id=new_trace_id(), conversation_id="by-turn"), owner_id=sv1.id)
    assert await store.conversation_owner("by-step") == "sv001"
    assert await store.conversation_owner("by-turn") == "sv001"


async def test_an_owner_is_set_once_and_never_replaced(store):
    sv1, sv2 = await store.get_or_create_user("sv001"), await store.get_or_create_user("sv002")
    await store.upsert_step(step("q", "c1"))  # written without an owner, e.g. by an older version
    assert await store.conversation_owner("c1") is None
    await store.upsert_conversation("c1", user_id=sv1.id)
    await store.upsert_step(step("q2", "c1", seconds=1), owner_id=sv2.id)
    await store.upsert_conversation("c1", user_id=sv2.id, title="đổi chủ?")
    assert await store.conversation_owner("c1") == "sv001"
