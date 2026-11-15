"""The same behaviour from the SQL store and the in-memory store."""

import asyncio
from datetime import timedelta

import pytest

from co5151_backend.domain.conversation import ChatSettings, Conversation, Feedback, Message, MessageRole, utcnow
from co5151_backend.domain.errors import NotFound
from co5151_backend.domain.trace import Outcome, Span, Trace, Usage
from co5151_backend.infrastructure.persistence.memory import InMemoryChatRepository, InMemoryTraceRepository
from co5151_backend.infrastructure.persistence.sql import SqlChatRepository, SqlTraceRepository, UnsupportedDatabase

pytestmark = pytest.mark.anyio


@pytest.fixture(params=["sql", "memory"])
async def repos(request, tmp_path):
    if request.param == "memory":
        chats = InMemoryChatRepository()
        yield chats, InMemoryTraceRepository(chats)
        return
    chats = SqlChatRepository.from_url(f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}")
    await chats.create_schema()
    yield chats, SqlTraceRepository(chats)
    await chats.close()


def conversation(cid: str, owner: str = "sv001", seconds: int = 0, **kw) -> Conversation:
    at = utcnow() + timedelta(seconds=seconds)
    return Conversation(id=cid, owner_id=owner, created_at=at, updated_at=at, **kw)


def message(mid: str, cid: str, role=MessageRole.USER, seconds: int = 0, **kw) -> Message:
    return Message(id=mid, conversation_id=cid, role=role, content=f"text {mid}",
                   created_at=utcnow() + timedelta(seconds=seconds), **kw)  # fmt: skip


async def test_create_is_idempotent_for_the_owner_and_hidden_from_others(repos):
    chats, _ = repos
    first = await chats.create(conversation("c1", title="Hỏi", settings=ChatSettings("gemini", None)))
    again = await chats.create(conversation("c1", title="khác"))
    assert again.title == "Hỏi" == first.title and again.settings.provider == "gemini"
    with pytest.raises(NotFound):
        await chats.create(conversation("c1", owner="sv002"))
    assert await chats.get("c1", "sv002") is None
    assert await chats.update("c1", "sv002", title="x") is None
    assert await chats.delete("c1", "sv002") is False


async def test_messages_come_back_in_order_and_recent_is_the_tail(repos):
    chats, _ = repos
    await chats.create(conversation("c1"))
    for i in range(4):
        await chats.add_message(message(f"m{i}", "c1", MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT, i))
    got = await chats.get("c1", "sv001")
    assert [m.id for m in got.messages] == ["m0", "m1", "m2", "m3"]
    assert [m.id for m in await chats.recent_messages("c1", 2)] == ["m2", "m3"]


async def test_list_is_per_owner_most_recent_first_with_cursor_and_search(repos):
    chats, _ = repos
    for i in range(3):
        await chats.create(conversation(f"c{i}", seconds=i, title=f"Câu {i}"))
    await chats.create(conversation("x", owner="sv002"))
    page = await chats.list_by_owner("sv001", limit=2)
    assert [c.id for c in page.items] == ["c2", "c1"] and page.next_cursor == "c1"
    rest = await chats.list_by_owner("sv001", limit=2, cursor=page.next_cursor)
    assert [c.id for c in rest.items] == ["c0"] and rest.next_cursor is None
    assert [c.id for c in (await chats.list_by_owner("sv001", search="câu 1")).items] == ["c1"]


async def test_new_message_moves_the_conversation_to_the_top(repos):
    chats, _ = repos
    await chats.create(conversation("old", seconds=-10))
    await chats.create(conversation("new", seconds=-5))
    await chats.add_message(message("m", "old"))
    assert (await chats.list_by_owner("sv001")).items[0].id == "old"


async def test_feedback_only_on_own_assistant_messages(repos):
    chats, _ = repos
    await chats.create(conversation("c1"))
    await chats.add_message(message("q", "c1"))
    await chats.add_message(message("a", "c1", MessageRole.ASSISTANT, 1))
    assert await chats.set_feedback("q", "sv001", Feedback(1)) is False
    assert await chats.set_feedback("a", "sv002", Feedback(1)) is False
    assert await chats.set_feedback("a", "sv001", Feedback(0, "sai số tín chỉ")) is True
    answer = (await chats.get("c1", "sv001")).messages[1]
    assert answer.feedback == Feedback(0, "sai số tín chỉ")
    assert await chats.set_feedback("a", "sv001", None) is True
    assert (await chats.get("c1", "sv001")).messages[1].feedback is None


