from web_fakes import CONVERSATION, PROVISION, TRACE

from co5151_web.present import (
    DRAFT_NOTE,
    SECURITY_STARTER,
    chat_settings_body,
    details_markdown,
    has_free_model,
    llm_options,
    pick_llm,
    plain_markdown,
    progress_line,
    provision_markdown,
    source_label,
    starters_for,
    step_markdown,
    thread_dict,
    verification_line,
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


CHOICES = {"providers": ["azure", "foundry"], "default": "azure", "models": {"azure": [], "foundry": ["a", "b"]}}


def test_settings_body_splits_provider_and_model():
    assert chat_settings_body({"llm": "foundry/b", "model": "ignored"}) == {"provider": "foundry", "model": "b"}
    assert chat_settings_body({"llm": "gemini", "model": "  "}) == {"provider": "gemini", "model": None}
    assert chat_settings_body({"llm": "gemini", "model": " x "}) == {"provider": "gemini", "model": "x"}
    assert chat_settings_body({"provider": "gemini"}) == {"provider": "gemini", "model": None}
    assert chat_settings_body(None) == {"provider": None, "model": None}


def test_one_option_per_listed_model_or_provider_default():
    options = llm_options(CHOICES)
    assert options == {"azure · model mặc định": "azure", "foundry · a": "foundry/a", "foundry · b": "foundry/b"}
    assert has_free_model(CHOICES) and not has_free_model({**CHOICES, "providers": ["foundry"]})
    assert llm_options({"providers": ["gemini"], "default": "gemini"}) == {"gemini · model mặc định": "gemini"}


def test_choice_falls_back_when_the_backend_no_longer_offers_it():
    options = llm_options(CHOICES)
    assert pick_llm({"provider": "foundry", "model": "b"}, options, "azure") == "foundry/b"
    assert pick_llm({"provider": "azure", "model": "custom"}, options, "foundry") == "azure"
    assert pick_llm({"provider": "foundry", "model": "gone"}, options, "azure") == "azure"
    assert pick_llm(None, options, "foundry") == "foundry/a"
    assert pick_llm({"provider": "kimi"}, llm_options({**CHOICES, "providers": ["foundry"]}), "kimi") == "foundry/a"


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


def test_source_label_is_short():
    assert source_label(PROVISION) == "Điều 11 · QĐ 2933/2021 · tr. 12–13"
    assert source_label({"id": "x", "title": "Khoản 5.5", "source": "", "pages": [7]}) == "Khoản 5.5 · tr. 7"
    long = {"id": "x", "title": "Sổ tay sinh viên " * 5, "source": "So_tay_2025.pdf", "pages": []}
    assert source_label(long) == "Sổ tay sinh viên Sổ tay sinh viên Sổ tay…" + " · So_tay_2025"
    assert source_label({"id": "QD-X", "title": "", "pages": []}) == "QD-X"


def test_provision_panel_says_where_it_comes_from_and_that_it_is_a_draft():
    text = provision_markdown(PROVISION)
    assert "`HCMUT_QD2933_2021.pdf`" in text and "**Trang PDF:** 12–13" in text and "`QD2933-2021-ART11`" in text
    assert "Bản nháp, chưa được duyệt" in text and "Điều 11.Phân ngành\n11.1 Phân ngành" in text
    assert "Bản nháp" not in provision_markdown({**PROVISION, "verified": True})


def test_source_text_is_shown_as_is():
    assert plain_markdown("- a *b*\n| c |\n# d\n2. e") == "\\- a \\*b\\*\n\\| c \\|\n\\# d\n2\\. e"
    assert plain_markdown("<script>") == "\\<script\\>"
    assert plain_markdown("\n    PHỤ LỤC 4\n\n\n\n  1. Quy định\n") == "PHỤ LỤC 4\n1\\. Quy định"


def test_verification_line_under_an_answer():
    assert verification_line(TRACE).startswith("_✓ Verifier đã kiểm") and verification_line(TRACE).endswith("_")
    assert "1 điều khoản trích dẫn" in verification_line(TRACE)
    assert "viết lại 2 lần" in verification_line({**TRACE, "verifier_rounds": 3})
    template = verification_line({**TRACE, "llm": None, "citations": []})
    assert "trả lời theo mẫu, không qua LLM" in template and "trích dẫn" not in template
    assert verification_line({**TRACE, "verifier_rounds": None}).startswith("_Không qua Verifier")
    refused = verification_line({**TRACE, "verifier_rounds": None, "outcome": "refuse", "llm": None})
    assert refused.startswith("_Từ chối theo quy tắc") and "Verifier" not in refused
    assert "LLM lỗi một phần" in verification_line({**TRACE, "llm_error": "hết quota"})
