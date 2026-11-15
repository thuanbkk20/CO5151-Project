from pathlib import Path

from fastapi.testclient import TestClient

from co5151_console.config import Settings
from co5151_console.container import build_container
from co5151_console.web.app import create_app


def test_settings_from_env():
    s = Settings.from_env({"BACKEND_URL": "http://b:9/", "BACKEND_ADMIN_TOKEN": " t ", "CONSOLE_DATABASE": "x.db"})
    assert (s.backend_url, s.admin_token, s.database, s.port) == ("http://b:9", "t", Path("x.db"), 8200)
    assert Settings.from_env({}).admin_token is None


def test_home_has_the_sidebar_and_one_card_per_feature(tmp_path):
    client = TestClient(create_app(build_container(Settings(database=tmp_path / "c.db"))))
    page = client.get("/").text
    assert 'class="sidebar"' in page and "Tổng quan" in page
    assert page.count('class="card"') == 4 and 'class="card" href="/sessions"' in page and "chưa đặt" not in page
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}
