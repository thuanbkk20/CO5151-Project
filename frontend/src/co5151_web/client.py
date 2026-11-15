"""HTTP client of the backend API. The frontend knows nothing else: no Advisor, no MCP, no LLM, no database."""

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

DEFAULT_URL = "http://127.0.0.1:8100"
# An answer may take several LLM calls (plan, write, verify, rewrite)
TIMEOUT = httpx.Timeout(10.0, read=180.0)


class BackendError(Exception):
    def __init__(self, status: int, detail: str = ""):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


class SessionExpired(BackendError):
    """401: the access token expired or was signed by another backend secret; the user has to sign in again."""


class BackendClient:
    def __init__(self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = (base_url or os.environ.get("BACKEND_URL") or DEFAULT_URL).rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=TIMEOUT, transport=transport)

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, token: str | None = None, **kw) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        res = await self._http.request(method, path, headers=headers, **kw)
        _raise_for(res)
        return res

    async def login(self, username: str, password: str) -> dict[str, Any] | None:
        """The session (`access_token`, `user`), or None for wrong credentials."""
        try:
            res = await self._request("POST", "/auth/login", json={"username": username, "password": password})
        except SessionExpired:
            return None
        return res.json()

    async def llm_providers(self, token: str) -> dict[str, Any]:
        return (await self._request("GET", "/llm/providers", token)).json()

    async def start(self, token: str, conversation_id: str, settings: dict | None = None) -> dict[str, Any]:
        body = {"id": conversation_id, **({"settings": settings} if settings else {})}
        return (await self._request("POST", "/conversations", token, json=body)).json()

    async def update(self, token: str, conversation_id: str, *, title: str | None = None,
                     settings: dict | None = None) -> dict[str, Any]:  # fmt: skip
        body = {k: v for k, v in {"title": title, "settings": settings}.items() if v is not None}
        return (await self._request("PATCH", f"/conversations/{conversation_id}", token, json=body)).json()

    async def delete(self, token: str, conversation_id: str) -> None:
        await self._request("DELETE", f"/conversations/{conversation_id}", token)

    async def conversations(self, token: str, *, limit: int = 20, cursor: str | None = None,
                            search: str | None = None) -> dict[str, Any]:  # fmt: skip
        params = {k: v for k, v in {"limit": limit, "cursor": cursor, "q": search}.items() if v}
        return (await self._request("GET", "/conversations", token, params=params)).json()

    async def conversation(self, token: str, conversation_id: str) -> dict[str, Any] | None:
        try:
            return (await self._request("GET", f"/conversations/{conversation_id}", token)).json()
        except BackendError as e:
            if e.status == 404:
                return None
            raise

    async def feedback(self, token: str, message_id: str, value: int | None, comment: str | None = None) -> None:
        if value is None:
            await self._request("DELETE", f"/messages/{message_id}/feedback", token)
        else:
            await self._request("PUT", f"/messages/{message_id}/feedback", token,
                                json={"value": value, "comment": comment})  # fmt: skip

    async def ask(self, token: str, conversation_id: str, content: str) -> AsyncIterator[tuple[str, dict]]:
        """Server-sent events of one answer: (`step`, data)* then (`answer` | `error`, data)."""
        headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
        path = f"/conversations/{conversation_id}/messages/stream"
        async with self._http.stream("POST", path, headers=headers, json={"content": content}) as res:
            if res.status_code >= 400:
                await res.aread()
                _raise_for(res)
            event = None
            async for line in res.aiter_lines():
                if line.startswith("event: "):
                    event = line.removeprefix("event: ")
                elif line.startswith("data: ") and event:
                    yield event, json.loads(line.removeprefix("data: "))
                    event = None


def _raise_for(res: httpx.Response) -> None:
    if res.status_code < 400:
        return
    try:
        detail = res.json().get("detail", "")
    except ValueError:
        detail = res.text
    raise (SessionExpired if res.status_code == 401 else BackendError)(res.status_code, str(detail))
