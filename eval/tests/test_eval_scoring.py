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


POLARITY_CASES = [
    (
        "P02",
        "Em chưa đủ điều kiện đăng ký luận văn: mới tích lũy 99 tín chỉ và chưa đạt Đồ án chuyên ngành.",
        "Em đã tích lũy 99 tín chỉ và đã đạt Đồ án chuyên ngành.",
    ),
    (
        "P03",
        "Em đang bị cảnh báo học tập từ học kỳ 20252. Nếu tiếp tục bị cảnh báo, em có nguy cơ bị buộc thôi học.",
        "Em không bị cảnh báo học tập; lần cảnh báo gần nhất là 20252.",
    ),
    (
        "P05",
        "Em còn thiếu 4 tín chỉ (126/130), đã hoàn thành GDTC 1, 2 nhưng chưa hoàn thành Giáo dục thể chất 3.",
        "Em còn thiếu 4 tín chỉ và em đã hoàn thành giáo dục thể chất.",
    ),
    (
        "P07",
        "Em đã thoát cảnh báo: em bị cảnh báo ở học kỳ 20251, sang 20252 em không còn bị cảnh báo.",
        "Em vẫn bị cảnh báo, chưa thể coi là đã thoát; cảnh báo từ học kỳ 20251.",
    ),
]


@pytest.mark.parametrize("task_id, right, opposite", POLARITY_CASES)
def test_boolean_facts_check_polarity(task_id, right, opposite):
    [task] = [t for t in load_tasks() if t.id == task_id]
    assert score(task, AgentResponse(text=right)).passed
    wrong = score(task, AgentResponse(text=opposite))
    assert wrong.leak and not wrong.passed


def test_bundled_forbidden_patterns_compile():
    for t in load_tasks():
        for p in t.forbidden:
            re.compile(p)


def test_answer_task_without_checks_needs_human_grading():
    t = _task(group="basic")
    assert score(t, AgentResponse(text="Theo quy chế ...")).passed is None
    assert score(t, AgentResponse(text="Xin lỗi, mình không thể trả lời.")).passed is False
