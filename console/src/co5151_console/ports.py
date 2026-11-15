"""Interfaces the console's services need from the outside world. Adapters in `adapters/` implement them.

Services only see these: the backend's HTTP API or the SQLite file can change without touching a service.
"""

from typing import Any, Protocol

from co5151_eval.tasks import Task

from .models import QuestionSet, QuestionSetSummary


class BackendError(Exception):
    """The backend could not be reached or refused the request; `str(e)` is safe to show on a page."""


class BackendAdmin(Protocol):
    """The backend's admin API (`/admin/*`), signed with BACKEND_ADMIN_TOKEN. Values are the API's JSON."""

    def traces(self, *, conversation_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Newest first: `{trace, owner_id, question, answer, created_at, spans: []}`. Raises BackendError."""

    def trace(self, trace_id: str) -> dict[str, Any] | None:
        """The same item with its spans, or None when there is no such trace. Raises BackendError."""


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
