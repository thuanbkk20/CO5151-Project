import pytest
from pydantic import ValidationError

from co5151_advisor.planner import Action, DecisionPlanner, Evidence, Plan


def test_models_are_frozen_and_forbid_extra():
    plan = Plan(action=Action.SUMMARY)
    assert plan.action == Action.SUMMARY
    with pytest.raises(ValidationError):
        Plan(action=Action.SUMMARY, extra_field="bad")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        plan.action = Action.RESPOND  # type: ignore[misc]

    ev = Evidence(credits_earned=100)
    assert ev.credits_earned == 100
    with pytest.raises(ValidationError):
        Evidence(invalid_key=123)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ev.credits_earned = 110  # type: ignore[misc]


def test_refuse_when_question_contains_another_student_id():
    planner = DecisionPlanner()
    assert planner.next_action("Xem điểm sinh viên 2310002 giúp em") == Action.REFUSE
    assert planner.next_action("Tra cứu điểm của sinh viên khác") == Action.REFUSE
    assert planner.next_action("Điểm của bạn khác có được không?") == Action.REFUSE


def test_clarify_vague_question():
    planner = DecisionPlanner()
    assert planner.next_action("Tư vấn giúp em") == Action.CLARIFY
    assert planner.next_action("Em cần tư vấn") == Action.CLARIFY
    assert planner.next_action("Giúp em với") == Action.CLARIFY


def test_warning_question_selects_warnings_then_respond():
    planner = DecisionPlanner()
    q = "Em có đang bị cảnh báo học tập không?"
    assert planner.next_action(q, evidence=None) == Action.WARNINGS
    ev = Evidence(warnings_checked=True, currently_warned=True)
    assert planner.next_action(q, evidence=ev) == Action.RESPOND


def test_graduation_question_sequence():
    planner = DecisionPlanner()
    q = "Với bảng điểm hiện tại em có đủ điều kiện đăng ký làm luận văn tốt nghiệp kỳ tới không?"
    # Step 1: SUMMARY
    assert planner.next_action(q, evidence=None) == Action.SUMMARY
    # Step 2: REGULATIONS
    ev_summary = Evidence(credits_earned=113, program_credits=128, ctdt="2023")
    assert planner.next_action(q, evidence=ev_summary) == Action.REGULATIONS
    # Step 3: RESPOND
    ev_full = Evidence(
        credits_earned=113,
        program_credits=128,
        ctdt="2023",
        regulations_checked=True,
        regulations=["Dieu_24_LVTN"],
    )
    assert planner.next_action(q, evidence=ev_full) == Action.RESPOND


def test_credit_summary_question_sequence():
    planner = DecisionPlanner()
    q = "Điểm trung bình tích lũy hiện tại của em là bao nhiêu và em đã tích lũy được bao nhiêu tín chỉ?"
    # Step 1: SUMMARY
    assert planner.next_action(q, evidence=None) == Action.SUMMARY
    # Step 2: RESPOND
    ev = Evidence(credits_earned=73, cgpa=2.95)
    assert planner.next_action(q, evidence=ev) == Action.RESPOND


def test_llm_decision_planner():
    from unittest.mock import MagicMock

    from co5151_advisor.llm import LLMResult
    from co5151_advisor.planner import LLMDecisionPlanner

    # 1. Fast-path refuse
    planner = LLMDecisionPlanner()
    assert planner.next_action("Tra cứu điểm của sinh viên 2310002") == Action.REFUSE

    # 2. When LLM is unavailable, falls back to DecisionPlanner
    mock_llm = MagicMock()
    mock_llm.is_available = False
    planner_fallback = LLMDecisionPlanner(llm_client=mock_llm)
    assert planner_fallback.next_action("Tư vấn giúp em") == Action.CLARIFY

    # 3. When LLM is available and returns valid action token
    mock_llm.is_available = True
    mock_llm.generate.return_value = LLMResult(text="REGULATIONS")
    planner_llm = LLMDecisionPlanner(llm_client=mock_llm)
    assert planner_llm.next_action("Điều kiện làm luận văn") == Action.REGULATIONS
