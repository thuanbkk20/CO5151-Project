"""Student Record service — transport-agnostic tool execution.

`call(name, token, args)` is the whole pipeline for one tool call:
    authenticate token → validate args (contracts) → authorize target (authz) → read & normalize → audit
and always returns a ToolResult envelope (never raises), so the MCP layer only has to serialize it.
"""

import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from co5151_contracts import STUDENT_RECORD_TOOLS, ErrorCode, ToolError, ToolResult, err, ok
from co5151_contracts.student import AcademicDecisions, SemesterSummary, Transcript, TranscriptQuery

from . import academic
from .audit import AccessLog
from .auth import TokenSigner
from .authz import authenticate, resolve_target
from .db import StudentDB

logger = logging.getLogger(__name__)


class StudentRecordService:
    def __init__(self, db: StudentDB, signer: TokenSigner, access_log: AccessLog):
        self.db = db
        self.signer = signer
        self.access_log = access_log
        self._handlers: dict[str, Callable[[str, BaseModel], BaseModel]] = {
            "get_my_profile": lambda sid, _: self._profile(sid),
            "get_my_academic_summary": lambda sid, _: self._summary(sid),
            "get_my_transcript": self._transcript,
            "get_my_semester_summary": lambda sid, _: self._semesters(sid),
            "get_my_academic_decisions": lambda sid, _: self._decisions(sid),
            "get_advisee_summary": lambda sid, _: self._summary(sid),
        }
        assert set(self._handlers) == set(STUDENT_RECORD_TOOLS), "every registered tool needs a handler"

    # ---------------------------------------------------------------- pipeline
    def call(self, name: str, token: str | None, args: dict[str, Any] | None = None) -> ToolResult:
        spec = STUDENT_RECORD_TOOLS.get(name)
        if spec is None:
            return err(ErrorCode.NOT_FOUND, f"Tool không tồn tại: {name}")
        claims, target = None, None
        try:
            claims = authenticate(self.signer, token)
            params = spec.parse_args(args)
            target = resolve_target(claims, spec, getattr(params, "student_id", None))
            data = self._handlers[name](target, params)
            if not isinstance(data, spec.output_model):  # contract guard: never emit an off-schema payload
                raise TypeError(f"{name} returned {type(data).__name__}, expected {spec.output_model.__name__}")
        except ToolError as e:
            self._audit(name, claims, target, e.code)
            return e.to_result()
        except Exception:
            logger.exception("tool %s failed", name)
            self._audit(name, claims, target, ErrorCode.INTERNAL)
            return err(ErrorCode.INTERNAL, "Lỗi hệ thống khi đọc hồ sơ. Vui lòng thử lại.")
        self._audit(name, claims, target, None)
        return ok(data)

    def _audit(self, tool, claims, target, error: ErrorCode | None):
        self.access_log.record(
            tool,
            actor=claims.sub if claims else None,
            role=claims.role.value if claims else None,
            target=target,
            allowed=error is None,
            error=error.value if error else None,
        )

    # ---------------------------------------------------------------- reads
    def _raw_profile(self, sid: str) -> dict:
        raw = self.db.raw_profile(sid)
        if raw is None:
            raise ToolError(ErrorCode.NOT_FOUND, "Không tìm thấy hồ sơ sinh viên.")
        return raw

    def _profile(self, sid: str):
        return academic.profile(self._raw_profile(sid))

    def _summary(self, sid: str):
        raw = self._raw_profile(sid)
        db = self.db
        return academic.summary(raw, db.raw_transcript(sid), db.raw_semesters(sid), db.raw_decisions(sid), db.ref)

    def _transcript(self, sid: str, q: TranscriptQuery):
        self._raw_profile(sid)
        special = self.db.ref["special_codes"]
        rows = [r for r in self.db.raw_transcript(sid) if q.semester is None or r["maHocKy"] == q.semester]
        return Transcript(student_id=sid, semester=q.semester, courses=[academic.course(r, special) for r in rows])

    def _semesters(self, sid: str):
        self._raw_profile(sid)
        return SemesterSummary(student_id=sid, semesters=[academic.semester(s) for s in self.db.raw_semesters(sid)])

    def _decisions(self, sid: str):
        self._raw_profile(sid)
        rows = self.db.raw_decisions(sid)
        warned = academic.consecutive_warnings(self.db.raw_transcript(sid), rows)
        return AcademicDecisions(
            student_id=sid,
            currently_warned=warned > 0,
            consecutive_warnings=warned,
            decisions=[academic.decision(d) for d in rows],
        )
