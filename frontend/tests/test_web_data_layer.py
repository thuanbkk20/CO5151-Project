import pytest
from chainlit.types import Feedback, Pagination, ThreadFilter
from chainlit.user import User
from web_fakes import CONVERSATION, TOKEN, USER, FakeBackend

from co5151_web.history import TOKEN_KEY, BackendDataLayer

pytestmark = pytest.mark.anyio


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
async def layer(backend):
    layer = BackendDataLayer(backend.client())
    await layer.create_user(User(identifier=USER["id"], metadata={"role": "student", TOKEN_KEY: TOKEN}))
    return layer


async def test_create_user_keeps_the_token_on_the_server_only(backend):
    layer = BackendDataLayer(backend.client())
    persisted = await layer.create_user(User(identifier="sv002", metadata={"role": "student", TOKEN_KEY: TOKEN}))
    assert persisted.metadata == {"role": "student"}
    assert layer.token_for("sv002") == TOKEN
    assert await layer.get_user("sv002") is None  # so Chainlit hands over the cookie's user on every request


async def test_threads_are_read_with_the_users_token(layer):
    page = await layer.list_threads(Pagination(first=20), ThreadFilter(userId=USER["id"]))
    assert [t["id"] for t in page.data] == [CONVERSATION["id"]]
    assert page.pageInfo.hasNextPage and page.pageInfo.endCursor == "c2"
    assert await layer.get_thread_author(CONVERSATION["id"]) == USER["id"]
    assert await layer.get_thread_author("khong-co") == ""
    assert (await layer.get_thread(CONVERSATION["id"]))["steps"][1]["id"] == "m2"


async def test_unknown_user_sees_nothing(layer):
    page = await layer.list_threads(Pagination(first=20), ThreadFilter(userId="nguoi-khac"))
    assert page.data == []


async def test_update_thread_creates_or_renames_and_ignores_session_metadata(layer, backend):
    await layer.update_thread(CONVERSATION["id"], name="Câu hỏi đầu", user_id=USER["id"])
    await layer.update_thread(CONVERSATION["id"], name="Tên mới")
    await layer.update_thread(CONVERSATION["id"], metadata={"chat_settings": {}})
    assert backend.requests == [("POST", "/conversations", {"id": CONVERSATION["id"]}),
                                ("PATCH", f"/conversations/{CONVERSATION['id']}", {"title": "Tên mới"})]  # fmt: skip


async def test_feedback_targets_the_backend_message(layer, backend):
    assert await layer.upsert_feedback(Feedback(forId="m2", value=0, comment="sai")) == "m2"
    assert await layer.delete_feedback("m2")
    assert backend.requests == [("PUT", "/messages/m2/feedback", {"value": 0, "comment": "sai"}),
                                ("DELETE", "/messages/m2/feedback", None)]  # fmt: skip


def test_app_registers_the_data_layer():
    from chainlit.data import get_data_layer

    from co5151_web import app

    assert get_data_layer() is app.LAYER
