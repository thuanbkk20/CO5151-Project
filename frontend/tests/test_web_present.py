from web_fakes import CONVERSATION, TRACE

from co5151_web.present import chat_settings_body, details_markdown, progress_line, thread_dict


def test_progress_lines():
    assert progress_line({"name": "plan", "action": "SUMMARY"}) == "Lập kế hoạch: SUMMARY"
    assert progress_line({"name": "write", "revision": True}) == "Soạn câu trả lời (viết lại)"
    assert progress_line({"name": "khac"}) == "khac"


def test_details_show_the_trace():
    text = details_markdown(TRACE)
    assert "get_my_academic_summary" in text and "QD-Đ22" in text and "1350" in text and "`t1`" in text
    assert "Lỗi LLM" not in text
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
