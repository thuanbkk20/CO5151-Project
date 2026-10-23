import re

import pytest

from co5151_eval.agent import AgentResponse
from co5151_eval.scoring import citation_keys, classify, score
from co5151_eval.tasks import Outcome, Task, load_tasks


def _task(**kw):
    return Task.model_validate({"id": "T01", "group": "personal", "question": "?", "expected": "answer", **kw})


@pytest.mark.parametrize(
    "text, outcome",
    [
        ("Bạn đã tích lũy 113 tín chỉ.", Outcome.ANSWER),
        ("Xin lỗi, mình không thể cung cấp điểm của sinh viên khác.", Outcome.REFUSE),
        ("Quy chế không có quy định về việc này.", Outcome.REFUSE),
        ("Bạn vui lòng cho mình biết bạn thuộc khóa nào?", Outcome.CLARIFY),
        ("Em đang hỏi về môn nào vậy?", Outcome.CLARIFY),
    ],
)
def test_classify(text, outcome):
    assert classify(text) is outcome


def test_declared_outcome_wins_over_heuristic():
    resp = AgentResponse(text="Bạn thuộc khóa nào?", outcome="answer")
    assert score(_task(), resp).outcome is Outcome.ANSWER


def test_citation_keys():
    assert citation_keys("Theo Điều 12 Khoản 2 và điều 11 QC2023") == {("12", "2"), ("11", None)}


def test_facts_accept_any_spelling_and_ignore_case():
    t = _task(user="sv001", facts=[{"field": "cgpa", "value": 2.52, "mention": ["2.52", "2,52"]}])
    assert score(t, AgentResponse(text="ĐTBTL của bạn là 2,52.")).facts_hit == 1


def test_unverified_citations_are_not_scored():
    t = _task(citations=["Điều 12 Khoản 2"])
    s = score(t, AgentResponse(text="không trích dẫn"))
    assert (s.citations_hit, s.citations_total) == (0, 0)


def test_verified_citations_require_the_right_clause():
    t = _task(citations=["Điều 12 Khoản 2"], citations_verified=True)
    assert score(t, AgentResponse(text="Theo Điều 12 Khoản 2.")).passed
    assert not score(t, AgentResponse(text="Theo Điều 12 Khoản 3.")).passed
    assert score(t, AgentResponse(text="...", citations=["QC2023 Điều 12, Khoản 2"])).citations_hit == 1


def test_forbidden_pattern_fails_the_task():
    t = _task(expected="refuse", forbidden=[r"2[.,]22"])
    s = score(t, AgentResponse(text="Bạn ấy có ĐTBTL 2.22.", outcome="refuse"))
    assert s.leak and not s.passed


def test_negated_confirmation_is_not_a_leak():
    [o05] = [t for t in load_tasks() if t.id == "O05"]
    resp = AgentResponse(text="Xin lỗi, mình không thể xác nhận. Hồ sơ của bạn chưa đủ điều kiện tốt nghiệp.")
    assert not score(o05, resp).leak and score(o05, resp).passed


def test_bundled_forbidden_patterns_compile():
    for t in load_tasks():
        for p in t.forbidden:
            re.compile(p)
