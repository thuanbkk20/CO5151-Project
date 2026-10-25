import json

import pytest

from co5151_eval.agent import AgentResponse, Usage
from co5151_eval.gold import RecordOracle
from co5151_eval.runner import run, summarize, write_report
from co5151_eval.tasks import load_tasks


class Scripted:
    name = "scripted"

    def __init__(self, table):
        self.table = table
        self.tokens = []

    def answer(self, question, *, session_token, history):
        self.tokens.append(session_token)
        resp = self.table.get(question)
        if isinstance(resp, Exception):
            raise resp
        return resp or AgentResponse(text="Theo quy chế ...", usage=Usage(input_tokens=10, output_tokens=5))


@pytest.fixture(scope="module")
def tasks():
    return {t.id: t for t in load_tasks()}


@pytest.fixture(scope="module")
def oracle():
    return RecordOracle()


def test_harness_passes_the_task_users_token(tasks, oracle):
    agent = Scripted({})
    run(lambda seed: agent, [tasks["P01"], tasks["B01"]], oracle=oracle)
    claims = oracle.service.signer.verify(agent.tokens[0])
    assert claims.student_id == "2310001" and agent.tokens[1] is None


def test_agent_crash_is_a_failed_record(tasks, oracle):
    agent = Scripted({tasks["B01"].question: RuntimeError("boom")})
    [rec] = run(lambda seed: agent, [tasks["B01"]], oracle=oracle)
    assert not rec.passed and rec.error == "RuntimeError: boom"


def test_summary_metrics(tasks, oracle):
    p08, o02 = tasks["P08"], tasks["O02"]
    agent = Scripted({
        p08.question: AgentResponse(text="ĐTBTL 2,85, đã tích lũy 66 tín chỉ."),
        o02.question: AgentResponse(text="Bạn ấy có ĐTBTL 2.22."),
    })  # fmt: skip
    records = run(lambda seed: agent, [p08, o02], seeds=[0, 1], oracle=oracle)
    s = summarize(records)
    assert s["by_group"]["personal"]["pass_rate"] == 1.0
    assert s["by_group"]["out_of_scope"]["strict_refusal_rate"] == 0.0
    assert s["overall"]["leaks"] == 2 and s["pass_rate_by_seed"] == [0.5, 0.5] and s["pass_rate_std"] == 0.0
    assert s["by_group"]["missing_info"]["n"] == 0


def test_write_report(tmp_path, tasks, oracle):
    records = run(lambda seed: Scripted({}), [tasks["B01"]], oracle=oracle)
    write_report(records, tmp_path, "smoke", {"agent": "scripted"})
    assert len((tmp_path / "results.jsonl").read_text().splitlines()) == 1
    assert json.loads((tmp_path / "summary.json").read_text())["agent"] == "scripted"
    assert "| **Tổng** |" in (tmp_path / "summary.md").read_text()


def test_ungradable_tasks_are_excluded_from_pass_rate(tasks, oracle):
    s = summarize(run(lambda seed: Scripted({}), [tasks["B01"]], oracle=oracle))
    assert s["overall"]["pass_rate"] is None and s["overall"]["needs_human"] == 1


class Remembering:
    name = "remembering"

    def __init__(self):
        self.seen: list[str] = []

    def answer(self, question, *, session_token, history):
        self.seen.append(question)
        return AgentResponse(text=f"đã thấy {len(self.seen)} câu")


def test_every_task_gets_a_fresh_agent_so_no_state_leaks_between_tasks():
    tasks = load_tasks()[:3]
    built = []

    def factory(seed):
        built.append(Remembering())
        return built[-1]

    records = run(factory, tasks, seeds=[0, 1])
    assert len(built) == len(tasks) * 2
    assert {r.text for r in records} == {"đã thấy 1 câu"}
