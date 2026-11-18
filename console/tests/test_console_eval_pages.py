from console_fakes import PASSWORD, TOKEN, FakeBackend, signed_in
from fastapi.testclient import TestClient

from co5151_console.adapters.backend_agent import HttpAnswerAgent
from co5151_console.adapters.backend_http import HttpBackendAdmin
from co5151_console.config import Settings
from co5151_console.container import build_container
from co5151_console.web.app import create_app


def client(tmp_path, background=lambda work: work()) -> TestClient:
    backend = FakeBackend(answers={"Học phí?": "Không có trong quy chế."})
    admin = HttpBackendAdmin("http://backend", TOKEN, transport=backend.transport())
    agent = HttpAnswerAgent("http://backend", "demo", transport=backend.transport())
    settings = Settings(database=tmp_path / "c.db", password=PASSWORD)
    container = build_container(settings, admin=admin, agent=agent, background=background)
    return signed_in(create_app(container))


def make_set(c: TestClient) -> str:
    page = c.post("/question-sets", data={"name": "Bộ thử"}, follow_redirects=False).headers["location"]
    c.post(f"{page}/tasks", data={"id": "O01", "group": "out_of_scope", "question": "Học phí?", "expected": "refuse"})
    return page.rsplit("/", 1)[1]


def test_confirm_then_run_then_read_the_results(tmp_path):
    c = client(tmp_path)
    assert "Chưa có bộ câu hỏi" in c.get("/eval").text
    set_id = make_set(c)
    confirm = c.get("/eval/confirm", params={"set_id": set_id}).text
    assert "1 câu" in confirm and "5 lời gọi LLM" in confirm
    started = c.post("/eval/runs", data={"set_id": set_id}, follow_redirects=False)
    assert started.status_code == 303
    page = c.get(started.headers["location"]).text
    assert "done" in page and "O01" in page and 'href="/traces/t1"' in page and "Không có trong quy chế." in page
    assert 'http-equiv="refresh"' not in page and "Đúng kết cục" in page
    assert "#1" in c.get("/eval").text and c.get("/eval/runs/99").status_code == 404


def test_a_running_run_refreshes_and_blocks_another(tmp_path):
    c = client(tmp_path, background=lambda work: None)  # never finishes
    set_id = make_set(c)
    page = c.get(c.post("/eval/runs", data={"set_id": set_id}, follow_redirects=False).headers["location"]).text
    assert 'http-equiv="refresh"' in page and "0/1" in page
    again = c.post("/eval/runs", data={"set_id": set_id})
    assert again.status_code == 422 and "chưa xong" in again.text
