"""The backend's AskQuestion as an eval agent, on the real in-process services. No LLM: template answers."""

import pytest

from co5151_backend.infrastructure.llm import PROVIDERS
from co5151_eval.agent import Agent
from co5151_eval.backend_agent import make_agent, make_agent_no_verifier, regulation_ids
from co5151_eval.gold import RecordOracle
from co5151_eval.runner import run
from co5151_eval.tasks import Outcome, load_tasks

QUESTION = "Với bảng điểm hiện tại em có đủ điều kiện làm luận văn tốt nghiệp kỳ tới không?"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ["LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "STUDENT_MCP_TOKEN_SECRET",
                 "ADVISOR_VERIFIER", "ADVISOR_PLANNER_MODE"] + [p.key_env for p in PROVIDERS.values()]:  # fmt: skip
        monkeypatch.delenv(name, raising=False)


def test_student_question_reads_the_record_and_is_verified_without_llm():
    agent = make_agent()
    assert isinstance(agent, Agent)
    resp = agent.answer(QUESTION, session_token=RecordOracle().token("sv002"), history=[])
    assert "get_my_academic_summary" in resp.tool_calls
    assert resp.outcome is Outcome.ANSWER and resp.text
    assert resp.verifier_rounds == 1
    assert resp.usage.total == 0


def test_guest_gets_no_record_tool_and_baseline_skips_the_verifier():
    resp = make_agent_no_verifier().answer(QUESTION, session_token=None, history=[])
    assert not any(t.startswith("get_my_") for t in resp.tool_calls)
    assert resp.verifier_rounds is None


def test_history_is_seeded_and_describe_names_the_pipeline():
    history = [{"role": "user", "content": "Chào"}, {"role": "assistant", "content": "Chào em"}]
    resp = make_agent().answer("Điều kiện tốt nghiệp gồm những gì?", session_token=None, history=history)
    assert resp.text
    config = make_agent().describe()
    assert config["llm"] is None and config["verifier"] == "llm" and config["regulation_source"]


def test_regulation_lookup_returns_provision_ids():
    assert regulation_ids("Điều kiện xét công nhận tốt nghiệp")


@pytest.mark.parametrize("suite", ["tasks", "injection"])
def test_every_task_runs_without_error(suite):
    records = run(make_agent, load_tasks(suite=suite))
    assert [r.task_id for r in records if r.error] == []
