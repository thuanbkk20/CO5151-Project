import httpx
import pytest
from console_fakes import ITEM, SESSION, SPANS, TOKEN, FakeBackend

from co5151_console.adapters.backend_http import HttpBackendAdmin
from co5151_console.ports import BackendError


def admin(backend: FakeBackend, token: str | None = TOKEN) -> HttpBackendAdmin:
    return HttpBackendAdmin("http://backend", token, transport=backend.transport())


def test_reads_traces_with_the_admin_token():
    backend = FakeBackend()
    assert admin(backend).traces(conversation_id=SESSION) == [ITEM]
    assert admin(backend).traces(conversation_id="khac") == []
    assert admin(backend).trace("t1")["spans"] == SPANS and admin(backend).trace("khong-co") is None
    assert backend.requests[0].url.params["conversation_id"] == SESSION
    admin(backend).traces()
    assert "conversation_id" not in backend.requests[-1].url.params


@pytest.mark.parametrize(
    ("backend", "token", "message"),
    [
        (FakeBackend(), None, "Chưa đặt BACKEND_ADMIN_TOKEN"),
        (FakeBackend(), "sai", "từ chối token admin"),
        (FakeBackend(admin_enabled=False), TOKEN, "chưa bật API admin"),
    ],
)
def test_configuration_problems_are_explained(backend, token, message):
    with pytest.raises(BackendError, match=message):
        admin(backend, token).traces()


def test_backend_down_is_explained():
    def down(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(BackendError, match="Không kết nối được backend"):
        HttpBackendAdmin("http://backend", TOKEN, transport=httpx.MockTransport(down)).traces()
