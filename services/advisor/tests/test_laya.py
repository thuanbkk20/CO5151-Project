from unittest.mock import MagicMock

from co5151_advisor.agent import AdvisorAgent
from co5151_advisor.planner import Action, DecisionPlanner, LayaDecisionPlanner


def test_laya_planner_guardrail_refuse():
    planner = LayaDecisionPlanner()
    assert planner.next_action("Xem điểm sinh viên 2310002 giúp em") == Action.REFUSE
    assert planner.next_action("Xem kết quả học tập của sinh viên khác") == Action.REFUSE


def test_laya_planner_fallback_on_unreachable_server():
    planner = LayaDecisionPlanner(server_url="http://127.0.0.1:9999/unreachable", timeout=0.1)
    # Falls back smoothly to DecisionPlanner
    assert planner.next_action("Tư vấn giúp em") == Action.CLARIFY
    assert planner.next_action("Em có bị cảnh báo học tập không?") == Action.WARNINGS


def test_advisor_agent_mode_switch(monkeypatch):
    mock_svc = MagicMock()

    # Default mode is rule
    monkeypatch.delenv("ADVISOR_PLANNER_MODE", raising=False)
    agent_default = AdvisorAgent(mock_svc)
    assert isinstance(agent_default.planner, DecisionPlanner)

    # Set mode to laya
    monkeypatch.setenv("ADVISOR_PLANNER_MODE", "laya")
    agent_laya = AdvisorAgent(mock_svc)
    assert isinstance(agent_laya.planner, LayaDecisionPlanner)

    # Explicit planner injection overrides env
    custom_planner = DecisionPlanner()
    agent_custom = AdvisorAgent(mock_svc, planner=custom_planner)
    assert agent_custom.planner is custom_planner


def test_laya_live_prediction_if_server_active():
    planner = LayaDecisionPlanner()
    action = planner.next_action("Với bảng điểm hiện tại em có đủ điều kiện làm luận văn không?")
    # Either predicted from live Laya (e.g. SUMMARY) or fell back to SUMMARY
    assert action in (Action.SUMMARY, Action.REGULATIONS, Action.RESPOND)
