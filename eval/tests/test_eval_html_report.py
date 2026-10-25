from co5151_eval.html_report import load_run, render, write_html_report
from co5151_eval.runner import Record, write_report


def _record(task_id, group, seed, passed, *, tokens=500, text="Câu trả lời", forbidden=None, error=None):
    return Record(task_id, group, seed, 1.5, tokens, "answer", passed is not False, 1, 1, 0, 0, forbidden or [],
                  passed, ["get_my_academic_summary"], text, error)  # fmt: skip


def _run(tmp_path, name, records, config):
    out = tmp_path / name
    write_report(records, out, name, {"agent": f"pkg:{name}", "agent_config": config, "tasks": 2, "commit": "abc1234"})
    return out


def _two_runs(tmp_path):
    llm = {"llm": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}, "planner": "LLMDecisionPlanner"}
    advisor = _run(tmp_path, "advisor", [
        _record("P01", "personal", 0, True),
        _record("P01", "personal", 1, False, tokens=100),
        _record("O05", "out_of_scope", 0, False, forbidden=["đủ điều kiện"], text="<script>alert(1)</script>"),
    ], llm)  # fmt: skip
    baseline = _run(tmp_path, "record_template", [
        _record("P01", "personal", 0, False, tokens=0),
        _record("O05", "out_of_scope", 0, False, tokens=0),
    ], None)  # fmt: skip
    return advisor, baseline


def test_report_compares_runs_and_marks_the_best(tmp_path):
    html = render([load_run(d) for d in _two_runs(tmp_path)])
    assert "gemini/gemini-3.5-flash-lite" in html and "không dùng LLM" in html
    assert "abc1234" in html
    assert "<td class='num best'>0.33</td>" in html
    assert html.count("<svg") == 1


def test_report_flags_template_answers_and_forbidden_matches(tmp_path):
    html = render([load_run(d) for d in _two_runs(tmp_path)])
    assert "nghi trả lời bằng template" in html
    assert "khớp mẫu cấm" in html
    assert "<span class='badge mixed'>1/2</span>⚠" in html


def test_answer_text_is_escaped(tmp_path):
    html = render([load_run(d) for d in _two_runs(tmp_path)])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_template_tokens_are_not_flagged_for_runs_without_llm(tmp_path):
    _, baseline = _two_runs(tmp_path)
    html = render([load_run(baseline)])
    assert "Không có câu nghi trả lời bằng template" in html


def test_write_html_report_creates_the_file(tmp_path):
    out = write_html_report(list(_two_runs(tmp_path)), tmp_path / "report" / "report.html")
    assert out.read_text("utf-8").startswith("<!doctype html>")
