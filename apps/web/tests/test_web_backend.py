from co5151_web import backend
from student_server.auth import TokenSigner

GRADUATION_Q = "Với bảng điểm hiện tại em có đủ điều kiện đăng ký làm luận văn tốt nghiệp kỳ tới không?"


def test_demo_account_signs_in_with_a_verifiable_token():
    ok, token = backend.sign_in("sv001", "demo")
    signer: TokenSigner = backend.student_service().signer
    assert ok and signer.verify(token).student_id == "2310001"


def test_an_authenticated_user_gets_a_new_token_after_a_restart_or_expiry():
    _, token = backend.sign_in("sv001", "demo")
    assert backend.token_is_fresh(token)
    refreshed = backend.refresh_token("sv001")
    claims = backend.student_service().signer.verify(refreshed)
    assert (claims.sub, claims.student_id) == ("sv001", "2310001")
    assert backend.refresh_token("khach") is None and backend.refresh_token("nobody") is None
    assert not backend.token_is_fresh(None) and not backend.token_is_fresh("garbage")


def test_a_token_about_to_expire_is_not_fresh():
    signer = backend.student_service().signer
    claims = {"sub": "sv001", "role": "student", "student_id": "2310001"}
    assert not backend.token_is_fresh(signer.issue(claims, ttl=backend.TOKEN_REFRESH_MARGIN_S - 5))
    assert backend.token_is_fresh(signer.issue(claims, ttl=backend.TOKEN_REFRESH_MARGIN_S + 60))


def test_wrong_password_is_rejected():
    assert backend.sign_in("sv001", "sai") == (False, None)


def test_guest_signs_in_without_a_record_token():
    assert backend.sign_in(backend.GUEST_USERNAME, "") == (True, None)


def test_only_providers_with_a_key_are_offered(monkeypatch):
    assert backend.configured_providers() == []
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    assert backend.configured_providers() == ["openai"]
    assert backend.default_provider(["openai"]) == "openai"
    assert backend.default_provider(["gemini", "openai"]) == "gemini"


def test_advisor_uses_the_chosen_provider_and_model():
    advisor = backend.new_advisor("openai", "my-model")
    assert advisor.llm_client.describe()["provider"] == "openai"
    assert advisor.llm_client.model == "my-model"


def test_ask_answers_from_the_logged_in_record_and_reports_details():
    _, token = backend.sign_in("sv001", "demo")
    reply = backend.ask(backend.new_advisor(), GRADUATION_Q, token=token, history=[])
    assert "102" in reply.text
    assert "get_my_academic_summary" in reply.details["tool_calls"]
    assert reply.details["llm"] == "gemini/gemini-3.5-flash-lite"
    assert "**Tool đã gọi:** get_my_academic_summary" in backend.details_markdown(reply.details)


def test_details_report_how_many_times_the_verifier_checked_the_answer(monkeypatch):
    _, token = backend.sign_in("sv001", "demo")
    reply = backend.ask(backend.new_advisor(), GRADUATION_Q, token=token, history=[])
    assert reply.details["verifier_rounds"] == 1
    assert "**Verifier:** 1 lượt kiểm" in backend.details_markdown(reply.details)

    monkeypatch.setenv("ADVISOR_VERIFIER", "off")
    reply = backend.ask(backend.new_advisor(), GRADUATION_Q, token=token, history=[])
    assert reply.details["verifier_rounds"] is None
    assert "**Verifier:** không kiểm" in backend.details_markdown(reply.details)


def test_every_turn_gets_a_trace_id_shown_in_the_details():
    _, token = backend.sign_in("sv001", "demo")
    first = backend.ask(backend.new_advisor(), GRADUATION_Q, token=token, history=[])
    second = backend.ask(backend.new_advisor(), GRADUATION_Q, token=token, history=[], trace_id="ab" * 16)
    assert len(first.details["trace_id"]) == 32 and second.details["trace_id"] == "ab" * 16
    assert f"**Trace ID:** `{'ab' * 16}`" in backend.details_markdown(second.details)


def test_turn_record_carries_the_trace_and_its_cost():
    _, token = backend.sign_in("sv001", "demo")
    reply = backend.ask(backend.new_advisor(), GRADUATION_Q, token=token, history=[])
    turn = backend.to_turn(reply.details, conversation_id="c1", user_message_id="m1", answer_message_id="m2")
    assert (turn.trace_id, turn.conversation_id, turn.answer_message_id) == (reply.details["trace_id"], "c1", "m2")
    assert turn.tool_calls == reply.details["tool_calls"] and turn.verifier_rounds == 1
    assert turn.latency_ms == round(reply.details["seconds"] * 1000)


def test_guest_question_does_not_touch_the_student_record():
    reply = backend.ask(
        backend.new_advisor(), "Điều kiện để được xét công nhận tốt nghiệp gồm những gì?", token=None, history=[]
    )
    assert reply.details["tool_calls"] == ["search_regulations"]


def test_only_recent_history_is_passed_on():
    seen = {}

    class Recorder:
        llm_client = None

        def answer(self, question, *, session_token, history):
            seen["history"] = history
            return backend.new_advisor().answer(question, session_token=session_token, history=[])

    history = [{"role": "user", "content": str(i)} for i in range(30)]
    backend.ask(Recorder(), "Xin chào", token=None, history=history)
    assert seen["history"] == history[-backend.HISTORY_TURNS :]
