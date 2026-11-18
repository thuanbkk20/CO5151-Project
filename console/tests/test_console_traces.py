from console_fakes import ITEM, PASSWORD, SESSION, SPANS, TOKEN, FakeBackend, signed_in
from fastapi.testclient import TestClient

from co5151_console.adapters.backend_http import HttpBackendAdmin
from co5151_console.config import Settings
from co5151_console.container import build_container
from co5151_console.services.traces import TraceBrowser
from co5151_console.web.app import create_app


def browser(backend: FakeBackend | None = None) -> TraceBrowser:
    return TraceBrowser(HttpBackendAdmin("http://backend", TOKEN, transport=(backend or FakeBackend()).transport()))


def client(tmp_path, backend: FakeBackend | None = None, token: str | None = TOKEN) -> TestClient:
    admin = HttpBackendAdmin("http://backend", token, transport=(backend or FakeBackend()).transport())
    return signed_in(create_app(build_container(Settings(database=tmp_path / "c.db", password=PASSWORD), admin=admin)))


def test_rows_say_who_asked_what_and_how_it_ended():
    [row] = browser().recent(SESSION)
    assert (row.owner, row.question, row.result, row.tone) == ("sv002", "Điều kiện tốt nghiệp?", "LLM viết", "ok")
    assert (row.tokens, row.seconds, row.created_at) == (1350, 2.5, "2026-11-15 08:00:00")


def test_detail_is_the_flow_of_nodes():
    detail = browser().detail("t1")
    assert [n.label for n in detail.nodes] == ["Planner", "MCP Regulation", "Advisor viết câu trả lời", "Verifier"]
    planner, regulation, writer, verifier = detail.nodes
    assert planner.summary == "→ SUMMARY (bởi rule)" and regulation.summary == "1 điều khoản: QD-Đ22"
    assert writer.summary == "[gemini/x] Theo Điều 22..." and writer.tokens == 1020
    assert (verifier.summary, verifier.tone) == ("REVISE · Sai số tín chỉ.", "warn")
    assert '"provision_id": "QD-Đ22"' in regulation.output and detail.question == ITEM["question"]
    assert browser().detail("khong-co") is None


def test_failures_have_the_error_tone():
    failed = {**SPANS[1], "output": {"ok": False, "error": {"code": "INTERNAL", "message": "down"}}}
    crashed = {**SPANS[0], "error": "RuntimeError: db down"}
    item = {**ITEM, "trace": {**ITEM["trace"], "error": "RuntimeError: db down"}, "spans": [failed, crashed]}

    class Admin:
        def trace(self, trace_id):
            return item

    detail = TraceBrowser(Admin()).detail("t1")
    assert (detail.row.result, detail.row.tone) == ("lỗi", "error")
    assert [(n.summary, n.tone) for n in detail.nodes] == [("Lỗi INTERNAL: down", "error"),
                                                          ("RuntimeError: db down", "error")]  # fmt: skip


def test_traces_pages(tmp_path):
    c = client(tmp_path)
    page = c.get("/traces", params={"session": SESSION}).text
    assert "Điều kiện tốt nghiệp?" in page and 'href="/traces/t1"' in page and 'class="active"' in page
    assert "Không có trace nào cho session này" in c.get("/traces", params={"session": "khac"}).text
    detail = c.get("/traces/t1").text
    assert "MCP Regulation" in detail and "Sai số tín chỉ." in detail and "Theo Điều 22..." in detail
    assert c.get("/traces/khong-co").status_code == 404
    panel = c.get("/traces/t1", params={"panel": 1}).text
    assert "MCP Regulation" in panel and 'class="sidebar"' not in panel and "← Traces" not in panel
    assert 'class="sidebar"' in detail and "data-panel" in page and "panel.js" in page


def test_configuration_problems_show_on_the_page(tmp_path):
    assert "Chưa đặt BACKEND_ADMIN_TOKEN" in client(tmp_path, token=None).get("/traces").text
    disabled = client(tmp_path, FakeBackend(admin_enabled=False))
    assert "chưa bật API admin" in disabled.get("/traces").text
    # The backend hides a disabled admin API behind the same 404 as a missing trace.
    assert disabled.get("/traces/t1").status_code == 404
    down = client(tmp_path, FakeBackend(), token="sai").get("/traces/t1")
    assert down.status_code == 502 and "từ chối token admin" in down.text
