from co5151_backend.domain.conversation import MAX_TITLE, title_from
from co5151_backend.domain.evidence import Action, Decision, Evidence
from co5151_backend.domain.trace import Usage, new_trace_id
from co5151_backend.infrastructure.config import Settings


def test_evidence_knows_what_was_collected():
    ev = Evidence(credits_earned=92, program_credits=128, ctdt="2023")
    assert ev.collected(Action.SUMMARY) and not ev.collected(Action.WARNINGS) and not ev.collected(Action.RESPOND)
    assert ev.student_facts()["credits_earned"] == 92 and "currently_warned" not in ev.student_facts()
    assert Evidence().student_facts() == {}


def test_warning_facts_list_the_semesters_and_decisions_on_one_line():
    warned = Decision(semester="Học kỳ 2 (2024 - 2025)", type="Cảnh báo học tập", content="Cảnh báo mức 1",
                      decision_no="1/QĐ-ĐHBK", is_warning=True)  # fmt: skip
    thesis = Decision(semester="Học kỳ 1 (2025 - 2026)", type="Quyết định khác", content="Giao đề tài",
                      decision_no="2/QĐ-ĐHBK")  # fmt: skip
    ev = Evidence(warnings_checked=True, currently_warned=False, consecutive_warnings=0, decisions=[thesis, warned])
    facts = ev.student_facts()
    assert ev.warning_semesters == ["Học kỳ 2 (2024 - 2025)"] and facts["warning_semesters"] == "Học kỳ 2 (2024 - 2025)"
    assert facts["decisions"].startswith("Học kỳ 1 (2025 - 2026): Quyết định khác: Giao đề tài (2/QĐ-ĐHBK); ")


def test_usage_adds_up_and_trace_ids_are_w3c_shaped():
    assert (Usage(1, 2) + Usage(3, 4)).total == 10
    trace_id = new_trace_id()
    assert len(trace_id) == 32 and int(trace_id, 16) >= 0


def test_title_is_the_first_question_on_one_line():
    assert title_from("  Em  đủ\nđiều kiện? ") == "Em đủ điều kiện?"
    assert len(title_from("x" * 1000)) == MAX_TITLE


def test_settings_from_env():
    s = Settings.from_env({"BACKEND_TOKEN_SECRET": "a", "STUDENT_MCP_TOKEN_SECRET": "b", "CHAT_DATABASE_URL": "off",
                           "REGULATION_MCP_PORT": "9000"})  # fmt: skip
    assert s.database_url is None and s.regulation_mcp_url == "http://127.0.0.1:9000/mcp"
    assert s.student_mcp_url == "http://127.0.0.1:8102/mcp" and s.token_secret == b"a"
    assert s.admin_token is None
    assert Settings.from_env({"BACKEND_ADMIN_TOKEN": " t0k "}).admin_token == "t0k"
    assert Settings.from_env({}).guest_login and not Settings.from_env({"GUEST_LOGIN": "Off"}).guest_login
