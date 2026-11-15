"""The console's own data in one SQLite file (Python's sqlite3): question sets and their tasks.

A connection per call: the pages run in FastAPI's thread pool and evaluation runs in a background thread.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from co5151_eval.tasks import Task

from ..models import InvalidInput, QuestionSet, QuestionSetSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS question_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
    set_id INTEGER NOT NULL REFERENCES question_sets(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    data TEXT NOT NULL,  -- the Task as JSON
    PRIMARY KEY (set_id, task_id)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class SqliteStore:
    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:  # commit, or roll back on an exception
                yield db
        finally:
            db.close()

    # Question sets -------------------------------------------------------------------------------------------

    def list_sets(self) -> list[QuestionSetSummary]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT s.id, s.name, s.created_at, COUNT(q.task_id) AS size FROM question_sets s "
                "LEFT JOIN questions q ON q.set_id = s.id GROUP BY s.id ORDER BY s.id DESC"
            ).fetchall()
        return [QuestionSetSummary(r["id"], r["name"], r["size"], r["created_at"]) for r in rows]

    def get_set(self, set_id: int) -> QuestionSet | None:
        with self._connect() as db:
            row = db.execute("SELECT id, name, created_at FROM question_sets WHERE id = ?", (set_id,)).fetchone()
            if row is None:
                return None
            data = db.execute("SELECT data FROM questions WHERE set_id = ? ORDER BY position", (set_id,)).fetchall()
        return QuestionSet(row["id"], row["name"], row["created_at"], [Task.model_validate_json(d[0]) for d in data])

    def create_set(self, name: str, tasks: list[Task] = ()) -> int:
        try:
            with self._connect() as db:
                set_id = db.execute("INSERT INTO question_sets (name, created_at) VALUES (?, ?)",
                                    (name, now())).lastrowid  # fmt: skip
                for position, task in enumerate(tasks):
                    db.execute("INSERT INTO questions VALUES (?, ?, ?, ?)",
                               (set_id, task.id, position, task.model_dump_json()))  # fmt: skip
        except sqlite3.IntegrityError as e:
            raise InvalidInput(f"Đã có bộ câu hỏi tên “{name}”.") from e
        return set_id

    def delete_set(self, set_id: int) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM question_sets WHERE id = ?", (set_id,))

    def save_task(self, set_id: int, task: Task) -> None:
        with self._connect() as db:
            row = db.execute("SELECT position FROM questions WHERE set_id = ? AND task_id = ?",
                             (set_id, task.id)).fetchone()  # fmt: skip
            if row is None:  # new: at the end
                position = db.execute("SELECT COALESCE(MAX(position) + 1, 0) FROM questions WHERE set_id = ?",
                                      (set_id,)).fetchone()[0]  # fmt: skip
            else:
                position = row[0]
            db.execute("INSERT OR REPLACE INTO questions VALUES (?, ?, ?, ?)",
                       (set_id, task.id, position, task.model_dump_json()))  # fmt: skip

    def delete_task(self, set_id: int, task_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM questions WHERE set_id = ? AND task_id = ?", (set_id, task_id))
