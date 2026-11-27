import pytest
from backend_fakes import GRADUATION, PASS, REFUSE, REVISE, UNVERIFIED, App, Regulations, ScriptedVerifier, Student

from co5151_backend.application.agents.advisor import prompts
from co5151_backend.application.usecases.ask import MAX_VERIFIER_ROUNDS
from co5151_backend.application.usecases.auth import AuthenticateOperator, SignIn
from co5151_backend.application.usecases.operator import OperatorTraces
from co5151_backend.application.usecases.provisions import ReadProvision, provision_of
from co5151_backend.domain.conversation import ChatSettings, Feedback, MessageRole
from co5151_backend.domain.errors import (
    AnswerFailed,
    InvalidCredentials,
    InvalidRequest,
    NotFound,
    Unauthenticated,
    Unavailable,
)
from co5151_backend.domain.principal import Role
from co5151_backend.domain.trace import Outcome
from co5151_backend.infrastructure.identity import DemoAccountDirectory
from co5151_contracts import ErrorCode

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


async def test_questions_are_limited_per_conversation_without_an_llm_call():
    app = App("Một", "Hai", "Ba", max_questions=3)
    principal, conv = await started(app)
    answers = [await app.ask.execute(principal, conv.id, f"Em đã tích lũy bao nhiêu tín chỉ? ({i})") for i in range(4)]
    assert [a.questions_left for a in answers] == [2, 1, 0, 0]
    assert answers[0].message.content == "Một\n\n(Hội thoại này còn 2 câu hỏi.)"
    assert answers[2].message.content.startswith("Ba\n\n(Đây là câu hỏi cuối")
    limited = answers[3]
    assert limited.message.content == prompts.limit_reached(3) and "đủ 3 câu hỏi" in limited.message.content
    assert (limited.trace.outcome, limited.trace.steps, limited.trace.usage.total) == (Outcome.LIMIT, ["LIMIT"], 0)
    assert len(app.model.calls) == 3 and await app.traces.get(limited.trace.trace_id, principal.user_id)
    saved = await app.conversations.get(principal, conv.id)
    assert len(saved.messages) == 8 and app.ask.questions_left(saved) == 0
    assert prompts.limit_reached(10) == prompts.LIMIT_REACHED
    _, other = await started(app)  # a new conversation starts again from 3
    assert app.ask.questions_left(await app.conversations.get(principal, other.id)) == 3


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


async def test_spans_show_what_each_node_received_and_returned():
    app = App("Nháp có G3-CANARY-7F3A.", "Bản sửa.", verifier=ScriptedVerifier(REVISE, PASS))
    principal, conv = await started(app)
    answer = await app.ask.execute(principal, conv.id, GRADUATION)
    spans = await app.conversations.spans(principal, answer.trace.trace_id)
    assert [(s.node, s.name) for s in spans] == [
        ("planner", "rules"), ("student_record", "get_my_academic_summary"), ("planner", "rules"),
        ("regulation", "search_regulations"), ("planner", "rules"), ("writer", "draft"), ("verifier", "round 1"),
        ("writer", "rewrite"), ("verifier", "round 2"),
    ]  # fmt: skip
    planner, student, _, regulation, _, draft, verify, rewrite, _ = spans
    assert planner.output == {"action": "SUMMARY", "by": "rule", "error": None}
    assert student.output["data"]["credits_earned"] == 113 and student.input["token"] == "(ẩn)"
    assert regulation.input["args"]["query"] == GRADUATION
    assert regulation.output["data"]["results"][0]["evidence"]["provision_id"] == "QD2933-2021-CL5.5"
    assert draft.output == {"text": "Nháp có .", "by": "fake/fake-1"} and draft.usage.total == 1100
    assert verify.output["status"] == "revise" and verify.input["draft"] == "Nháp có ."
    assert rewrite.input["verifier_issues"][0]["message"] == "Quy chế không nêu ngưỡng 105 tín chỉ."
    assert all(a.start_ms <= b.start_ms for a, b in zip(spans, spans[1:], strict=False))
    dumped = repr(spans)
    assert prompts.CANARY not in dumped and prompts.SYSTEM_PROMPT[:40] not in dumped
    assert not any(token in dumped for _, token in app.student.calls)
    other = app.sign_in.execute("sv002", "demo").principal
    with pytest.raises(NotFound):
        await app.conversations.spans(other, answer.trace.trace_id)


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
    *_, failed_span = await app.conversations.spans(principal, failed.value.trace_id)
    assert (failed_span.node, failed_span.error) == ("student_record", "RuntimeError: db down")


