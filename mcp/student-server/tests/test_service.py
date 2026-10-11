import json

import pytest

from co5151_contracts import STUDENT_RECORD_TOOLS, ErrorCode

STUDENTS = [f"sv00{i}" for i in range(1, 9)]
SELF_TOOLS = [n for n in STUDENT_RECORD_TOOLS if n.startswith("get_my_")]


def dumped(res):
    return res.model_dump(mode="json")


@pytest.mark.parametrize("user", STUDENTS)
@pytest.mark.parametrize("tool", SELF_TOOLS)
def test_every_self_tool_matches_its_output_contract(service, token, user, tool):
    res = service.call(tool, token(user), {})
    assert res.ok, res.error
    STUDENT_RECORD_TOOLS[tool].output_model.model_validate(dumped(res)["data"])


@pytest.mark.parametrize("user", STUDENTS)
def test_no_pii_ever_leaves_the_service(db, service, token, user):
    mssv = db.account(user)["mssv"]
    raw = db.raw_profile(mssv)
    out = json.dumps([dumped(service.call(t, token(user), {})) for t in SELF_TOOLS], ensure_ascii=False)
    for secret in (raw["email"], raw["soCccd"], str(raw["sessionId"]), raw["personId"], raw["id"]):
        assert secret not in out


def test_student_sees_own_record(service, token):
    data = dumped(service.call("get_my_profile", token("sv002"), {}))["data"]
    assert data["student_id"] == "2310002" and data["full_name"] == "Trần Thị Bình"


def test_transcript_semester_filter(service, token):
    data = dumped(service.call("get_my_transcript", token("sv001"), {"semester": "20231"}))["data"]
    assert data["courses"] and {c["semester"] for c in data["courses"]} == {"20231"}
    assert dumped(service.call("get_my_transcript", token("sv001"), {"semester": "19991"}))["data"]["courses"] == []


def test_warnings_tool(service, token):
    data = dumped(service.call("get_my_warnings", token("sv003"), {}))["data"]
    assert data["currently_warned"] and data["history"][0]["semester"] == "20252"


@pytest.mark.parametrize(
    "tool, args",
    [
        ("get_my_profile", {"student_id": "2310002"}),
        ("get_my_academic_summary", {"student_id": "2310002", "as_admin": True}),
        ("get_my_transcript", {"semester": "'; DROP TABLE profiles; --"}),
    ],
)
def test_injected_arguments_rejected(service, token, tool, args):
    res = service.call(tool, token("sv001"), args)
    assert res.error.code is ErrorCode.INVALID_ARGUMENT


def test_advisor_flow(service, token):
    ok = service.call("get_advisee_summary", token("cvht01"), {"student_id": "2310003"})
    assert ok.ok and ok.data.student_id == "2310003"
    denied = service.call("get_advisee_summary", token("cvht01"), {"student_id": "2210004"})
    assert denied.error.code is ErrorCode.FORBIDDEN
    assert service.call("get_my_profile", token("cvht01"), {}).error.code is ErrorCode.FORBIDDEN


def test_student_cannot_call_advisor_tool(service, token):
    res = service.call("get_advisee_summary", token("sv001"), {"student_id": "2310002"})
    assert res.error.code is ErrorCode.FORBIDDEN


def test_missing_token_and_unknown_tool(service):
    assert service.call("get_my_profile", None).error.code is ErrorCode.UNAUTHENTICATED
    assert service.call("delete_student", None).error.code is ErrorCode.NOT_FOUND


def test_every_call_is_audited(service, token):
    service.call("get_my_profile", token("sv001"), {})
    service.call("get_advisee_summary", token("sv001"), {"student_id": "2310002"})
    service.call("get_my_profile", "bad.token")
    events = service.access_log.events()
    assert [(e.tool, e.allowed, e.error) for e in events] == [
        ("get_my_profile", True, None),
        ("get_advisee_summary", False, "FORBIDDEN"),
        ("get_my_profile", False, "UNAUTHENTICATED"),
    ]
    assert "2310001" not in repr(events) and "sv001" not in repr(events)


def test_internal_errors_are_masked(service, token, monkeypatch):
    def boom(_):
        raise RuntimeError("db path /secret/students.sqlite3 locked")

    monkeypatch.setattr(service.db, "raw_profile", boom)
    res = service.call("get_my_profile", token("sv001"), {})
    assert res.error.code is ErrorCode.INTERNAL and "secret" not in res.error.message
