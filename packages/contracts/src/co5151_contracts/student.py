"""Input/output models of the Student Record MCP tools.

Every model forbids extra fields:
- on inputs, an injected argument (e.g. `student_id` on a `get_my_*` tool) is rejected as INVALID_ARGUMENT;
- on outputs, a field outside the contract (e.g. CCCD, email) cannot be serialized to the agent.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .auth import StudentId

SemesterCode = Annotated[str, StringConstraints(pattern=r"^([0-9]{4}[123]|BL)$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- inputs


class NoArgs(_Strict):
    """Tool không nhận tham số — danh tính lấy từ token phiên."""


class TranscriptQuery(_Strict):
    semester: SemesterCode | None = Field(
        None, description="Mã học kỳ dạng YYYYK (K = 1, 2, 3 hè), ví dụ 20252; hoặc BL (bảo lưu / công nhận)."
    )


class AdviseeQuery(_Strict):
    student_id: StudentId = Field(description="MSSV 7 chữ số của sinh viên thuộc danh sách cố vấn.")


# ---------------------------------------------------------------- outputs


class StudentProfile(_Strict):
    student_id: StudentId
    full_name: str
    faculty: str
    program_type: str = Field(description="Hệ đào tạo, ví dụ CQ (chính quy).")
    cohort: int = Field(description="Khóa tuyển sinh, ví dụ 2023.")
    ctdt: str = Field(description="Phiên bản chương trình đào tạo / quy chế áp dụng, ví dụ 2019 hoặc 2023.")


class AcademicSummary(_Strict):
    student_id: StudentId
    cohort: int
    ctdt: str
    program_credits: int = Field(description="Tổng số tín chỉ của chương trình đào tạo.")
    credits_earned: int = Field(description="Số tín chỉ tích lũy (theo bảng điểm học kỳ).")
    cgpa: float | None = Field(description="Điểm trung bình tích lũy thang 4.")
    cgpa10: float = Field(description="Điểm trung bình tích lũy thang 10.")
    capstone_project_passed: bool = Field(description="Đã đạt Đồ án chuyên ngành.")
    toeic: int | None = Field(description="Điểm TOEIC hoặc điểm quy đổi tương đương từ chứng chỉ khác.")
    english_cert: str | None = Field(description="Chứng chỉ ngoại ngữ đã nộp, ví dụ 'IELTS 6.5'.")
    gdtc_completed: bool
    gdqp_completed: bool
    currently_warned: bool = Field(description="Đang bị cảnh báo học tập ở học kỳ chính gần nhất.")
    consecutive_warnings: int
    retake_credits: int = Field(description="Tổng số tín chỉ đã học lại.")
    last_semester: SemesterCode | None


class CourseRecord(_Strict):
    semester: SemesterCode
    course: str
    name: str
    credits: int
    letter: str = Field(description="Điểm chữ (A+ … F) hoặc mã đặc biệt (MT, CT, VT, HT).")
    score10: float | None = Field(description="Điểm thang 10; null với mã điểm đặc biệt.")
    passed: bool
    status: str | None = Field(description="Ý nghĩa mã điểm đặc biệt, ví dụ 'Hoãn thi'.")
    in_gpa: bool = Field(description="Có được tính vào điểm trung bình không.")
    note: str | None


class Transcript(_Strict):
    student_id: StudentId
    semester: SemesterCode | None = None
    courses: list[CourseRecord]


class SemesterRecord(_Strict):
    semester: SemesterCode
    label: str
    credits_semester: int
    gpa10_semester: float
    credits_cumulative: int
    gpa10_cumulative: float
    updated: str


class SemesterSummary(_Strict):
    student_id: StudentId
    semesters: list[SemesterRecord] = Field(description="Mới nhất trước.")


class AcademicDecision(_Strict):
    semester: SemesterCode
    semester_label: str = Field(description="Tên học kỳ, ví dụ 'Học kỳ 1 (2026 - 2027)'.")
    decision_no: str = Field(description="Số quyết định, ví dụ '5487/QĐ-ĐHBK'.")
    decision_date: str = Field(description="Ngày ký quyết định (dd/mm/yyyy).")
    type: str = Field(description="Loại quyết định, ví dụ 'Cảnh báo học tập', 'Tạm dừng học', 'Quyết định khác'.")
    content: str = Field(description="Nội dung quyết định, ví dụ 'Giao đề tài Đồ án/Đề án tốt nghiệp'.")
    reason: str | None = Field(description="Lý do ra quyết định.")
    student_status: str = Field(description="Tình trạng học tập của sinh viên theo quyết định, ví dụ 'Đang theo học'.")
    is_warning: bool = Field(description="Quyết định là cảnh báo học tập.")
    updated: str = Field(description="Ngày cập nhật cuối (dd/mm/yyyy).")


class AcademicDecisions(_Strict):
    student_id: StudentId
    currently_warned: bool = Field(description="Đang bị cảnh báo học tập ở học kỳ chính gần nhất.")
    consecutive_warnings: int = Field(description="Số học kỳ chính liên tiếp bị cảnh báo, tính đến học kỳ gần nhất.")
    decisions: list[AcademicDecision] = Field(description="Mọi quyết định học vụ của sinh viên, mới nhất trước.")
