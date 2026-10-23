import re
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryKind = Literal["goal", "preference"]
PERMITTED_KINDS: set[str] = {"goal", "preference"}

# Sensitive pattern checkers
MSSV_PATTERN = re.compile(r"\b\d{7}\b")
TOKEN_PATTERNS = [
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"\b[a-fA-F0-9]{32,}\b"),
    re.compile(r"ey[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}", re.IGNORECASE),
]
RAW_ACADEMIC_FIELDS = [
    "socccd",
    "personid",
    "diemso",
    "diemchu",
    "sinhvienid",
    "namhochockyid",
    "sessionid",
    "session_id",
    "mamonhoc",
    "tenmonhoc",
    "sotinchi",
    "diemdat",
    "diemkhongin",
    "sotctlchung",
    "diemtbtlchung",
    "hinhthucxuly",
    "lanlientiep",
    "soquyetdinh",
    "userid",
    "user_id",
    "student_id",
    "transcript",
]

PREFERENCE_PATTERNS = [
    re.compile(
        r"(?:em|tôi|mình)?\s*(?:ưu\s+tiên|thích|nguyện\s+vọng|muốn)\s+([^.!?\n]+)",
        re.IGNORECASE,
    ),
]


class MemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    value: str
    source: str
    created_at: float
    expires_at: float | None = None

    def is_expired(self, current_time: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = time.time() if current_time is None else current_time
        return now > self.expires_at


class DecisionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str
    sources: list[str] = Field(default_factory=list)
    created_at: float


class MemoryGate:
    """Privacy-preserving memory store for student preferences and goals."""

    def __init__(self):
        self._items: list[MemoryItem] = []

    def _validate(self, kind: str, value: str) -> None:
        if kind not in PERMITTED_KINDS:
            raise ValueError(f"Invalid memory kind: {kind!r}. Permitted kinds are: {sorted(PERMITTED_KINDS)}")

        if MSSV_PATTERN.search(value):
            raise ValueError("MemoryGate rejected value: contains a seven-digit student ID / MSSV")

        if any(p.search(value) for p in TOKEN_PATTERNS):
            raise ValueError("MemoryGate rejected value: contains token-shaped string")

        val_lower = value.lower()
        if any(field in val_lower for field in RAW_ACADEMIC_FIELDS):
            raise ValueError("MemoryGate rejected value: contains raw academic or identity fields")

    def store(
        self,
        kind: str,
        value: str,
        source: str,
        ttl: float | None = None,
        current_time: float | None = None,
    ) -> MemoryItem:
        self._validate(kind, value)
        now = time.time() if current_time is None else current_time
        expires_at = (now + ttl) if ttl is not None else None
        item = MemoryItem(
            kind=kind,
            value=value,
            source=source,
            created_at=now,
            expires_at=expires_at,
        )
        self._items.append(item)
        return item

    def get_items(self, kind: str | None = None, current_time: float | None = None) -> list[MemoryItem]:
        now = time.time() if current_time is None else current_time
        valid = [it for it in self._items if not it.is_expired(now)]
        if kind is not None:
            valid = [it for it in valid if it.kind == kind]
        return valid

    def process_user_statement(self, text: str, current_time: float | None = None) -> MemoryItem | None:
        for p in PREFERENCE_PATTERNS:
            match = p.search(text)
            if match:
                pref_val = match.group(0).strip()
                try:
                    return self.store(
                        kind="preference",
                        value=pref_val,
                        source="user-stated",
                        current_time=current_time,
                    )
                except ValueError:
                    return None
        return None
