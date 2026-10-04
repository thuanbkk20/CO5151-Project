import pytest
from pydantic import ValidationError

from co5151_contracts import Role, SessionClaims

NOW = 1_800_000_000


def student(**kw):
    return dict({"sub": "sv001", "role": "student", "student_id": "2310001", "iat": NOW, "exp": NOW + 3600}, **kw)


def advisor(**kw):
    base = {
        "sub": "cvht01",
        "role": "advisor",
        "advisor_id": "CV01",
        "advisees": ["2310001"],
        "iat": NOW,
        "exp": NOW + 60,
    }
    return dict(base, **kw)


def test_valid_student_and_advisor_claims():
    assert SessionClaims(**student()).role is Role.STUDENT
    assert SessionClaims(**advisor()).advisees == ("2310001",)


@pytest.mark.parametrize(
    "claims",
    [
        student(student_id=None),
        student(student_id="23-0001"),
        student(advisees=["2310002"]),
        advisor(advisor_id=None),
        advisor(student_id="2310001"),
        student(exp=NOW),
        student(role="admin"),
        student(is_admin=True),
    ],
)
def test_invalid_claims_rejected(claims):
    with pytest.raises(ValidationError):
        SessionClaims(**claims)


def test_expiry_check():
    c = SessionClaims(**student())
    assert not c.is_expired(NOW + 10)
    assert c.is_expired(NOW + 3600)
