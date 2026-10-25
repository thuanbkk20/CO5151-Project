from unittest.mock import MagicMock

import pytest

from co5151_advisor.executor import StudentExecutionResult, StudentExecutor
from co5151_advisor.planner import Evidence
from co5151_contracts import ErrorCode, err, ok
from co5151_contracts.student import AcademicSummary


def _sample_academic_summary() -> AcademicSummary:
    return AcademicSummary(
        student_id="2310001",
        cohort=2023,
        ctdt="2023",
        program_credits=128,
        credits_earned=113,
        cgpa=2.52,
        cgpa10=7.2,
        capstone_project_passed=True,
        toeic=500,
        english_cert=None,
        gdtc_completed=True,
        gdqp_completed=True,
        currently_warned=False,
        consecutive_warnings=0,
        retake_credits=0,
        last_semester="20252",
    )


def test_allowed_tools_restriction():
    mock_svc = MagicMock()
    executor = StudentExecutor(mock_svc)

    with pytest.raises(ValueError, match="not allowed"):
        executor.call("get_my_profile", token="some_token")

    with pytest.raises(ValueError, match="not allowed"):
        executor.call("get_my_transcript", token="some_token")


def test_academic_summary_exposes_only_required_fields():
    mock_svc = MagicMock()
    mock_svc.call.return_value = ok(_sample_academic_summary())

    executor = StudentExecutor(mock_svc)
    res: StudentExecutionResult = executor.call("get_my_academic_summary", token="secret-token-123")

    assert res.ok
    assert isinstance(res.evidence, Evidence)
    ev = res.evidence
    assert ev.ctdt == "2023"
    assert ev.program_credits == 128
    assert ev.credits_earned == 113
    assert ev.remaining_credits == 128 - 113
    assert ev.cgpa == 2.52
    assert ev.capstone_project_passed is True
    assert ev.gdtc_completed is True
    assert ev.gdqp_completed is True

    dumped = ev.model_dump()
    assert "student_id" not in dumped
    assert "secret-token-123" not in str(dumped)
    assert "toeic" not in dumped


def test_internal_error_retries_once_and_succeeds():
    mock_svc = MagicMock()
    mock_svc.call.side_effect = [
        err(ErrorCode.INTERNAL, "DB lock"),
        ok(_sample_academic_summary()),
    ]

    executor = StudentExecutor(mock_svc)
    res = executor.call("get_my_academic_summary", token="tok")

    assert res.ok
    assert mock_svc.call.call_count == 2
    assert res.evidence is not None


def test_internal_error_retries_once_and_fails_safely():
    mock_svc = MagicMock()
    mock_svc.call.side_effect = [
        err(ErrorCode.INTERNAL, "DB lock 1"),
        err(ErrorCode.INTERNAL, "DB lock 2"),
    ]

    executor = StudentExecutor(mock_svc)
    res = executor.call("get_my_academic_summary", token="tok")

    assert not res.ok
    assert mock_svc.call.call_count == 2
    assert "thử lại sau" in res.error.lower()
    assert res.error_code == ErrorCode.INTERNAL


def test_unauthenticated_maps_safely_without_retry():
    mock_svc = MagicMock()
    mock_svc.call.return_value = err(ErrorCode.UNAUTHENTICATED, "token expired")

    executor = StudentExecutor(mock_svc)
    res = executor.call("get_my_academic_summary", token="bad-tok")

    assert not res.ok
    assert mock_svc.call.call_count == 1
    assert "đăng nhập lại" in res.error.lower()
    assert res.error_code == ErrorCode.UNAUTHENTICATED


def test_forbidden_maps_safely_without_retry():
    mock_svc = MagicMock()
    mock_svc.call.return_value = err(ErrorCode.FORBIDDEN, "access denied")

    executor = StudentExecutor(mock_svc)
    res = executor.call("get_my_academic_summary", token="tok")

    assert not res.ok
    assert mock_svc.call.call_count == 1
    assert "quyền" in res.error.lower()
    assert res.error_code == ErrorCode.FORBIDDEN


def test_invalid_argument_and_not_found_map_safely():
    mock_svc = MagicMock()
    mock_svc.call.return_value = err(ErrorCode.INVALID_ARGUMENT, "bad param")
    executor = StudentExecutor(mock_svc)

    res = executor.call("get_my_academic_summary", token="tok")
    assert not res.ok
    assert "không hợp lệ" in res.error.lower() or "thiếu" in res.error.lower()

    mock_svc.call.return_value = err(ErrorCode.NOT_FOUND, "no student")
    res = executor.call("get_my_academic_summary", token="tok")
    assert not res.ok
    assert "không tìm thấy" in res.error.lower()
