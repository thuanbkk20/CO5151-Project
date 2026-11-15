"""Interfaces the console's services need from the outside world. Adapters in `adapters/` implement them.

Services only see these: the backend's HTTP API or the SQLite file can change without touching a service.
"""

from typing import Any, Protocol


class BackendError(Exception):
    """The backend could not be reached or refused the request; `str(e)` is safe to show on a page."""


class BackendAdmin(Protocol):
    """The backend's admin API (`/admin/*`), signed with BACKEND_ADMIN_TOKEN. Values are the API's JSON."""

    def traces(self, *, conversation_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Newest first: `{trace, owner_id, question, answer, created_at, spans: []}`. Raises BackendError."""

    def trace(self, trace_id: str) -> dict[str, Any] | None:
        """The same item with its spans, or None when there is no such trace. Raises BackendError."""
