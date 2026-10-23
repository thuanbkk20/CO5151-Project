"""Task schema of the evaluation set and its loader.

One task = one user question plus what a correct system must do with it:
- `expected`: answer / clarify (ask back for missing info) / refuse (Strict Refusal);
- `facts`: values from the logged-in student's record that a correct answer must state;
- `citations`: articles of the regulation a correct answer must cite (filled by the regulation owner);
- `forbidden`: regex patterns that must never appear (other students' data, false confirmations, ...).

Auto-scoring covers what is checkable mechanically; `reference_answer` is for human grading.
"""

import json
from enum import Enum
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATA = resources.files("co5151_eval") / "data"


class Group(str, Enum):
    BASIC = "basic"  # Nhóm 1 – quy chế cơ bản, không cần tra điểm
    PERSONAL = "personal"  # Nhóm 2 – kết hợp quy chế và hồ sơ cá nhân
    MISSING_INFO = "missing_info"  # Nhóm 3 – thiếu khóa/ngành/ngữ cảnh, phải hỏi lại
    OUT_OF_SCOPE = "out_of_scope"  # Nhóm 4 – bẫy / ngoài phạm vi, phải từ chối


class Outcome(str, Enum):
    ANSWER = "answer"
    CLARIFY = "clarify"
    REFUSE = "refuse"


class Fact(BaseModel):
    """A value from the student's record the answer must state, e.g. credits_earned = 113."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(description="Trường trong AcademicSummary / WarningHistory, để đối chiếu với mock data.")
    value: str | int | float | bool
    mention: list[str] = Field(description="Các cách viết chấp nhận được trong câu trả lời (khớp một là đủ).")


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[A-Z]+[0-9]{2}$")
    group: Group
    question: str
    user: str | None = Field(None, description="Tài khoản demo đang đăng nhập (sv001…, cvht01) hoặc null.")
    history: list[dict[str, str]] = Field(default_factory=list, description="Các lượt hội thoại trước, nếu có.")
    expected: Outcome
    facts: list[Fact] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list, description="Ví dụ 'Điều 12 Khoản 2'.")
    citations_verified: bool = Field(False, description="Đáp án trích dẫn đã được người phụ trách quy chế xác nhận.")
    forbidden: list[str] = Field(default_factory=list, description="Regex không được xuất hiện trong câu trả lời.")
    reference_answer: str = ""
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self):
        if self.facts and self.user is None:
            raise ValueError(f"{self.id}: facts need a logged-in user")
        if self.citations_verified and not self.citations:
            raise ValueError(f"{self.id}: citations_verified without citations")
        return self


def load_tasks(path: str | Path | None = None) -> list[Task]:
    """Load a JSON list of tasks (default: the bundled 24-task set); ids must be unique."""
    raw = Path(path).read_text("utf-8") if path else (DATA / "tasks.json").read_text("utf-8")
    tasks = [Task.model_validate(t) for t in json.loads(raw)]
    ids = [t.id for t in tasks]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"duplicate task ids: {sorted(dup)}")
    return tasks
