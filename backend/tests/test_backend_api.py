"""The HTTP API over the real container, with in-memory and fake adapters (no MCP server, no LLM)."""

import json

import pytest
from backend_fakes import GRADUATION, Model, Models, Regulations, Student
from fastapi.testclient import TestClient

from co5151_backend.api.app import create_app
from co5151_backend.container import Adapters, build_container
from co5151_backend.infrastructure.config import Settings

SETTINGS = Settings(token_secret=b"api-test-secret-at-least-32-bytes", student_token_secret=b"s", database_url=None,
                    planner_mode="rule", verifier_mode="rules")  # fmt: skip
CONV = "0b8f6a3e-7c1e-4a37-9a6c-3f2d9b8e1a11"


@pytest.fixture
def client():
    adapters = Adapters(student=Student(), regulations=Regulations(), models=Models(Model(*["Bạn đủ điều kiện."] * 5)))
    with TestClient(create_app(build_container(SETTINGS, adapters))) as client:
        yield client


def login(client, username="sv001") -> dict:
    res = client.post("/auth/login", json={"username": username, "password": "demo"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_health_and_auth(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.post("/auth/login", json={"username": "sv001", "password": "x"}).status_code == 401
    assert client.get("/conversations").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert client.get("/me", headers=login(client)).json() == {"id": "sv001", "role": "student",
                                                                "display_name": "sv001"}  # fmt: skip
    guest = client.get("/me", headers=login(client, "khach")).json()
    assert guest["role"] == "guest" and guest["id"].startswith("khach-")


def test_conversation_lifecycle(client):
    auth = login(client)
    assert client.get("/llm/providers", headers=auth).json() == {"providers": ["fake"], "default": "fake"}
    res = client.post("/conversations", json={"id": CONV, "settings": {"provider": "fake"}}, headers=auth)
    assert res.status_code == 201 and res.json()["settings"] == {"provider": "fake", "model": None}
    assert client.post("/conversations", json={"settings": {"provider": "openai"}}, headers=auth).status_code == 422
    assert client.post("/conversations", json={"unknown": 1}, headers=auth).status_code == 422

    answer = client.post(f"/conversations/{CONV}/messages", json={"content": GRADUATION}, headers=auth).json()
    assert answer["message"]["content"] == "Bạn đủ điều kiện." and answer["trace"]["verifier_rounds"] == 1
    assert answer["trace"]["tool_calls"] == ["get_my_academic_summary", "search_regulations"]

    detail = client.get(f"/conversations/{CONV}", headers=auth).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"] and detail["title"] == GRADUATION
    answer_id = detail["messages"][1]["id"]
    assert client.put(f"/messages/{answer_id}/feedback", json={"value": 1}, headers=auth).status_code == 204
    assert client.put(f"/messages/{answer_id}/feedback", json={"value": 3}, headers=auth).status_code == 422
    assert client.get(f"/conversations/{CONV}", headers=auth).json()["messages"][1]["feedback"] == {
        "value": 1, "comment": None}  # fmt: skip
    trace = client.get(f"/traces/{answer['trace']['trace_id']}", headers=auth).json()
    assert trace["answer_message_id"] == answer_id

    renamed = client.patch(f"/conversations/{CONV}", json={"title": "Luận văn"}, headers=auth).json()
    assert renamed["title"] == "Luận văn"
    assert [c["id"] for c in client.get("/conversations", headers=auth).json()["items"]] == [CONV]
    assert client.delete(f"/conversations/{CONV}", headers=auth).status_code == 204
    assert client.get(f"/conversations/{CONV}", headers=auth).status_code == 404


def test_other_users_see_nothing(client):
    owner, other = login(client, "sv001"), login(client, "sv002")
    client.post("/conversations", json={"id": CONV}, headers=owner)
    assert client.get(f"/conversations/{CONV}", headers=other).status_code == 404
    assert client.post(f"/conversations/{CONV}/messages", json={"content": "x"}, headers=other).status_code == 404
    assert client.post("/conversations", json={"id": CONV}, headers=other).status_code == 404
    assert client.get("/conversations", headers=other).json()["items"] == []


def test_stream_sends_steps_then_the_verified_answer(client):
    auth = login(client)
    client.post("/conversations", json={"id": CONV}, headers=auth)
    with client.stream("POST", f"/conversations/{CONV}/messages/stream", json={"content": GRADUATION},
                       headers=auth) as res:  # fmt: skip
        assert res.headers["content-type"].startswith("text/event-stream")
        events = [line.removeprefix("event: ") for line in res.iter_lines() if line.startswith("event: ")]
    assert events[0] == "step" and events[-1] == "answer" and "error" not in events
    assert (
        client.post(f"/conversations/{CONV}x/messages/stream", json={"content": "x"}, headers=auth).status_code == 404
    )


def test_stream_reports_a_failure_with_its_trace_id():
    adapters = Adapters(student=Student(fail=RuntimeError("down")), regulations=Regulations(), models=Models(None))
    with TestClient(create_app(build_container(SETTINGS, adapters))) as client:
        auth = login(client)
        client.post("/conversations", json={"id": CONV}, headers=auth)
        with client.stream("POST", f"/conversations/{CONV}/messages/stream", json={"content": GRADUATION},
                           headers=auth) as res:  # fmt: skip
            lines = list(res.iter_lines())
        error = json.loads(lines[lines.index("event: error") + 1].removeprefix("data: "))
        assert error["detail"] == "answer failed" and len(error["trace_id"]) == 32
        res = client.post(f"/conversations/{CONV}/messages", json={"content": GRADUATION}, headers=auth)
        assert res.status_code == 500 and len(res.json()["trace_id"]) == 32
