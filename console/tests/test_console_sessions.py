from console_fakes import ITEM, PASSWORD, SESSION, TOKEN, FakeBackend, signed_in

from co5151_console.adapters.backend_http import HttpBackendAdmin
from co5151_console.config import Settings
from co5151_console.container import build_container
from co5151_console.services.sessions import SessionBrowser
from co5151_console.web.app import create_app


def admin(backend: FakeBackend | None = None, token: str | None = TOKEN) -> HttpBackendAdmin:
    return HttpBackendAdmin("http://backend", token, transport=(backend or FakeBackend()).transport())


def test_sessions_and_the_turns_of_one_in_order():
    class TwoTurns:  # the admin API gives the newest trace first
        def traces(self, *, conversation_id=None, limit=50):
            later = {**ITEM, "question": "Còn tốt nghiệp?", "trace": {**ITEM["trace"], "trace_id": "t2"}}
            return [later, ITEM]

    [row] = SessionBrowser(admin()).all()
    assert (row.id, row.owner, row.title, row.turns, row.updated_at) == (SESSION, "sv002", "Điều kiện tốt nghiệp?",
                                                                          1, "2026-11-15 08:00:05")  # fmt: skip
    detail = SessionBrowser(TwoTurns()).detail(SESSION)
    assert [t.row.trace_id for t in detail.turns] == ["t1", "t2"] and detail.owner == "sv002"
    assert detail.turns[0].answer == "Theo Điều 22..." and detail.turns[1].question == "Còn tốt nghiệp?"
    assert SessionBrowser(admin(FakeBackend())).detail("khac").turns == []


def test_sessions_pages(tmp_path):
    c = signed_in(create_app(build_container(Settings(database=tmp_path / "c.db", password=PASSWORD), admin=admin())))
    page = c.get("/sessions").text
    assert f'href="/sessions/{SESSION}"' in page and "Điều kiện tốt nghiệp?" in page
    session = c.get(f"/sessions/{SESSION}").text
    assert "Theo Điều 22..." in session and 'href="/traces/t1" data-panel' in session and "1 lượt" in session
    assert "chưa có lượt nào" in c.get("/sessions/khac").text
    panel = c.get(f"/sessions/{SESSION}", params={"panel": 1}).text
    assert "Theo Điều 22..." in panel and 'class="sidebar"' not in panel and "← Sessions" not in panel
    assert f'href="/sessions/{SESSION}" data-panel' in page and 'id="panel-back"' in page
    assert f'href="/sessions/{SESSION}"' in c.get("/traces").text  # the Session column leads here
    settings = Settings(database=tmp_path / "d.db", password=PASSWORD)
    down = signed_in(create_app(build_container(settings, admin=admin(token="sai"))))
    assert "từ chối token admin" in down.get("/sessions").text
    assert down.get(f"/sessions/{SESSION}").status_code == 502
