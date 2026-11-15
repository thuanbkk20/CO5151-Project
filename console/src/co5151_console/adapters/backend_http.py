"""The backend's admin API over HTTP (httpx). The admin token stays here, never in a page."""

from typing import Any

import httpx

from ..ports import BackendError

TIMEOUT = httpx.Timeout(10.0)


class HttpBackendAdmin:
    def __init__(self, base_url: str, admin_token: str | None, transport: httpx.BaseTransport | None = None):
        self._token = admin_token
        self._http = httpx.Client(base_url=base_url, timeout=TIMEOUT, transport=transport)

    def _get(self, path: str, **params: Any) -> httpx.Response:
        if not self._token:
            raise BackendError("Chưa đặt BACKEND_ADMIN_TOKEN trong .env (phải giống bên backend).")
        try:
            res = self._http.get(path, params={k: v for k, v in params.items() if v is not None},
                                 headers={"Authorization": f"Bearer {self._token}"})  # fmt: skip
        except httpx.HTTPError as e:
            raise BackendError(f"Không kết nối được backend ({self._http.base_url}): {type(e).__name__}") from e
        if res.status_code == 401:
            raise BackendError("Backend từ chối token admin: BACKEND_ADMIN_TOKEN hai bên phải giống nhau.")
        return res

    def traces(self, *, conversation_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        res = self._get("/admin/traces", conversation_id=conversation_id, limit=limit)
        if res.status_code == 404:
            raise BackendError("Backend chưa bật API admin (BACKEND_ADMIN_TOKEN trống ở backend).")
        _raise_for(res)
        return res.json()["items"]

    def trace(self, trace_id: str) -> dict[str, Any] | None:
        res = self._get(f"/admin/traces/{trace_id}")
        if res.status_code == 404:
            return None
        _raise_for(res)
        return res.json()


def _raise_for(res: httpx.Response) -> None:
    if res.status_code >= 400:
        raise BackendError(f"Backend trả lỗi {res.status_code}: {res.text[:200]}")
