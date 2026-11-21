import pytest

from co5151_backend.application.tracing import MAX_ITEMS, MAX_TEXT, REDACTED, SpanRecorder, clip


def test_clip_bounds_size_and_redacts_secrets():
    clipped = clip({"text": "x" * (MAX_TEXT + 5), "items": list(range(MAX_ITEMS + 3)), "s": "a SECRET b"}, ("SECRET",))
    assert clipped["text"].startswith("x" * MAX_TEXT) and clipped["text"].endswith("(+5 ký tự)")
    assert len(clipped["items"]) == MAX_ITEMS + 1 and clipped["items"][-1] == "… (+3 mục)"
    assert clipped["s"] == f"a {REDACTED} b"


def test_a_failing_node_is_recorded_and_the_error_raised():
    spans = SpanRecorder(secrets=["SECRET"])
    with pytest.raises(RuntimeError), spans.span("regulation", "search", {"q": "SECRET"}):
        raise RuntimeError("down SECRET")
    [span] = spans.spans
    assert span.input == {"q": REDACTED} and span.error == f"RuntimeError: down {REDACTED}"
    with SpanRecorder(keep=False).span("planner", "rules", {}) as s:
        s.output = {"action": "RESPOND"}
