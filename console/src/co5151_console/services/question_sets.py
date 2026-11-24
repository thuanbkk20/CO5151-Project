"""Question sets: create, import the default 24 tasks, add or edit a task from the form, delete."""

import json
from dataclasses import dataclass

from pydantic import ValidationError

from co5151_eval.tasks import Group, Outcome, Task, load_tasks

from ..models import InvalidInput, QuestionSet, QuestionSetSummary
from ..ports import QuestionSetStore

DEFAULT_SET_NAME = "Bộ mặc định (eval/tasks.json)"
GROUPS = [g.value for g in Group]
OUTCOMES = [o.value for o in Outcome]


@dataclass(frozen=True)
class TaskForm:
    """The task form as typed: every field is text; lists are one item per line."""

    id: str
    group: str
    question: str
    expected: str
    user: str = ""
    also_accept: tuple[str, ...] = ()
    citations: str = ""
    forbidden: str = ""
    facts: str = ""  # JSON list of {"field", "value", "mention"}
    reference_answer: str = ""
    notes: str = ""

    @classmethod
    def of(cls, task: Task) -> "TaskForm":
        facts = json.dumps([f.model_dump() for f in task.facts], ensure_ascii=False, indent=2) if task.facts else ""
        return cls(id=task.id, group=task.group.value, question=task.question, expected=task.expected.value,
                   user=task.user or "", also_accept=tuple(o.value for o in task.also_accept),
                   citations="\n".join(task.citations), forbidden="\n".join(task.forbidden), facts=facts,
                   reference_answer=task.reference_answer, notes=task.notes)  # fmt: skip

    def to_task(self) -> Task:
        try:
            facts = json.loads(self.facts) if self.facts.strip() else []
        except ValueError as e:
            raise InvalidInput(f"Facts không phải JSON hợp lệ: {e}") from e
        try:
            return Task(
                id=self.id.strip().upper(),
                group=self.group,
                question=self.question.strip(),
                user=self.user.strip() or None,
                expected=self.expected,
                also_accept=list(self.also_accept),
                facts=facts,
                citations=_lines(self.citations),
                forbidden=_lines(self.forbidden),
                reference_answer=self.reference_answer.strip(),
                notes=self.notes.strip(),
            )
        except ValidationError as e:
            raise InvalidInput("; ".join(_message(err) for err in e.errors())) from e


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _message(error: dict) -> str:
    where = ".".join(str(p) for p in error.get("loc", ()))
    return f"{where}: {error.get('msg')}" if where else str(error.get("msg"))


class QuestionSets:
    def __init__(self, store: QuestionSetStore):
        self._store = store

    def all(self) -> list[QuestionSetSummary]:
        return self._store.list_sets()

    def get(self, set_id: int) -> QuestionSet | None:
        return self._store.get_set(set_id)

    def create(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise InvalidInput("Tên bộ câu hỏi không được trống.")
        return self._store.create_set(name)

    def import_default(self) -> int:
        """A copy of eval's 24 tasks, to run as they are or to edit."""
        return self._store.create_set(DEFAULT_SET_NAME, load_tasks())

    def delete(self, set_id: int) -> None:
        self._store.delete_set(set_id)

    def save_task(self, set_id: int, form: TaskForm, *, replacing: str | None = None) -> Task:
        """Add the task, or replace `replacing` (its id may change). Raises InvalidInput."""
        question_set = self._store.get_set(set_id)
        if question_set is None:
            raise InvalidInput("Không có bộ câu hỏi này.")
        task = form.to_task()
        if task.id != replacing and question_set.task(task.id) is not None:
            raise InvalidInput(f"Bộ này đã có câu {task.id}.")
        if replacing and replacing != task.id:
            self._store.delete_task(set_id, replacing)
        self._store.save_task(set_id, task)
        return task

    def delete_task(self, set_id: int, task_id: str) -> None:
        self._store.delete_task(set_id, task_id)
