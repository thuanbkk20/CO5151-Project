import pytest

from co5151_contracts import STUDENT_RECORD_TOOLS, ErrorCode, ToolError
from student_server.audit import AccessLog
from student_server.auth import TokenSigner
from student_server.authz import authenticate, resolve_target

SIGNER = TokenSigner(b"test-secret")
STUDENT = SIGNER.verify(SIGNER.issue({"sub": "sv001", "role": "student", "student_id": "2310001"}))
ADVISOR = SIGNER.verify(
    SIGNER.issue({"sub": "cvht01", "role": "advisor", "advisor_id": "CVHT01", "advisees": ["2310001", "2310002"]})
)
SELF_TOOLS = [t for n, t in STUDENT_RECORD_TOOLS.items() if n.startswith("get_my_")]
ADVISEE = STUDENT_RECORD_TOOLS["get_advisee_summary"]


def code_of(fn, *args):
    with pytest.raises(ToolError) as e:
        fn(*args)
    return e.value.code


FOREIGN = TokenSigner(b"other").issue({"sub": "x", "role": "student", "student_id": "2310002"})


@pytest.mark.parametrize("token", [None, "", "garbage", FOREIGN])
def test_unauthenticated(token):
    assert code_of(authenticate, SIGNER, token) is ErrorCode.UNAUTHENTICATED


@pytest.mark.parametrize("spec", SELF_TOOLS, ids=lambda t: t.name)
def test_student_reads_only_own_record(spec):
    assert resolve_target(STUDENT, spec) == "2310001"
    assert code_of(resolve_target, STUDENT, spec, "2310002") is ErrorCode.FORBIDDEN


def test_student_cannot_use_advisor_tool():
    assert code_of(resolve_target, STUDENT, ADVISEE, "2310001") is ErrorCode.FORBIDDEN


@pytest.mark.parametrize("spec", SELF_TOOLS, ids=lambda t: t.name)
def test_advisor_cannot_use_self_tools(spec):
    assert code_of(resolve_target, ADVISOR, spec) is ErrorCode.FORBIDDEN


def test_advisor_limited_to_advisees():
    assert resolve_target(ADVISOR, ADVISEE, "2310002") == "2310002"
    for other in ["2310003", "9999999", None]:
        assert code_of(resolve_target, ADVISOR, ADVISEE, other) is ErrorCode.FORBIDDEN


def test_denial_does_not_reveal_existence():
    def message(mssv):
        with pytest.raises(ToolError) as e:
            resolve_target(ADVISOR, ADVISEE, mssv)
        return e.value.message

    assert message("2310003") == message("9999999")  # existing vs unknown student


def test_access_log_pseudonymizes():
    log = AccessLog(b"k")
    ev = log.record("get_my_profile", actor="sv001", role="student", target="2310001", allowed=True)
    assert ev.actor == log.pseudonym("sv001") and "2310001" not in repr(log.events())
    assert AccessLog(b"other").pseudonym("sv001") != ev.actor
    denied = log.record(
        "get_advisee_summary", actor=None, role=None, target=None, allowed=False, error="UNAUTHENTICATED"
    )
    assert log.events()[-1] == denied and denied.target is None
