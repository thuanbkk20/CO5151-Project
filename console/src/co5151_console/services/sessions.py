"""Sessions page: the conversations, and one conversation as its turns (question, answer, trace) in order."""

from dataclasses import dataclass, field

from ..ports import BackendAdmin
from .traces import TraceRow, row_of

MAX_TURNS = 200  # the admin API's largest page


@dataclass(frozen=True)
class SessionRow:
    id: str
    owner: str
    title: str
    turns: int
    updated_at: str


@dataclass(frozen=True)
class Turn:
    row: TraceRow  # outcome, tokens, time, trace id
    question: str | None
    answer: str | None


@dataclass(frozen=True)
class SessionDetail:
    id: str
    owner: str
    turns: list[Turn] = field(default_factory=list)


def _time(value: str | None) -> str:
    return (value or "")[:19].replace("T", " ")


class SessionBrowser:
    def __init__(self, admin: BackendAdmin):
        self._admin = admin

    def all(self, limit: int = 50) -> list[SessionRow]:
        """Raises BackendError."""
        return [
            SessionRow(
                s["conversation_id"],
                s["owner_id"],
                s.get("title") or "(chưa có tiêu đề)",
                s["turns"],
                _time(s.get("updated_at")),
            )  # fmt: skip
            for s in self._admin.sessions(limit=limit)
        ]

    def detail(self, session_id: str) -> SessionDetail:
        """Oldest turn first, as the conversation went. Raises BackendError."""
        items = list(reversed(self._admin.traces(conversation_id=session_id, limit=MAX_TURNS)))
        owner = items[0]["owner_id"] if items else ""
        return SessionDetail(session_id, owner, [Turn(row_of(i), i.get("question"), i.get("answer")) for i in items])
