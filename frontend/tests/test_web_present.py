from web_fakes import CONVERSATION, TRACE

from co5151_web.present import (
    DRAFT_NOTE,
    SECURITY_STARTER,
    chat_settings_body,
    details_markdown,
    pick_provider,
    progress_line,
    starters_for,
    step_markdown,
    thread_dict,
    welcome_markdown,
)


def test_progress_lines_are_plain_words():
    assert progress_line({"name": "plan", "action": "SUMMARY"}) == "Hiểu câu hỏi: cần đọc hồ sơ học vụ"
    assert progress_line({"name": "tool", "tool": "search_regulations"}) == "Tra quy chế đào tạo"
    assert progress_line({"name": "write"}) == "Soạn câu trả lời"
    assert progress_line({"name": "write", "revision": True}) == "Viết lại theo góp ý của Verifier"
    assert progress_line({"name": "verify", "round": 1, "status": "revise"}) == "Verifier kiểm tra lượt 1: cần sửa"
    # values the frontend does not know yet are shown as they come
    assert progress_line({"name": "plan", "action": "MOI"}) == "Hiểu câu hỏi: MOI"
    assert progress_line({"name": "tool", "tool": "get_x"}) == "Gọi tool `get_x`"
    assert progress_line({"name": "khac"}) == "khac"


def test_step_lists_the_steps_then_the_technical_details():
    running = step_markdown(["Tra quy chế đào tạo"])
    assert running == "- Tra quy chế đào tạo" and "Chi tiết kỹ thuật" not in running
    done = step_markdown(["Tra quy chế đào tạo"], TRACE)
    assert done.startswith("- Tra quy chế đào tạo\n\n**Chi tiết kỹ thuật**") and "`t1`" in done


def test_details_show_the_trace():
    text = details_markdown(TRACE)
    assert "get_my_academic_summary" in text and "QD-Đ22" in text and "1350" in text and "`t1`" in text
    assert "Lỗi LLM" not in text
    assert "**Conversation ID:** `6f1c1f0e-0000-4000-8000-000000000001`" in text
    assert "Lỗi LLM:** hết quota" in details_markdown({**TRACE, "llm_error": "hết quota"})


def test_thread_keeps_backend_message_ids_and_feedback():
    thread = thread_dict(CONVERSATION, "sv002")
    assert thread["userIdentifier"] == "sv002"
    assert thread["metadata"] == {"chat_settings": {"provider": "gemini"}}
    user, answer = thread["steps"]
    assert (user["type"], user["name"]) == ("user_message", "sv002")
    assert answer["id"] == "m2" and answer["feedback"]["forId"] == "m2" and answer["feedback"]["value"] == 1


def test_settings_body_maps_an_empty_model_to_the_default():
    assert chat_settings_body({"provider": "gemini", "model": "  "}) == {"provider": "gemini", "model": None}
    assert chat_settings_body(None) == {"provider": None, "model": None}


def test_provider_falls_back_when_its_key_is_gone():
    assert pick_provider("openai", ["gemini", "openai"], "gemini") == "openai"
    assert pick_provider("kimi", ["gemini", "openai"], "openai") == "openai"
    assert pick_provider(None, ["openai"], "gemini") == "openai"


def test_starters_by_role():
    student, guest, advisor = starters_for("student"), starters_for("guest"), starters_for("advisor")
    assert any("hồ sơ" in q or "của em" in q or "em " in q for _, q in student[:-1])
    assert guest == advisor and not any("của em" in q for _, q in guest)  # nothing the Advisor cannot read for them
    assert student[-1] == guest[-1] == SECURITY_STARTER
    assert starters_for(None) == guest


def test_welcome_by_role_says_the_data_is_a_draft():
    assert "Xin chào Nguyễn An" in welcome_markdown("student", "Nguyễn An")
    assert "tài khoản khách" in welcome_markdown("guest", "Khách") and "`sv001`" in welcome_markdown(None, None)
    assert "chưa có trong chat" in welcome_markdown("advisor", "TS. Mai Văn Hùng")
    assert all(DRAFT_NOTE in welcome_markdown(r, "x") for r in ("student", "guest", "advisor"))
