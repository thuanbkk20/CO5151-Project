import pytest

from co5151_contracts import ErrorCode, Role, ToolError
from co5151_contracts.export import DEFAULT_OUT, main
from co5151_contracts.tools import STUDENT_RECORD_TOOLS, Permission


def test_student_record_tools_are_read_only():
    assert {t.permission for t in STUDENT_RECORD_TOOLS.values()} == {Permission.READ_ONLY}


def test_self_tools_take_no_student_id():
    for name, t in STUDENT_RECORD_TOOLS.items():
        if name.startswith("get_my_"):
            assert t.roles == {Role.STUDENT}
            assert "student_id" not in t.input_schema()["properties"]


def test_every_input_schema_forbids_extra_properties():
    for t in STUDENT_RECORD_TOOLS.values():
        assert t.input_schema()["additionalProperties"] is False


def test_parse_args_reports_problems_without_echoing_input():
    with pytest.raises(ToolError) as e:
        STUDENT_RECORD_TOOLS["get_my_profile"].parse_args({"student_id": "2310002"})
    assert e.value.code is ErrorCode.INVALID_ARGUMENT
    assert "2310002" not in str(e.value.details)
    assert e.value.details["problems"][0]["field"] == "student_id"


def test_parse_args_accepts_none_as_empty():
    assert STUDENT_RECORD_TOOLS["get_my_transcript"].parse_args(None).semester is None


def test_committed_schemas_are_up_to_date():
    assert main(["--check", "--out", str(DEFAULT_OUT)]) == 0, "run: uv run python -m co5151_contracts.export"
