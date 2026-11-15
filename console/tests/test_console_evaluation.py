import pytest
from console_fakes import FakeBackend

from co5151_console.adapters.backend_agent import HttpAnswerAgent
from co5151_console.adapters.sqlite_store import SqliteStore
from co5151_console.models import InvalidInput
from co5151_console.services.evaluation import Evaluation
from co5151_console.services.question_sets import QuestionSets, TaskForm

FACTS = '[{"field": "remaining_credits", "value": 15, "mention": ["15"]}]'


def setup(tmp_path, backend: FakeBackend, background=lambda work: work()):
    store = SqliteStore(tmp_path / "console.db")
    sets = QuestionSets(store)
    set_id = sets.create("Bộ thử")
    sets.save_task(set_id, TaskForm(id="P01", group="personal", question="Em còn bao nhiêu tín chỉ?",
                                    expected="answer", user="sv001", facts=FACTS))  # fmt: skip
    sets.save_task(set_id, TaskForm(id="P02", group="personal", question="Hỏng", expected="answer", user="sv002"))
    agent = HttpAnswerAgent("http://backend", "demo", transport=backend.transport())
    return Evaluation(store, store, agent, background=background), set_id, store


def test_a_run_scores_each_answer_like_the_eval_cli(tmp_path):
    backend = FakeBackend(answers={"Em còn bao nhiêu tín chỉ?": "Em còn 15 tín chỉ."}, fail_questions=("Hỏng",))
    evaluation, set_id, _ = setup(tmp_path, backend)
    report = evaluation.report(evaluation.start(set_id))
    assert (report.run.status, report.run.done, report.run.total) == ("done", 2, 2)
    ok, failed = report.results
    assert (ok.task_id, ok.trace_id, ok.record.passed, ok.record.facts_hit) == ("P01", "t1", True, 1)
    assert (failed.trace_id, failed.record.passed) == ("t-failed", False) and "backend 500" in failed.record.error
    assert report.overall["n"] == 2 and report.overall["pass_rate"] == 0.5 and report.overall["errors"] == 1
    assert list(report.by_group) == ["personal"] and backend.logins == ["sv001", "sv002"]


def test_one_run_at_a_time_and_interrupted_runs(tmp_path):
    pending = []
    evaluation, set_id, store = setup(tmp_path, FakeBackend(), background=pending.append)
    run_id = evaluation.start(set_id)
    assert evaluation.running().id == run_id and evaluation.report(run_id).overall == {}
    with pytest.raises(InvalidInput, match="chưa xong"):
        evaluation.start(set_id)
    store.interrupt_running()
    assert evaluation.report(run_id).run.status == "interrupted" and evaluation.running() is None
    with pytest.raises(InvalidInput, match="chưa có câu nào"):
        evaluation.start(QuestionSets(store).create("Rỗng"))
