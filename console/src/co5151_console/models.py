"""What the console keeps: question sets of evaluation tasks (the `co5151_eval` Task model)."""

from dataclasses import dataclass, field

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
