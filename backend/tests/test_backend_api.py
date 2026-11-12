from fastapi.testclient import TestClient

from co5151_backend.api.app import create_app
from co5151_backend.container import build_container
from co5151_backend.infrastructure.config import Settings


def test_health():
    settings = Settings(token_secret=b"t", student_token_secret=b"s", database_url=None)
    with TestClient(create_app(build_container(settings))) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
