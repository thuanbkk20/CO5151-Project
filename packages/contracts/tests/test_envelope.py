import pytest
from pydantic import ValidationError

from co5151_contracts import ErrorCode, ToolError, ToolResult, err, ok


def test_ok_envelope_shape():
    assert ok({"x": 1}).model_dump(exclude_none=True) == {"ok": True, "data": {"x": 1}}


def test_err_envelope_shape():
    dumped = err(ErrorCode.FORBIDDEN, "nope").model_dump(mode="json")
    assert dumped == {"ok": False, "data": None, "error": {"code": "FORBIDDEN", "message": "nope", "details": None}}


def test_envelope_rejects_inconsistent_states():
    with pytest.raises(ValidationError):
        ToolResult(ok=False)
    with pytest.raises(ValidationError):
        ToolResult(ok=True, error={"code": "INTERNAL", "message": "x"})


def test_unknown_error_code_rejected():
    with pytest.raises(ValidationError):
        ToolResult.model_validate({"ok": False, "error": {"code": "TEAPOT", "message": "x"}})


def test_tool_error_converts_to_result():
    res = ToolError(ErrorCode.NOT_FOUND, "missing", {"id": "1"}).to_result()
    assert not res.ok and res.error.code is ErrorCode.NOT_FOUND and res.error.details == {"id": "1"}


def test_only_internal_is_retryable():
    assert [c for c in ErrorCode if c.retryable] == [ErrorCode.INTERNAL]
