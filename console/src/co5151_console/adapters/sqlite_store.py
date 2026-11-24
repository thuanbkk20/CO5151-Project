"""The console's own data in one SQLite file (Python's sqlite3): question sets and their tasks, evaluation runs
and their results.

A connection per call: the pages run in FastAPI's thread pool and evaluation runs in a background thread.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from co5151_eval.runner import Record
from co5151_eval.tasks import Task

from ..models import InvalidInput, QuestionSet, QuestionSetSummary, Run, RunResult

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
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_name TEXT NOT NULL,  -- copied: the set may be edited or deleted later
    status TEXT NOT NULL,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS run_results (
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    question TEXT NOT NULL,
    trace_id TEXT,
    record TEXT NOT NULL,  -- the co5151_eval Record as JSON
    PRIMARY KEY (run_id, position)
);
"""
RUN_COLUMNS = "SELECT r.*, (SELECT COUNT(*) FROM run_results x WHERE x.run_id = r.id) AS done FROM runs r"


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

    # Evaluation runs -----------------------------------------------------------------------------------------

    def create_run(self, set_name: str, total: int) -> int:
        with self._connect() as db:
            return db.execute("INSERT INTO runs (set_name, status, total, created_at) VALUES (?, 'running', ?, ?)",
                              (set_name, total, now())).lastrowid  # fmt: skip

    def add_result(self, run_id: int, task_id: str, question: str, trace_id: str | None, record: Record) -> None:
        with self._connect() as db:
            position = db.execute("SELECT COUNT(*) FROM run_results WHERE run_id = ?", (run_id,)).fetchone()[0]
            data = json.dumps(asdict(record), ensure_ascii=False)
            db.execute("INSERT INTO run_results VALUES (?, ?, ?, ?, ?, ?)",
                       (run_id, position, task_id, question, trace_id, data))  # fmt: skip

    def finish_run(self, run_id: int, status: str, error: str | None = None) -> None:
        with self._connect() as db:
            db.execute("UPDATE runs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                       (status, error, now(), run_id))  # fmt: skip

    def interrupt_running(self) -> None:
        with self._connect() as db:
            db.execute("UPDATE runs SET status = 'interrupted', finished_at = ? WHERE status = 'running'", (now(),))

    def list_runs(self) -> list[Run]:
        with self._connect() as db:
            return [_run(r) for r in db.execute(f"{RUN_COLUMNS} ORDER BY r.id DESC").fetchall()]

    def get_run(self, run_id: int) -> Run | None:
        with self._connect() as db:
            row = db.execute(f"{RUN_COLUMNS} WHERE r.id = ?", (run_id,)).fetchone()
        return _run(row) if row else None

    def results(self, run_id: int) -> list[RunResult]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM run_results WHERE run_id = ? ORDER BY position", (run_id,)).fetchall()
        return [RunResult(r["task_id"], r["question"], r["trace_id"], Record(**json.loads(r["record"]))) for r in rows]


def _run(row: sqlite3.Row) -> Run:
    return Run(id=row["id"], set_name=row["set_name"], status=row["status"], total=row["total"], done=row["done"],
               created_at=row["created_at"], finished_at=row["finished_at"], error=row["error"])  # fmt: skip
