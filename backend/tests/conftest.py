import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def no_repo_env_file(monkeypatch):
    """Tests never read the repo's .env (it may hold real LLM keys)."""
    monkeypatch.setattr("co5151_backend.cli.find_env_file", lambda: None)


# Real MCP servers on free local ports, for the gateway tests ---------------------------------------------------

STUDENT_SECRET = b"backend-test-shared-secret"


def _serve(app):
    import socket
    import threading
    import time

    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("MCP server did not start")
        time.sleep(0.05)
    return server, thread, f"http://127.0.0.1:{port}/mcp"


@pytest.fixture
def student_token():
    """A Student Record token for a demo account, signed with the secret of `student_mcp_url`."""
    from co5151_backend.infrastructure.identity import DemoAccountDirectory, SignedStudentTokens

    return lambda username: SignedStudentTokens(STUDENT_SECRET, ttl=60).issue(DemoAccountDirectory().get(username))


@pytest.fixture(scope="session")
def student_mcp_url():
    from student_server import mcp_compat
    from student_server.config import Settings
    from student_server.server import build_server, build_service

    settings = Settings(token_secret=STUDENT_SECRET)
    server, thread, url = _serve(mcp_compat.http_app(build_server(build_service(settings), settings)))
    yield url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def regulation_mcp_url():
    from pathlib import Path

    import regulation_server
    from regulation_server.regulation_mcp_v2 import http_app
    from regulation_server.regulation_service_v2 import RegulationServiceV2

    base = Path(regulation_server.__file__).resolve().parents[2]
    server, thread, url = _serve(http_app(RegulationServiceV2(base, allow_draft=True)))
    yield url
    server.should_exit = True
    thread.join(timeout=5)
