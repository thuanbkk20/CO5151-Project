import pytest

from co5151_chat_store import ChatStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def store(tmp_path):
    store = ChatStore.from_url(f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}")
    await store.create_schema()
    yield store
    await store.close()
