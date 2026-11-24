"""Evaluation runs: ask every task of a question set through the backend, score each answer with `co5151_eval`,
keep one Record per task; the metrics are `co5151_eval.runner.summarize`, the same as `co5151-eval run`.

A run goes on in the background (one at a time, every answer costs LLM calls); its page shows the results so far.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from co5151_eval.agent import AgentResponse, Usage
from co5151_eval.runner import Record, summarize
from co5151_eval.scoring import score
from co5151_eval.tasks import Outcome, Task

from ..models import InvalidInput, Run, RunResult
from ..ports import AgentAnswer, AnswerAgent, QuestionSetStore, RunStore

# Planner (rules first, an LLM only when they cannot decide) + writer + Verifier + one rewrite + its check
MAX_LLM_CALLS_PER_TASK = 5
Background = Callable[[Callable[[], None]], None]


def in_a_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="evaluation-run", daemon=True).start()


@dataclass(frozen=True)
class RunReport:
    run: Run
    results: list[RunResult]
    overall: dict[str, Any] = field(default_factory=dict)
    by_group: dict[str, dict[str, Any]] = field(default_factory=dict)


def response_of(answer: AgentAnswer) -> AgentResponse:
    """The answer as `co5151_eval` scores it; read the same way as the in-process backend agent of the eval."""
    trace = answer.trace or {}
    return AgentResponse(
        text=answer.text,
        outcome=Outcome(trace["outcome"]) if trace.get("outcome") else Outcome.ANSWER,
        citations=trace.get("citations") or [],
        tool_calls=trace.get("tool_calls") or [],
        usage=Usage(input_tokens=trace.get("input_tokens") or 0, output_tokens=trace.get("output_tokens") or 0),
        verifier_rounds=trace.get("verifier_rounds"),
    )


def record_of(task: Task, answer: AgentAnswer, latency_s: float) -> Record:
    resp = response_of(answer)
    s = score(task, resp)
    return Record(task.id, task.group.value, 0, round(latency_s, 4), resp.usage.total, s.outcome.value, s.outcome_ok,
                  s.facts_hit, s.facts_total, s.citations_hit, s.citations_total, s.forbidden_hits,
                  False if answer.error else s.passed, resp.tool_calls, resp.text, answer.error, resp.citations,
                  resp.verifier_rounds)  # fmt: skip


class Evaluation:
    def __init__(
        self, sets: QuestionSetStore, runs: RunStore, agent: AnswerAgent, background: Background = in_a_thread
    ):
        self._sets = sets
        self._runs = runs
        self._agent = agent
        self._background = background

    def runs(self) -> list[Run]:
        return self._runs.list_runs()

    def running(self) -> Run | None:
        return next((r for r in self._runs.list_runs() if r.status == "running"), None)

    def start(self, set_id: int) -> int:
        """Raises InvalidInput: no such set, an empty set, or a run still going."""
        question_set = self._sets.get_set(set_id)
        if question_set is None or not question_set.tasks:
            raise InvalidInput("Bộ câu hỏi không có hoặc chưa có câu nào.")
        if (busy := self.running()) is not None:
            raise InvalidInput(f"Lần chạy #{busy.id} chưa xong; đợi xong rồi chạy tiếp.")
        run_id = self._runs.create_run(question_set.name, len(question_set.tasks))
        self._background(lambda: self._run(run_id, question_set.tasks))
        return run_id

    def _run(self, run_id: int, tasks: list[Task]) -> None:
        try:
            for task in tasks:
                if task.history:  # the API cannot insert earlier turns into a conversation
                    answer, latency = AgentAnswer("", None, "câu có history: API không chèn được lượt cũ"), 0.0
                else:
                    start = time.perf_counter()
                    answer = self._agent.answer(task.question, user=task.user)
                    latency = time.perf_counter() - start
                trace_id = (answer.trace or {}).get("trace_id")
                self._runs.add_result(run_id, task.id, task.question, trace_id, record_of(task, answer, latency))
        except Exception as e:  # keep the run's page honest instead of "running" forever
            self._runs.finish_run(run_id, "failed", f"{type(e).__name__}: {e}")
            raise
        self._runs.finish_run(run_id, "done")

    def report(self, run_id: int) -> RunReport | None:
        run = self._runs.get_run(run_id)
        if run is None:
            return None
        results = self._runs.results(run_id)
        if not results:
            return RunReport(run, results)
        summary = summarize([r.record for r in results])
        by_group = {g: m for g, m in summary["by_group"].items() if m["n"]}
        return RunReport(run, results, summary["overall"], by_group)
