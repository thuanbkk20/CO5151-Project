import pytest
from pydantic import ValidationError

from co5151_contracts import (
    IssueCode,
    RegulationExcerpt,
    Verdict,
    VerdictStatus,
    VerificationIssue,
    VerificationRequest,
)

ISSUE = VerificationIssue(code=IssueCode.UNSUPPORTED_CITATION, message="Điều 99 không có trong bằng chứng")


def test_request_round_trips_through_json():
    request = VerificationRequest(
        question="Em đủ điều kiện làm luận văn chưa?",
        draft="Bạn đã tích lũy 92/128 tín chỉ.",
        student_facts={"credits_earned": 92, "cgpa": 2.28, "capstone_project_passed": False, "english_cert": None},
        regulations=[RegulationExcerpt(id="QD2933-2021-CL5.5", content="Điều kiện đăng ký luận văn...")],
    )
    again = VerificationRequest.model_validate_json(request.model_dump_json())
    assert again == request
    assert again.student_facts["capstone_project_passed"] is False
    assert again.student_facts["credits_earned"] == 92


def test_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        VerificationRequest(question="q", draft="d", session_token="abc")


def test_pass_carries_no_issues():
    assert Verdict(status=VerdictStatus.PASS).issues == []
    with pytest.raises(ValidationError):
        Verdict(status=VerdictStatus.PASS, issues=[ISSUE])


@pytest.mark.parametrize("status", [VerdictStatus.REVISE, VerdictStatus.REFUSE])
def test_revise_and_refuse_must_say_why(status):
    assert Verdict(status=status, issues=[ISSUE]).issues == [ISSUE]
    with pytest.raises(ValidationError):
        Verdict(status=status)
