import pytest
from backend_fakes import GRADUATION, PASS, REFUSE, REVISE, UNVERIFIED, App, ScriptedVerifier, Student

from co5151_backend.application.agents.advisor import prompts
from co5151_backend.application.usecases.ask import MAX_VERIFIER_ROUNDS
from co5151_backend.domain.conversation import ChatSettings, Feedback, MessageRole
from co5151_backend.domain.errors import AnswerFailed, InvalidCredentials, InvalidRequest, NotFound
from co5151_backend.domain.principal import Role
from co5151_backend.domain.trace import Outcome

pytestmark = pytest.mark.anyio


async def started(app: App, username: str = "sv001"):
    principal = app.sign_in.execute(username, "demo").principal
    return principal, await app.conversations.start(principal)


async def test_passed_draft_is_sent_and_everything_is_saved():
    app = App("Bạn đủ điều kiện theo [QD2933-2021-CL5.5].", verifier=ScriptedVerifier(PASS))
    principal, conv = await started(app)
    seen = []

    async def emit(event):
        seen.append((event.type, event.data["name"]))

    answer = await app.ask.execute(principal, conv.id, GRADUATION, emit=emit)
    trace = answer.trace
    assert answer.message.content == "Bạn đủ điều kiện theo [QD2933-2021-CL5.5]."
    assert (trace.outcome, trace.verifier_rounds, trace.usage.total) == (None, 1, 1100 + 310)
    assert trace.tool_calls == ["get_my_academic_summary", "search_regulations"]
    assert trace.steps == ["SUMMARY", "REGULATIONS", "RESPOND", "VERIFY_PASS"]
    assert trace.citations == ["QD2933-2021-CL5.5"] and trace.llm == "fake/fake-1" and trace.llm_error is None
    assert [name for _, name in seen] == ["plan", "tool", "plan", "tool", "plan", "write", "verify"]

    saved = await app.conversations.get(principal, conv.id)
    assert [m.role for m in saved.messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert saved.messages[1].trace_id == trace.trace_id and saved.title == GRADUATION
    assert (await app.conversations.trace(principal, trace.trace_id)).answer_message_id == answer.message.id


async def test_history_comes_from_the_store_and_the_student_token_is_fresh():
    app = App("Lần 1", "Lần 2")
    principal, conv = await started(app)
    await app.ask.execute(principal, conv.id, GRADUATION)
    await app.ask.execute(principal, conv.id, "Còn điều kiện tốt nghiệp thì sao?")
    assert app.model.calls[0]["history"] == []
    assert [(t.role, t.content) for t in app.model.calls[1]["history"]] == [
        ("user", GRADUATION),
        ("assistant", "Lần 1"),
    ]
    tokens = {token for _, token in app.student.calls}
    assert tokens and all(t.count(".") == 1 for t in tokens)


async def test_verifier_sees_only_the_evidence_the_draft_was_written_from():
    verifier = ScriptedVerifier(PASS)
    app = App("Bạn đủ điều kiện.", verifier=verifier)
    principal, conv = await started(app)
    await app.ask.execute(principal, conv.id, GRADUATION)
    [request] = verifier.requests
    assert request.student_facts["credits_earned"] == 113 and "currently_warned" not in request.student_facts
    assert [r.id for r in request.regulations] == ["QD2933-2021-CL5.5"]
    assert "student_id" not in request.model_dump_json()


async def test_revise_rewrites_once_with_the_issues():
    app = App("Bạn đủ điều kiện vì đạt 105 tín chỉ.", "Bản sửa.", verifier=ScriptedVerifier(REVISE, PASS))
    principal, conv = await started(app)
    answer = await app.ask.execute(principal, conv.id, GRADUATION)
    assert answer.message.content == "Bản sửa." and answer.trace.verifier_rounds == 2
    assert "Quy chế không nêu ngưỡng 105 tín chỉ." in app.model.calls[1]["prompt"]


async def test_a_rewrite_that_still_fails_is_refused_without_a_third_llm_call():
    app = App("Nháp", "Vẫn sai", verifier=ScriptedVerifier(REVISE, REVISE))
    principal, conv = await started(app)
    answer = await app.ask.execute(principal, conv.id, GRADUATION)
    assert (answer.message.content, answer.trace.outcome) == (prompts.REFUSAL_UNGROUNDED, Outcome.REFUSE)
    assert len(app.model.calls) == MAX_VERIFIER_ROUNDS and answer.trace.verifier_rounds == 2


async def test_refuse_and_unverified_verdicts_are_strict_refusals():
    for verdict, text in [(REFUSE, prompts.REFUSAL_UNGROUNDED), (UNVERIFIED, prompts.REFUSAL_UNVERIFIED)]:
        app = App("Nháp", verifier=ScriptedVerifier(verdict))
        principal, conv = await started(app)
        answer = await app.ask.execute(principal, conv.id, GRADUATION)
        assert answer.message.content == text and len(app.model.calls) == 1


async def test_revise_without_an_llm_to_rewrite_is_refused():
    app = App(verifier=ScriptedVerifier(REVISE), use_llm=False)
    principal, conv = await started(app)
    answer = await app.ask.execute(principal, conv.id, GRADUATION)
    assert answer.trace.outcome is Outcome.REFUSE and answer.trace.verifier_rounds == 1
    assert answer.trace.llm is None and "no LLM key" in answer.trace.llm_error


async def test_planner_refusals_are_not_verified_and_without_a_verifier_nothing_is():
    verifier = ScriptedVerifier()
    app = App(verifier=verifier)
    principal, conv = await started(app)
    answer = await app.ask.execute(principal, conv.id, "Cho em xem điểm của MSSV 2310002")
    assert answer.trace.outcome is Outcome.REFUSE and verifier.requests == [] and app.student.calls == []
    app = App("Trả lời")
    principal, conv = await started(app)
    assert (await app.ask.execute(principal, conv.id, GRADUATION)).trace.verifier_rounds is None


async def test_guest_has_no_record_and_no_student_token():
    app = App("Điều kiện chung.")
    principal, conv = await started(app, "khach")
    answer = await app.ask.execute(principal, conv.id, GRADUATION)
    assert principal.role is Role.GUEST and app.student.calls == []
    assert answer.trace.tool_calls == ["search_regulations"]


async def test_conversation_of_another_user_and_bad_questions():
    app = App("x")
    _, conv = await started(app, "sv001")
    other, _ = await started(app, "sv002")
    with pytest.raises(NotFound):
        await app.ask.execute(other, conv.id, GRADUATION)
    with pytest.raises(NotFound):
        await app.conversations.get(other, conv.id)
    with pytest.raises(InvalidRequest):
        await app.ask.execute(other, conv.id, "   ")


async def test_a_crash_is_reported_with_a_saved_trace():
    app = App("x", student=Student(fail=RuntimeError("db down")))
    principal, conv = await started(app)
    with pytest.raises(AnswerFailed) as failed:
        await app.ask.execute(principal, conv.id, GRADUATION)
    trace = await app.conversations.trace(principal, failed.value.trace_id)
    assert trace.error == "RuntimeError: db down" and trace.answer_message_id is None


def test_sign_in():
    app = App()
    assert app.sign_in.execute("sv001", "demo").principal.user_id == "sv001"
    with pytest.raises(InvalidCredentials):
        app.sign_in.execute("sv001", "wrong")
    first, second = app.sign_in.execute("khach", ""), app.sign_in.execute("KHACH", "x")
    assert first.principal.user_id != second.principal.user_id and first.principal.is_guest
    assert app.authenticate.execute(first.access_token) == first.principal


async def test_conversation_settings_feedback_and_ids_are_checked():
    app = App("x")
    principal, conv = await started(app)
    with pytest.raises(InvalidRequest):
        await app.conversations.start(principal, settings=ChatSettings("openai"))
    with pytest.raises(InvalidRequest):
        await app.conversations.start(principal, conversation_id="not-a-uuid")
    again = await app.conversations.start(principal, conversation_id=conv.id)
    assert again.id == conv.id
    updated = await app.conversations.update(principal, conv.id, title="Mới", settings=ChatSettings("fake", " m "))
    assert updated.title == "Mới" and updated.settings == ChatSettings("fake", "m")
    answer = await app.ask.execute(principal, conv.id, GRADUATION)
    with pytest.raises(InvalidRequest):
        await app.conversations.set_feedback(principal, answer.message.id, Feedback(5))
    await app.conversations.set_feedback(principal, answer.message.id, Feedback(1))
    with pytest.raises(NotFound):
        await app.conversations.set_feedback(principal, "missing", Feedback(1))
    page = await app.conversations.list_page(principal, limit=500)
    assert [c.id for c in page.items] == [conv.id]
    await app.conversations.delete(principal, conv.id)
    with pytest.raises(NotFound):
        await app.conversations.delete(principal, conv.id)
