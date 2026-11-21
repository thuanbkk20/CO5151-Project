"""What the console keeps: question sets of evaluation tasks (the `co5151_eval` Task model) and evaluation runs
(one `co5151_eval` Record per task, so the metrics are the same as `co5151-eval run`)."""

from dataclasses import dataclass, field

from co5151_eval.runner import Record
from co5151_eval.tasks import Task


class InvalidInput(ValueError):
    """A form value the console cannot accept; `str(e)` is shown next to the form."""


@dataclass(frozen=True)
class QuestionSetSummary:
    id: int
    name: str
    size: int
    created_at: str


@dataclass(frozen=True)
class QuestionSet:
    id: int
    name: str
    created_at: str
    tasks: list[Task] = field(default_factory=list)

    def task(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)


@dataclass(frozen=True)
class Run:
    id: int
    set_name: str
    status: str  # running | done | failed | interrupted
    total: int
    done: int
    created_at: str
    finished_at: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    task_id: str
    question: str
    trace_id: str | None
    record: Record