async def test_rename_settings_and_delete(repos):
    chats, traces = repos
    await chats.create(conversation("c1"))
    await chats.add_message(message("q", "c1"))
    await traces.save(Trace(trace_id="t" * 32, conversation_id="c1"))
    renamed = await chats.update("c1", "sv001", title="Mới", settings=ChatSettings("openai", "gpt-4.1-mini"))
    assert renamed.title == "Mới" and renamed.settings.model == "gpt-4.1-mini"
    assert await chats.delete("c1", "sv001") is True
    assert await chats.get("c1", "sv001") is None and await traces.get("t" * 32, "sv001") is None


async def test_trace_round_trip_is_owner_scoped(repos):
    chats, traces = repos
    await chats.create(conversation("c1"))
    trace = Trace(trace_id="a" * 32, conversation_id="c1", outcome=Outcome.REFUSE, steps=["REFUSE"],
                  tool_calls=["get_my_academic_summary"], citations=["Dieu_24"], verifier_rounds=2,
                  usage=Usage(10, 5), latency_ms=1200, llm="gemini/x", llm_error="LLMError: 429")  # fmt: skip
    await traces.save(trace)
    got = await traces.get("a" * 32, "sv001")
    assert got.outcome is Outcome.REFUSE and got.usage.total == 15 and got.llm_error == "LLMError: 429"
    assert got.steps == ["REFUSE"] and got.citations == ["Dieu_24"] and got.verifier_rounds == 2
    assert await traces.get("a" * 32, "sv002") is None


async def test_spans_are_saved_with_their_trace_owner_scoped_and_replaced(repos):
    chats, traces = repos
    await chats.create(conversation("c1"))
    later = Span(node="verifier", name="round 1", output={"status": "pass"}, start_ms=20, usage=Usage(30, 2))
    first = Span(node="planner", name="rules", input={"question": "q"}, start_ms=0, duration_ms=1)
    await traces.save(Trace(trace_id="s" * 32, conversation_id="c1"), [later, first])
    assert await traces.spans("s" * 32, "sv001") == [first, later]
    assert await traces.spans("s" * 32, "sv002") is None and await traces.spans("x" * 32, "sv001") is None
    await traces.save(Trace(trace_id="s" * 32, conversation_id="c1"), [first])
    assert await traces.spans("s" * 32, "sv001") == [first]
    await chats.delete("c1", "sv001")
    assert await traces.spans("s" * 32, "sv001") is None


async def test_trace_log_reads_every_owner_newest_first_with_question_and_answer(repos):
    chats, traces = repos
    await chats.create(conversation("c1"))
    await chats.create(conversation("c2", owner="sv002"))
    await chats.add_message(message("q1", "c1"))
    await chats.add_message(message("a1", "c1", MessageRole.ASSISTANT, seconds=1))
    older = Trace(trace_id="1" * 32, conversation_id="c1", user_message_id="q1", answer_message_id="a1",
                  created_at=utcnow())  # fmt: skip
    newer = Trace(trace_id="2" * 32, conversation_id="c2", error="boom", created_at=utcnow() + timedelta(seconds=5))
    await traces.save(older, [Span(node="planner", name="rules")])
    await traces.save(newer)
    assert [r.trace.trace_id for r in await traces.recent()] == ["2" * 32, "1" * 32]
    [mine] = await traces.recent(conversation_id="c1", limit=10)
    assert (mine.owner_id, mine.question, mine.answer, mine.spans) == ("sv001", "text q1", "text a1", [])
    found = await traces.find("1" * 32)
    assert [s.node for s in found.spans] == ["planner"] and found.trace.user_message_id == "q1"
    failed = await traces.find("2" * 32)
    assert (failed.owner_id, failed.question, failed.trace.error) == ("sv002", None, "boom")
    assert await traces.find("x" * 32) is None and len(await traces.recent(limit=1)) == 1


async def test_concurrent_creates_of_one_conversation_both_succeed(tmp_path):
    chats = SqlChatRepository.from_url(f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}")
    await chats.create_schema()
    results = await asyncio.gather(*(chats.create(conversation("c1")) for _ in range(5)))
    assert {c.id for c in results} == {"c1"}
    await chats.close()


def test_only_sqlite_and_postgres():
    with pytest.raises(UnsupportedDatabase):
        SqlChatRepository.from_url("mysql+aiomysql://u:p@h/db")
