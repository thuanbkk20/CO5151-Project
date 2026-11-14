import os
from pathlib import Path

OFF_VALUES = {"off", "none", "false", "0"}


def database_url(default_sqlite_file: Path, variable: str = "CHAT_DATABASE_URL") -> str | None:
    """The SQLAlchemy URL to store chats in, or None when persistence is turned off.

    Empty: a SQLite file at `default_sqlite_file`. `off`: no persistence. Anything else is used as given, e.g.
    `postgresql+asyncpg://user:password@host:5432/co5151`.
    """
    value = os.environ.get(variable, "").strip()
    if value.lower() in OFF_VALUES:
        return None
    return value or f"sqlite+aiosqlite:///{default_sqlite_file.resolve()}"


def new_trace_id() -> str:
    """32 lowercase hex characters, the trace-id format of W3C trace context (also used by OpenTelemetry)."""
    return os.urandom(16).hex()
