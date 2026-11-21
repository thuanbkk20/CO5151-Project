"""Interfaces the console's services need from the outside world. Adapters in `adapters/` implement them.

Services only see these: the backend's HTTP API or the SQLite file can change without touching a service.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from co5151_eval.runner import Record
from co5151_eval.tasks import Task

from .models import QuestionSet, QuestionSetSummary, Run, RunResult


class BackendError(Exception):
    """The backend could not be reached or refused the request; `str(e)` is safe to show on a page."""


class BackendAdmin(Protocol):
    """The backend's admin API (`/admin/*`), signed with BACKEND_ADMIN_TOKEN. Values are the API's JSON."""

    def traces(self, *, conversation_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Newest first: `{trace, owner_id, question, answer, created_at, spans: []}`. Raises BackendError."""

    def trace(self, trace_id: str) -> dict[str, Any] | None:
        """The same item with its spans, or None when there is no such trace. Raises BackendError."""

    def sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Conversations, most recently active first: `{conversation_id, owner_id, title, turns, created_at,
        updated_at}`. Raises BackendError."""


class QuestionSetStore(Protocol):
    def list_sets(self) -> list[QuestionSetSummary]:
        """Newest first."""

    def get_set(self, set_id: int) -> QuestionSet | None:
        """With its tasks in the order they were added."""

    def create_set(self, name: str, tasks: list[Task] = ()) -> int:
        """Raises InvalidInput when the name is taken."""

    def delete_set(self, set_id: int) -> None: ...

    def save_task(self, set_id: int, task: Task) -> None:
        """Add the task, or replace the task with the same id."""

    def delete_task(self, set_id: int, task_id: str) -> None: ...


@dataclass(frozen=True)
class AgentAnswer:
    """One answer of the backend: the text and its trace (the API's TraceOut JSON), or the error."""

    text: str
    trace: dict[str, Any] | None
    error: str | None = None


class AnswerAgent(Protocol):
    """Asks the backend one question as a user would: sign in, open a conversation, ask."""

    def answer(self, question: str, *, user: str | None) -> AgentAnswer:
        """`user`: a demo account, or None for a guest. Never raises: failures come back in `error`."""


class RunStore(Protocol):
    def create_run(self, set_name: str, total: int) -> int: ...

    def add_result(self, run_id: int, task_id: str, question: str, trace_id: str | None, record: Record) -> None: ...

    def finish_run(self, run_id: int, status: str, error: str | None = None) -> None: ...

    def interrupt_running(self) -> None:
        """Runs left `running` by a console that stopped: mark them `interrupted`."""

    def list_runs(self) -> list[Run]:
        """Newest first."""

    def get_run(self, run_id: int) -> Run | None: ...

    def results(self, run_id: int) -> list[RunResult]:
        """In the order the tasks ran."""
