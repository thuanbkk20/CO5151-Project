from console_fakes import FakeBackend
from fastapi.testclient import TestClient

from co5151_console.adapters.backend_http import HttpBackendAdmin
from co5151_console.config import Settings
from co5151_console.container import build_container
from co5151_console.web.app import create_app


def client(tmp_path) -> TestClient:
    admin = HttpBackendAdmin("http://backend", None, transport=FakeBackend().transport())
    return TestClient(create_app(build_container(Settings(database=tmp_path / "c.db"), admin=admin)))


def test_create_a_set_add_edit_and_delete_a_task(tmp_path):
    c = client(tmp_path)
    created = c.post("/question-sets", data={"name": "Bộ thử"}, follow_redirects=False)
    assert created.status_code == 303
    page = created.headers["location"]
    assert "Bộ thử" in c.get("/question-sets").text and "chưa có câu nào" in c.get(page).text

    task = {"id": "N01", "group": "basic", "question": "Học phí bao nhiêu?", "expected": "answer",
            "also_accept": ["clarify"]}  # fmt: skip
    assert c.post(f"{page}/tasks", data=task, follow_redirects=False).status_code == 303
    assert "Học phí bao nhiêu?" in c.get(page).text
    form = c.get(f"{page}/tasks/N01").text
    assert 'value="N01"' in form and 'value="clarify" checked' in form

    edited = c.post(f"{page}/tasks", data={**task, "editing": "N01", "id": "N02"})
    assert edited.status_code == 200 and "N02" in edited.text and "/tasks/N01" not in edited.text
    duplicate = c.post(f"{page}/tasks", data={**task, "id": "N02"})
    assert duplicate.status_code == 422 and "đã có câu N02" in duplicate.text

    c.post(f"{page}/tasks/N02/delete")
    assert "chưa có câu nào" in c.get(page).text
    c.post(f"{page}/delete")
    assert c.get(page).status_code == 404


def test_import_the_default_set_once(tmp_path):
    c = client(tmp_path)
    page = c.post("/question-sets/import-default").text
    assert "B01" in page and "Thời gian tối đa" in page
    again = c.post("/question-sets/import-default")
    assert again.status_code == 422 and "Đã có bộ câu hỏi" in again.text
    assert c.post("/question-sets", data={"name": " "}).status_code == 422
