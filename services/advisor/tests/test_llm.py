from unittest.mock import MagicMock

from co5151_advisor.agent import AdvisorAgent
from co5151_advisor.llm import CANARY_STRING, LLMClient, LLMResult
from co5151_advisor.regulations import RegulationDocument
from co5151_contracts import ok
from co5151_contracts.student import AcademicSummary
from co5151_eval.agent import Outcome


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


def test_llm_client_unavailable_without_key():
    client = LLMClient(api_key=None)
    assert not client.is_available
    assert client.generate("hello") is None


def test_llm_canary_leak_protection():
    mock_inner = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = f"Answer with leaked {CANARY_STRING} secret!"
    mock_inner.chat.completions.create.return_value.choices = [mock_choice]
    mock_inner.chat.completions.create.return_value.usage.prompt_tokens = 10
    mock_inner.chat.completions.create.return_value.usage.completion_tokens = 20

    client = LLMClient(api_key="test-key")
    client._client = mock_inner

    res = client.generate("prompt")
    assert res is not None
    assert CANARY_STRING not in res.text
    assert "secret!" in res.text


def test_advisor_agent_uses_llm_when_available():
    mock_svc = MagicMock()
    mock_svc.call.return_value = ok(_sample_summary())

    mock_reg = MagicMock()
    mock_reg.search.return_value = [RegulationDocument(id="Dieu_24", title="Quy chế", content="Nội dung quy chế")]

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.is_available = True
    mock_llm.generate.return_value = LLMResult(
        text="Theo dữ liệu học vụ, bạn đã tích lũy 113 tín chỉ và đủ điều kiện.",
        input_tokens=150,
        output_tokens=60,
    )

    agent = AdvisorAgent(mock_svc, mock_reg, llm_client=mock_llm)
    q = "Em có đủ điều kiện làm luận văn không?"
    resp = agent.answer(q, session_token="tok", history=[])

    assert resp.outcome is None
    assert "113 tín chỉ và đủ điều kiện" in resp.text
    calls = mock_llm.generate.call_count
    assert calls > 1
    assert resp.usage.input_tokens == 150 * calls
    assert resp.usage.output_tokens == 60 * calls


def test_advisor_agent_falls_back_when_llm_fails():
    mock_svc = MagicMock()
    mock_svc.call.return_value = ok(_sample_summary())

    mock_reg = MagicMock()
    mock_reg.search.return_value = [RegulationDocument(id="Dieu_24", title="Quy chế", content="Nội dung quy chế")]

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.is_available = True
    # Upstream failed (e.g. Insufficient account funds)
    mock_llm.generate.return_value = None

    agent = AdvisorAgent(mock_svc, mock_reg, llm_client=mock_llm)
    q = "Em có đủ điều kiện làm luận văn không?"
    resp = agent.answer(q, session_token="tok", history=[])

    assert resp.outcome == Outcome.ANSWER
    # Falls back gracefully to template synthesis
    assert "Đủ điều kiện" in resp.text
    assert "113" in resp.text
