from co5151_web import backend
from student_server.auth import TokenSigner

GRADUATION_Q = "Với bảng điểm hiện tại em có đủ điều kiện đăng ký làm luận văn tốt nghiệp kỳ tới không?"


def test_demo_account_signs_in_with_a_verifiable_token():
    ok, token = backend.sign_in("sv001", "demo")
    signer: TokenSigner = backend.student_service().signer
    assert ok and signer.verify(token).student_id == "2310001"


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
