"""Thin compatibility layer over the official `mcp` Python SDK (v1.x FastMCP and v2.x MCPServer).

Server side: build a server, optionally protected by Bearer-token auth (OAuth 2.1 resource-server
pattern from the MCP authorization spec), and run it over stdio or Streamable HTTP.
Client side: open an initialized Streamable HTTP session that sends `Authorization: Bearer <token>`
(used by the host app / agents and by the end-to-end tests).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server

    SDK_MAJOR = 2
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

    SDK_MAJOR = 1

from mcp import ClientSession
from mcp.server.auth.middleware.auth_context import get_access_token  # noqa: F401  (re-exported)
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

from co5151_contracts import SCOPE_RECORDS_READ

from .auth import AuthError, TokenSigner


class SessionTokenVerifier:
    """Validates the per-user session token on EVERY HTTP request.

    Returning None makes the SDK's bearer middleware answer HTTP 401 before any tool runs.
    In production this would validate a JWT from the university SSO (signature, expiry, audience).
    """

    def __init__(self, signer: TokenSigner):
        self._signer = signer

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = self._signer.verify(token)
        except AuthError:
            return None
        return AccessToken(token=token, client_id=claims.sub, scopes=[SCOPE_RECORDS_READ], expires_at=claims.exp)


def make_server(name: str, instructions: str, *, host: str, port: int, verifier=None, issuer_url: str = "") -> Any:
    kw: dict[str, Any] = {"instructions": instructions}
    if verifier is not None:
        extra = {"validate_token_resource": False} if "validate_token_resource" in AuthSettings.model_fields else {}
        kw["token_verifier"] = verifier
        kw["auth"] = AuthSettings(
            issuer_url=issuer_url,
            resource_server_url=f"http://{host}:{port}",
            required_scopes=[SCOPE_RECORDS_READ],
            **extra,
        )
    if SDK_MAJOR == 1:
        kw.update(host=host, port=port)
    return _Server(name, **kw)


def http_app(server: Any) -> Any:
    """The Starlette ASGI app serving Streamable HTTP at /mcp (with auth middleware when protected)."""
    return server.streamable_http_app()


def run(server: Any, transport: str, *, host: str, port: int) -> None:
    if transport == "stdio":
        server.run("stdio")
    elif SDK_MAJOR == 1:
        server.run(transport="streamable-http")
    else:
        server.run("streamable-http", host=host, port=port)


@asynccontextmanager
async def open_session(url: str, token: str | None = None, timeout: float = 30) -> AsyncIterator[ClientSession]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if SDK_MAJOR == 2:
        import httpx2
        from mcp.client.streamable_http import streamable_http_client

        async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http:
            async with streamable_http_client(url, http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    yield session
    else:
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(url, headers=headers, timeout=timeout) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                yield session
