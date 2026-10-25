"""Tool registry: one ToolSpec per tool = name + description + I/O models + permission level.

MCP servers register their tools from this registry and agents read it to build function-calling
schemas, so the two sides cannot drift apart.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, ValidationError

from .auth import SCOPE_RECORDS_READ, Role
from .envelope import ErrorCode, ToolError
from .student import (
    AcademicDecisions,
    AcademicSummary,
    AdviseeQuery,
    NoArgs,
    SemesterSummary,
    StudentProfile,
    Transcript,
    TranscriptQuery,
)


class Permission(str, Enum):
    """Permission levels used in the D2 tools table (R2)."""

    READ_ONLY = "read-only"
    WRITE_REVERSIBLE = "write-reversible"
    WRITE_IRREVERSIBLE = "write-irreversible"
    EXECUTE = "execute"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    permission: Permission
    roles: frozenset[Role]
    scope: str

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()

    def parse_args(self, args: Any) -> BaseModel:
        """Validate raw tool arguments; raise INVALID_ARGUMENT without echoing the input back."""
        try:
            return self.input_model.model_validate(args if args is not None else {})
        except ValidationError as e:
            problems = [
                {"field": ".".join(str(p) for p in d["loc"]) or None, "problem": d["msg"]}
                for d in e.errors(include_input=False, include_url=False)
            ]
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "Tham số không hợp lệ.", {"problems": problems}) from None

    def manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission.value,
            "roles": sorted(r.value for r in self.roles),
            "scope": self.scope,
        }


def _student_tool(name, description, input_model, output_model, roles=frozenset({Role.STUDENT})):
    return ToolSpec(name, description, input_model, output_model, Permission.READ_ONLY, roles, SCOPE_RECORDS_READ)


STUDENT_RECORD_TOOLS: dict[str, ToolSpec] = {
    t.name: t
    for t in [
        _student_tool(
            "get_my_profile",
            "Hồ sơ của sinh viên ĐANG ĐĂNG NHẬP: MSSV, họ tên, khoa, hệ, khóa tuyển sinh, chương trình đào tạo.",
            NoArgs,
            StudentProfile,
        ),
        _student_tool(
            "get_my_academic_summary",
            "Tóm tắt học vụ của sinh viên đang đăng nhập: tín chỉ tích lũy, ĐTBTL thang 4 (cgpa) và thang 10 (cgpa10), "
            "đồ án chuyên ngành, chứng chỉ ngoại ngữ (quy đổi TOEIC), GDTC/GDQP, trạng thái cảnh báo.",
            NoArgs,
            AcademicSummary,
        ),
        _student_tool(
            "get_my_transcript",
            "Bảng điểm môn học của sinh viên đang đăng nhập (mã điểm đặc biệt đã được giải mã), "
            "có thể lọc theo học kỳ dạng 20252 hoặc BL.",
            TranscriptQuery,
            Transcript,
        ),
        _student_tool(
            "get_my_semester_summary",
            "Bảng điểm theo học kỳ của sinh viên đang đăng nhập: tín chỉ tích lũy và điểm trung bình (thang 10) "
            "từng học kỳ và cộng dồn.",
            NoArgs,
            SemesterSummary,
        ),
        _student_tool(
            "get_my_academic_decisions",
            "Các quyết định học vụ của sinh viên đang đăng nhập (cảnh báo học tập, tạm dừng / tiếp tục học, "
            "miễn học, giao đề tài tốt nghiệp, ...) kèm trạng thái cảnh báo hiện tại.",
            NoArgs,
            AcademicDecisions,
        ),
        _student_tool(
            "get_advisee_summary",
            "(Chỉ dành cho Cố vấn học tập) Tóm tắt học vụ của một sinh viên thuộc danh sách cố vấn "
            "của tài khoản đang đăng nhập.",
            AdviseeQuery,
            AcademicSummary,
            roles=frozenset({Role.ADVISOR}),
        ),
    ]
}
