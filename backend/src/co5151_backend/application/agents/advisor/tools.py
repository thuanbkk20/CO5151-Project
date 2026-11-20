"""The Advisor's tools: two Student Record reads and the regulation search, each projected onto Evidence."""

from dataclasses import dataclass
from typing import Any

from co5151_contracts import ErrorCode

from ....domain.evidence import Action, Regulation
from ...ports import RegulationGateway, StudentRecordGateway

STUDENT_TOOLS = {Action.SUMMARY: "get_my_academic_summary", Action.WARNINGS: "get_my_academic_decisions"}
REGULATION_TOOL = "search_regulations"

SAFE_ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNAUTHENTICATED: "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại.",
    ErrorCode.FORBIDDEN: "Bạn không có quyền truy cập thông tin học vụ này.",
    ErrorCode.INVALID_ARGUMENT: "Thông tin yêu cầu không hợp lệ hoặc bị thiếu thông tin cần thiết.",
    ErrorCode.NOT_FOUND: "Không tìm thấy dữ liệu học vụ phù hợp.",
    ErrorCode.INTERNAL: "Hệ thống gặp sự cố tạm thời khi xử lý hồ sơ. Vui lòng thử lại sau.",
}


@dataclass(frozen=True)
class StudentFacts:
    """Fields to merge into Evidence, or a message safe to show when the read failed."""

    fields: dict[str, Any] | None = None
    error: str | None = None
    error_code: ErrorCode | None = None


class StudentTools:
    """Only the two reads the Advisor needs; the token comes from the use case, never from the LLM."""

    def __init__(self, gateway: StudentRecordGateway):
        self._gateway = gateway

    async def read(self, action: Action, token: str) -> StudentFacts:
        tool = STUDENT_TOOLS[action]
        res = await self._gateway.call(tool, token)
        if not res.ok and res.error.code.retryable:
            res = await self._gateway.call(tool, token)  # once
        if not res.ok:
            code = res.error.code
            return StudentFacts(error=SAFE_ERROR_MESSAGES.get(code, SAFE_ERROR_MESSAGES[ErrorCode.INTERNAL]),
                                error_code=code)  # fmt: skip
        data = res.data
        if action is Action.SUMMARY:
            return StudentFacts(
                {
                    "ctdt": data.ctdt,
                    "program_credits": data.program_credits,
                    "credits_earned": data.credits_earned,
                    "remaining_credits": data.program_credits - data.credits_earned,
                    "cgpa": data.cgpa,
                    "capstone_project_passed": data.capstone_project_passed,
                    "toeic": data.toeic,
                    "english_cert": data.english_cert,
                    "gdtc_completed": data.gdtc_completed,
                    "gdqp_completed": data.gdqp_completed,
                }
            )
        return StudentFacts(
            {
                "warnings_checked": True,
                "currently_warned": data.currently_warned,
                "consecutive_warnings": data.consecutive_warnings,
            }
        )


class RegulationSearch:
    def __init__(self, gateway: RegulationGateway, *, top_k: int = 3, hops: int = 1, max_chars: int = 1500):
        self._gateway = gateway
        self._top_k = top_k
        self._hops = hops
        self._max_chars = max_chars

    async def search(self, query: str) -> list[Regulation]:
        res = await self._gateway.call(REGULATION_TOOL, {"query": query, "top_k": self._top_k, "hops": self._hops})
        if not res.ok:
            return []
        return [self._regulation(r) for r in res.data.get("results", [])]

    def _regulation(self, result: dict) -> Regulation:
        evidence = result.get("evidence") or {}
        citation = result.get("citation") or {}
        pages = citation.get("pdf_pages") or []
        source = citation.get("file_name", "")
        where = f"{source}, trang {pages[0]}-{pages[-1]}" if pages else source
        # Decisions carry `fragments`; language rules only `source_text`; handbook / FAQ units `text`.
        text = (
            " ".join(f.get("text", "") for f in evidence.get("fragments") or [])
            or evidence.get("text")
            or evidence.get("source_text")
            or ""
        )
        title = evidence.get("title", result["id"])
        return Regulation(
            id=evidence.get("provision_id") or result["id"],
            title=f"{title} ({where})" if where else title,
            content=" ".join(text.split())[: self._max_chars],
        )
