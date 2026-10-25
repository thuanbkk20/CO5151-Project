from typing import Any

from pydantic import BaseModel, ConfigDict

from co5151_contracts import ErrorCode

from .planner import Evidence


class StudentExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    evidence: Evidence | None = None
    error: str | None = None
    error_code: ErrorCode | None = None


SAFE_ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNAUTHENTICATED: "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại.",
    ErrorCode.FORBIDDEN: "Bạn không có quyền truy cập thông tin học vụ này.",
    ErrorCode.INVALID_ARGUMENT: "Thông tin yêu cầu không hợp lệ hoặc bị thiếu thông tin cần thiết.",
    ErrorCode.NOT_FOUND: "Không tìm thấy dữ liệu học vụ phù hợp.",
    ErrorCode.INTERNAL: "Hệ thống gặp sự cố tạm thời khi xử lý hồ sơ. Vui lòng thử lại sau.",
}


class StudentExecutor:
    """Wraps StudentRecordService.call to enforce strict tool scoping, evidence projection, and error mapping."""

    ALLOWED_TOOLS = {"get_my_academic_summary", "get_my_academic_decisions"}

    def __init__(self, service: Any):
        self._service = service

    def call(self, tool_name: str, token: str | None, args: dict[str, Any] | None = None) -> StudentExecutionResult:
        if tool_name not in self.ALLOWED_TOOLS:
            raise ValueError(f"Tool {tool_name!r} is not allowed. Allowed tools: {sorted(self.ALLOWED_TOOLS)}")

        # Execute with retry logic for INTERNAL errors
        res = self._service.call(tool_name, token, args)
        if not res.ok and res.error.code == ErrorCode.INTERNAL:
            # Retry exactly once
            res = self._service.call(tool_name, token, args)

        if not res.ok:
            code = res.error.code
            safe_msg = SAFE_ERROR_MESSAGES.get(code, "Đã xảy ra lỗi khi truy vấn dữ liệu học vụ.")
            return StudentExecutionResult(ok=False, error=safe_msg, error_code=code)

        data = res.data
        if tool_name == "get_my_academic_summary":
            remaining = data.program_credits - data.credits_earned
            evidence = Evidence(
                ctdt=data.ctdt,
                program_credits=data.program_credits,
                credits_earned=data.credits_earned,
                remaining_credits=remaining,
                cgpa=data.cgpa,
                capstone_project_passed=data.capstone_project_passed,
                toeic=data.toeic,
                english_cert=data.english_cert,
                gdtc_completed=data.gdtc_completed,
                gdqp_completed=data.gdqp_completed,
            )
            return StudentExecutionResult(ok=True, evidence=evidence)

        if tool_name == "get_my_academic_decisions":
            evidence = Evidence(
                warnings_checked=True,
                currently_warned=data.currently_warned,
                consecutive_warnings=data.consecutive_warnings,
            )
            return StudentExecutionResult(ok=True, evidence=evidence)

        return StudentExecutionResult(ok=False, error="Tool không được hỗ trợ.", error_code=ErrorCode.NOT_FOUND)
