from co5151_eval.html_report import load_run, render, write_html_report
from co5151_eval.runner import Record, write_report

ADVISOR_CONFIG = {
    "llm": {"provider": "gemini", "model": "gemini-3.5-flash-lite"},
    "planner": "LLMDecisionPlanner",
    "regulation_source": "ToolRegulationSource",
}


def _record(task_id, group, seed, passed, *, outcome="answer", tokens=500, text="Câu trả lời", forbidden=None,
            tools=None, citations=None, facts=(1, 1)):  # fmt: skip
    return Record(task_id, group, seed, 1.5, tokens, outcome, passed is not False, facts[0], facts[1], 0, 0,
                  forbidden or [], passed, tools or [], text, None, citations or [])  # fmt: skip


def _run(tmp_path, name, records, config):
    out = tmp_path / name
    write_report(records, out, name, {"agent": f"pkg:{name}", "agent_config": config, "tasks": 2, "commit": "abc1234"})
    return out


def _two_runs(tmp_path):
    advisor = _run(tmp_path, "advisor", [
        _record("P01", "personal", 0, True, text="Em có 102 tín chỉ, TOEIC 500.",
                tools=["get_my_academic_summary", "search_regulations"], citations=["QD1260-2026-CL12.2"]),
        _record("P01", "personal", 1, False, tokens=100, facts=(1, 2), tools=["search_regulations"]),
        _record("O05", "out_of_scope", 0, False, forbidden=["đủ điều kiện"],
                text="Tôi xác nhận em đủ điều kiện tốt nghiệp <script>alert(1)</script>"),
    ], ADVISOR_CONFIG)  # fmt: skip
    baseline = _run(tmp_path, "record_template", [
        _record("P01", "personal", 0, False, tokens=0, facts=(1, 2)),
        _record("O05", "out_of_scope", 0, False, tokens=0),
    ], None)  # fmt: skip
    return advisor, baseline


def _html(tmp_path, lookup=None):
    return render([load_run(d) for d in _two_runs(tmp_path)], regulation_lookup=lookup)


def test_summary_counts_and_rates_with_counts(tmp_path):
    html = _html(tmp_path)
    assert "<span class='t-pass'>1 đạt</span><span class='t-fail'>2 trượt</span>" in html
    assert "<td class='num best'>0.33<span class='count'>(1/3)</span></td>" in html
    assert "gemini/gemini-3.5-flash-lite" in html and "không dùng LLM" in html and "abc1234" in html


def test_scoring_rules_are_explained_per_group(tmp_path):
    html = _html(tmp_path)
    assert "<h2>Cách chấm</h2>" in html
    assert "nghĩa là đạt 2 trong 3 lần hỏi, không phải điểm" in html
    assert html.count("<b>Hệ thống phải:</b>") == 4


def test_task_row_shows_seed_passes_and_why_it_failed(tmp_path):
    html = _html(tmp_path)
    assert "<span class='badge mixed'>1/2 lần đạt</span>" in html
    assert "thiếu fact (1/2) ×1" in html
    assert "sai kết cục (trả lời, cần từ chối) ×1; khớp mẫu cấm ×1" in html


def test_scorecard_lists_each_check(tmp_path):
    html = _html(tmp_path)
    assert "Fact <code>credits_earned</code> = 102: có nêu “102”" in html
    assert "<b>không thấy</b> cách viết nào" in html
    assert "<mark>đủ điều kiện tốt nghiệp</mark>" in html
    assert "→ TRƯỢT vì sai kết cục (trả lời, cần từ chối), khớp mẫu cấm" in html
    assert "nghi trả lời bằng template" in html


def test_recorded_regulation_calls_are_shown(tmp_path):
    html = _html(tmp_path)
    assert "trả 1 đoạn: <code>QD1260-2026-CL12.2</code>" in html
    assert "<span class='flag bad'>không trả đoạn nào</span>" in html
    assert "tra lại sau khi chạy" not in html


def test_lookup_reconstructs_regulation_results_for_old_runs(tmp_path):
    html = _html(tmp_path, lookup=lambda question: ["QD2933-2021-ART10"] if "luận văn" in question else [])
    assert "tra lại sau khi chạy) với câu hỏi này <span class='flag bad'>không trả đoạn quy chế nào</span>" in html
    assert "Một số phiếu chấm ghi kết quả Regulation MCP" in html


def test_answer_text_is_escaped(tmp_path):
    html = _html(tmp_path)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_write_html_report_creates_the_file(tmp_path):
    out = write_html_report(list(_two_runs(tmp_path)), tmp_path / "report" / "report.html")
    assert out.read_text("utf-8").startswith("<!doctype html>")