async def test_operator_reads_every_users_traces():
    app = App("Bạn đủ điều kiện.")
    principal, conv = await started(app)
    answer = await app.ask.execute(principal, conv.id, GRADUATION)
    operator = OperatorTraces(app.traces)
    [record] = await operator.recent(conversation_id=conv.id)
    assert (record.owner_id, record.question, record.answer) == ("sv001", GRADUATION, "Bạn đủ điều kiện.")
    detail = await operator.detail(answer.trace.trace_id)
    assert detail.spans[0].node == "planner" and detail.trace.trace_id == answer.trace.trace_id
    assert await operator.recent(conversation_id="khac") == []
    with pytest.raises(NotFound):
        await operator.detail("x" * 32)
    with pytest.raises(InvalidRequest):
        await operator.recent(limit=0)


def test_sign_in():
    app = App()
    assert app.sign_in.execute("sv001", "demo").principal.user_id == "sv001"
    with pytest.raises(InvalidCredentials):
        app.sign_in.execute("sv001", "wrong")
    first, second = app.sign_in.execute("khach", ""), app.sign_in.execute("KHACH", "x")
    assert first.principal.user_id != second.principal.user_id and first.principal.is_guest
    assert app.authenticate.execute(first.access_token) == first.principal


def test_guest_sign_in_can_be_turned_off():
    app = App()
    closed = SignIn(DemoAccountDirectory(), app.tokens, guest_login=False)
    for password in ("", "demo"):
        with pytest.raises(InvalidCredentials):
            closed.execute("khach", password)
    assert closed.execute("sv001", "demo").principal.user_id == "sv001"


def test_operator_token_is_checked_and_the_admin_api_is_off_without_one():
    operator = AuthenticateOperator("admin-token")
    operator.execute("admin-token")
    for wrong in ("", None, "admin-token2"):
        with pytest.raises(Unauthenticated):
            operator.execute(wrong)
    with pytest.raises(NotFound):
        AuthenticateOperator(None).execute("anything")


async def test_conversation_settings_feedback_and_ids_are_checked():
    app = App("x", "x")
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
    app.models.allowed = ["a", "b"]
    assert app.conversations.llm_choices() == (["fake"], "fake", {"fake": ["a", "b"]})
    with pytest.raises(InvalidRequest):
        await app.conversations.update(principal, conv.id, settings=ChatSettings("fake", "c"))
    with pytest.raises(InvalidRequest):
        await app.conversations.update(principal, conv.id, settings=ChatSettings(None, "c"))
    assert (await app.conversations.update(principal, conv.id, settings=ChatSettings(None, "b"))).settings.model == "b"
    app.models.allowed = ["a"]  # "b" retired: the conversation answers with the default model
    await app.ask.execute(principal, conv.id, GRADUATION)
    assert app.models.created[-1] == (None, None)
    await app.conversations.delete(principal, conv.id)
    with pytest.raises(NotFound):
        await app.conversations.delete(principal, conv.id)


async def test_read_provision_by_its_citation_id():
    read = ReadProvision(Regulations())
    p = await read.execute(" QD2933-2021-CL5.5 ")
    assert (p.id, p.title, p.source, p.pages, p.verified) == ("QD2933-2021-CL5.5", "Khoản 5.5", "HCMUT_QD2933_2021.pdf",
                                                              [7, 8], False)  # fmt: skip
    assert p.text == "5.5 Đăng ký các học phần tốt nghiệp"
    with pytest.raises(NotFound):
        await read.execute("QD-KHONG-CO")
    with pytest.raises(InvalidRequest):
        await read.execute("  ")
    with pytest.raises(InvalidRequest):
        await read.execute("x" * 161)
    with pytest.raises(Unavailable):
        await ReadProvision(Regulations(fail=ErrorCode.INTERNAL)).execute("QD2933-2021-CL5.5")


def test_provision_text_from_fragments_or_source_text():
    data = {"results": [{"id": "r", "evidence": {"source_text": "  Điều 1 ...  ", "warning": "bản nháp"}}]}
    p = provision_of(data)
    assert (p.id, p.title, p.source, p.pages, p.text, p.note) == ("r", "r", "", [], "Điều 1 ...", "bản nháp")
    fragments = [{"text": "trang 1 "}, {"text": ""}, {"text": "trang 2"}]
    two = {"results": [{"id": "r", "evidence": {"fragments": fragments}}]}
    assert provision_of(two).text == "trang 1\ntrang 2"
