from pathlib import Path

from console_fakes import PASSWORD, signed_in
from fastapi.testclient import TestClient

from co5151_console.config import Settings
from co5151_console.container import build_container
from co5151_console.web.app import create_app
from co5151_console.web.auth import COOKIE, Sessions


def test_settings_from_env():
    s = Settings.from_env({"BACKEND_URL": "http://b:9/", "BACKEND_ADMIN_TOKEN": " t ", "CONSOLE_DATABASE": "x.db"})
    assert (s.backend_url, s.admin_token, s.database, s.port) == ("http://b:9", "t", Path("x.db"), 8200)
    assert Settings.from_env({}).admin_token is None


def test_home_has_the_sidebar_and_one_card_per_feature(tmp_path):
    client = signed_in(create_app(build_container(Settings(database=tmp_path / "c.db", password=PASSWORD))))
    page = client.get("/").text
    assert 'class="sidebar"' in page and "Tổng quan" in page
    assert page.count('class="card"') == 4 and 'class="card" href="/sessions"' in page and "chưa đặt" not in page
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}


def app(tmp_path, password: str | None = PASSWORD):
    return create_app(build_container(Settings(database=tmp_path / "c.db", password=password)))


def test_settings_of_the_operator_account():
    s = Settings.from_env({"CONSOLE_USERNAME": " ops ", "CONSOLE_PASSWORD": " demo "})
    assert (s.username, s.password) == ("ops", "demo")
    assert (Settings.from_env({}).username, Settings.from_env({"CONSOLE_PASSWORD": " "}).password) == ("admin", None)


def test_every_page_needs_sign_in_except_login_static_and_health(tmp_path):
    c = TestClient(app(tmp_path))
    to_login = c.get("/traces?conversation_id=x", follow_redirects=False)
    assert to_login.status_code == 303 and to_login.headers["location"] == "/login?next=%2Ftraces%3Fconversation_id%3Dx"
    posted = c.post("/question-sets", data={"name": "x"}, follow_redirects=False)
    assert posted.headers["location"] == "/login?next=%2F"  # a form is not replayed after sign-in
    panel = c.get("/traces/t1", params={"panel": 1})
    assert panel.status_code == 401 and 'href="/login"' in panel.text
    assert c.get("/static/style.css").status_code == 200 and c.get("/healthz").status_code == 200
    page = c.get("/login", params={"next": "/sessions"}).text
    assert 'name="next" value="/sessions"' in page and "chưa ai đăng nhập được" not in page


def test_sign_in_goes_to_next_then_sign_out(tmp_path):
    c = TestClient(app(tmp_path))
    wrong = c.post("/login", data={"username": "admin", "password": "sai", "next": "/sessions"})
    assert wrong.status_code == 401 and "Sai tên đăng nhập hoặc mật khẩu" in wrong.text and COOKIE not in c.cookies
    ok = c.post("/login", data={"username": "admin", "password": PASSWORD, "next": "/eval"}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/eval"
    cookie = ok.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    home = c.get("/")
    assert home.status_code == 200 and "Đăng xuất" in home.text and ">admin<" in home.text
    assert c.post("/logout", follow_redirects=False).headers["location"] == "/login"
    assert c.get("/", follow_redirects=False).status_code == 303


def test_next_never_leaves_the_console(tmp_path):
    c = TestClient(app(tmp_path))
    for target in ("//evil.example", "https://evil.example", "/\\evil.example"):
        signed = c.post("/login", data={"username": "admin", "password": PASSWORD, "next": target},
                        follow_redirects=False)  # fmt: skip
        assert signed.headers["location"] == "/"
        assert 'name="next" value="/"' in c.get("/login", params={"next": target}).text


def test_no_password_set_means_nobody_signs_in(tmp_path):
    c = TestClient(app(tmp_path, password=None))
    assert "chưa ai đăng nhập được" in c.get("/login").text
    assert c.post("/login", data={"username": "admin", "password": ""}).status_code in (401, 422)
    assert c.post("/login", data={"username": "admin", "password": "None"}).status_code == 401


def test_session_cookie_is_signed_and_expires():
    sessions = Sessions("admin", "pw", ttl=60, key=b"k" * 32)
    cookie = sessions.issue(now=1000)
    assert sessions.user(cookie, now=1059) == "admin" and sessions.user(cookie, now=1060) is None
    payload, sig = cookie.split(".")
    forged = Sessions("admin", "pw", key=b"x" * 32).issue(now=1000)
    assert sessions.user(forged, now=1000) is None and sessions.user(payload + ".", now=1000) is None
    assert sessions.user("rac", now=1000) is None and sessions.user(None) is None
    assert not sessions.check("Admin", "pw") and not sessions.check("admin", "PW") and sessions.check("admin", "pw")
