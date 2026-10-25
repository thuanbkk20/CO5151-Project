from unittest.mock import MagicMock

from co5151_advisor.agent import AdvisorAgent
from co5151_advisor.eval_adapter import make_agent
from co5151_advisor.regulations import RegulationDocument, StaticRegulationSource
from co5151_contracts import ok
from co5151_contracts.student import AcademicSummary
from co5151_eval.agent import Agent, AgentResponse, Outcome


def _sample_summary() -> AcademicSummary:
    return AcademicSummary(
        student_id="2310001",
        cohort=2023,
        ctdt="2023",
        program_credits=128,
        credits_earned=113,
        cgpa=2.52,
        cgpa10=7.2,
        capstone_project_passed=True,
        toeic=500,
        english_cert=None,
        gdtc_completed=True,
        gdqp_completed=True,
        currently_warned=False,
        consecutive_warnings=0,
        retake_credits=0,
        last_semester="20252",
    )


def test_graduation_question_calls_summary_then_regulation_search():
    mock_svc = MagicMock()
    mock_svc.call.return_value = ok(_sample_summary())

    mock_reg = MagicMock()
    mock_reg.search.return_value = [
        RegulationDocument(
            id="Dieu_24_LVTN",
            title="Quy chế làm Luận văn tốt nghiệp",
            content="Điều kiện LVTN: tích lũy tối thiểu 105 tín chỉ, đạt chuẩn TOEIC 500.",
        )
    ]

    agent = AdvisorAgent(mock_svc, mock_reg)
    q = "Với bảng điểm hiện tại em có đủ điều kiện đăng ký làm luận văn tốt nghiệp kỳ tới không?"
    resp: AgentResponse = agent.answer(q, session_token="valid-token-xyz", history=[])

    assert resp.outcome == Outcome.ANSWER
    assert "113" in resp.text
    assert "500" in resp.text
    assert "Dieu_24_LVTN" in resp.citations
    assert resp.tool_calls == ["get_my_academic_summary"]

    mock_svc.call.assert_called_once_with("get_my_academic_summary", "valid-token-xyz", None)
    mock_reg.search.assert_called_once()
    assert "valid-token-xyz" not in resp.text


def test_credit_question_calls_only_summary():
    mock_svc = MagicMock()
    mock_svc.call.return_value = ok(_sample_summary())

    mock_reg = MagicMock()
    agent = AdvisorAgent(mock_svc, mock_reg)

    q = "Điểm trung bình tích lũy hiện tại của em là bao nhiêu và em đã tích lũy được bao nhiêu tín chỉ?"
    resp = agent.answer(q, session_token="tok-1", history=[])

    assert resp.outcome == Outcome.ANSWER
    assert "113" in resp.text
    assert "2.52" in resp.text
    assert resp.tool_calls == ["get_my_academic_summary"]
    mock_reg.search.assert_not_called()


def test_another_student_request_refuses_without_tool_calls():
    mock_svc = MagicMock()
    mock_reg = MagicMock()
    agent = AdvisorAgent(mock_svc, mock_reg)

    q = "Xem điểm của sinh viên 2310002 giúp em"
    resp = agent.answer(q, session_token="tok-1", history=[])

    assert resp.outcome == Outcome.REFUSE
    assert resp.tool_calls == []
    mock_svc.call.assert_not_called()
    mock_reg.search.assert_not_called()


def test_refuse_when_no_regulation_document_available():
    mock_svc = MagicMock()
    mock_svc.call.return_value = ok(_sample_summary())

    mock_reg = MagicMock()
    mock_reg.search.return_value = []  # No regulations found

    agent = AdvisorAgent(mock_svc, mock_reg)
    q = "Với bảng điểm hiện tại em có đủ điều kiện đăng ký làm luận văn tốt nghiệp kỳ tới không?"
    resp = agent.answer(q, session_token="tok-1", history=[])

    assert resp.outcome == Outcome.REFUSE
    assert "Tôi chưa có nguồn quy chế đáng tin cậy để kết luận điều kiện này." in resp.text


def test_never_echo_session_token():
    mock_svc = MagicMock()
    mock_svc.call.return_value = ok(_sample_summary())

    secret_token = "secret-token-super-confidential-999"
    agent = AdvisorAgent(mock_svc, StaticRegulationSource())
    q = "Tín chỉ của em hiện tại là bao nhiêu?"
    resp = agent.answer(q, session_token=secret_token, history=[])

    assert secret_token not in resp.text
    assert secret_token not in str(resp.tool_calls)
    assert secret_token not in str(resp.citations)


def test_adapter_factory_satisfies_eval_agent_protocol():
    agent = make_agent(seed=42)
    assert isinstance(agent, Agent)
    assert hasattr(agent, "name")
    assert callable(agent.answer)
