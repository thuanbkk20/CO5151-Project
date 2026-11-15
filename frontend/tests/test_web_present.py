from web_fakes import CONVERSATION, SPANS, TRACE

from co5151_web.present import (
    answer_choices,
    answers_of_thread,
    chat_settings_body,
    details_markdown,
    empty_flow_props,
    flow_props,
    pick_provider,
    progress_line,
    thread_dict,
)


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


def test_provider_falls_back_when_its_key_is_gone():
    assert pick_provider("openai", ["gemini", "openai"], "gemini") == "openai"
    assert pick_provider("kimi", ["gemini", "openai"], "openai") == "openai"
    assert pick_provider(None, ["openai"], "gemini") == "openai"


def test_flow_props_show_each_node_in_order():
    props = flow_props("Điều kiện tốt nghiệp?", "Theo Điều 22...", SPANS, TRACE)
    assert [n["label"] for n in props["nodes"]] == ["Planner", "MCP Student Record", "MCP Regulation",
                                                    "Advisor viết câu trả lời", "Verifier"]  # fmt: skip
    planner, student, regulation, writer, verifier = props["nodes"]
    assert planner["summary"] == "→ SUMMARY (bởi rule)" and student["summary"] == "Trả về 1 trường hồ sơ"
    assert regulation["summary"] == "1 điều khoản: QD-Đ22" and '"credits_earned": 113' in student["output"]
    assert writer["summary"] == "[gemini/x] Theo Điều 22..." and writer["tokens"] == 1020
    assert (verifier["summary"], verifier["tone"]) == ("PASS", "ok")
    assert (props["total_ms"], props["total_tokens"], props["answer"]) == (2500, 1350, "Theo Điều 22...")


def test_flow_props_flag_failures():
    failed_tool = {**SPANS[2], "output": {"ok": False, "error": {"code": "INTERNAL", "message": "down"}}}
    revise = {**SPANS[4], "output": {"status": "revise", "issues": [{"code": "X", "message": "Sai số tín chỉ."}]}}
    crashed = {**SPANS[1], "error": "RuntimeError: db down"}
    nodes = flow_props("q", None, [failed_tool, revise, crashed], None)["nodes"]
    assert [(n["summary"], n["tone"]) for n in nodes] == [
        ("Lỗi INTERNAL: down", "error"),
        ("REVISE · Sai số tín chỉ.", "warn"),
        ("RuntimeError: db down", "error"),
    ]


def test_answers_of_a_reopened_thread_are_keyed_by_trace():
    answers = answers_of_thread(thread_dict(CONVERSATION, "sv002"))
    assert answers == {"t1": {"question": "Điều kiện tốt nghiệp?", "answer": "Theo Điều 22...", "message_id": "m2"}}
    assert answers_of_thread({"steps": []}) == {}


def test_picker_lists_the_answers_by_question():
    flows = {"t1": {"question": "Điều kiện tốt nghiệp?"}, "t2": {"question": "x" * 80}}
    assert answer_choices(flows) == [{"trace_id": "t1", "label": "#1 Điều kiện tốt nghiệp?"},
                                     {"trace_id": "t2", "label": "#2 " + "x" * 59 + "…"}]  # fmt: skip
    empty = empty_flow_props(flows)
    assert empty["empty"] and empty["nodes"] == [] and len(empty["answers"]) == 2
