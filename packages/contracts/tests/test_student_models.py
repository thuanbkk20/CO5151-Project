import pytest
from pydantic import ValidationError

from co5151_contracts.student import AdviseeQuery, NoArgs, StudentProfile, TranscriptQuery

PROFILE = {
    "student_id": "2310001",
    "full_name": "Nguyễn Văn A",
    "faculty": "Khoa Khoa học và Kỹ thuật Máy tính",
    "program_type": "CQ",
    "cohort": 2023,
    "ctdt": "2023",
}


def test_no_args_rejects_injected_student_id():
    with pytest.raises(ValidationError):
        NoArgs.model_validate({"student_id": "2310002"})


@pytest.mark.parametrize("sem", ["20252", "20233", "BL"])
def test_semester_code_accepts(sem):
    assert TranscriptQuery(semester=sem).semester == sem


@pytest.mark.parametrize("sem", ["2025", "20254", "bl", "20252; DROP TABLE"])
def test_semester_code_rejects(sem):
    with pytest.raises(ValidationError):
        TranscriptQuery(semester=sem)


def test_advisee_query_requires_valid_mssv():
    assert AdviseeQuery(student_id="2310001").student_id == "2310001"
    for bad in [{}, {"student_id": "abc"}, {"student_id": "2310001", "role": "advisor"}]:
        with pytest.raises(ValidationError):
            AdviseeQuery.model_validate(bad)


def test_output_models_refuse_pii_fields():
    StudentProfile(**PROFILE)
    with pytest.raises(ValidationError):
        StudentProfile(**PROFILE, soCccd="000000000001")
