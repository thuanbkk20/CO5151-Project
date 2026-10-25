"""Student Record MCP server — ONE long-running process serving MANY users.

How multi-user isolation works
- Every HTTP request must carry `Authorization: Bearer <session token>` of the user it acts for.
  The SDK's bearer middleware calls SessionTokenVerifier on each request: missing / invalid /
  expired token → HTTP 401 before any tool runs.
- Inside a tool, `get_access_token()` returns the token of THE CURRENT REQUEST (context-local),
  so two users calling at the same time each read only their own record.
- The token travels in the transport header set by the host app, never in tool arguments, so the
  LLM can neither see nor swap it. Student tools take no student_id at all.

Dev-only fallback: stdio serves a single user whose token is given at start-up.
"""

import json
import logging
from collections.abc import Callable

from mcp.types import ToolAnnotations

from co5151_contracts import STUDENT_RECORD_TOOLS

from . import mcp_compat
from .audit import AccessLog
from .auth import TokenSigner
from .config import Settings
from .db import StudentDB
from .service import StudentRecordService

logger = logging.getLogger(__name__)

NAME = "student-record-mcp"
INSTRUCTIONS = (
    "Scoped, read-only access to the logged-in user's academic records. Identity comes from the session "
    "token, never from arguments. Every result is a JSON envelope {ok, data} | {ok: false, error: {code, message}}."
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

TokenProvider = Callable[[], "str | None"]


def request_token() -> str | None:
    """Token of the HTTP request being served (set by the SDK's bearer-auth middleware)."""
    at = mcp_compat.get_access_token()
    return at.token if at else None


def _tool_functions(run: Callable[[str, dict], str]) -> dict[str, Callable[..., str]]:
    """Typed entry points the SDK introspects. Arguments are re-validated against contracts in the service."""

    def get_my_profile() -> str:
        return run("get_my_profile", {})

    def get_my_academic_summary() -> str:
        return run("get_my_academic_summary", {})

    def get_my_transcript(semester: str | None = None) -> str:
        return run("get_my_transcript", {} if semester is None else {"semester": semester})

    def get_my_semester_summary() -> str:
        return run("get_my_semester_summary", {})

    def get_my_academic_decisions() -> str:
        return run("get_my_academic_decisions", {})

    def get_advisee_summary(student_id: str) -> str:
        return run("get_advisee_summary", {"student_id": student_id})

    fns = [get_my_profile, get_my_academic_summary, get_my_transcript, get_my_semester_summary,
           get_my_academic_decisions, get_advisee_summary]  # fmt: skip
    return {f.__name__: f for f in fns}


def build_service(settings: Settings) -> StudentRecordService:
    db = StudentDB(settings.db_path, settings.data_dir)
    return StudentRecordService(
        db, TokenSigner(settings.token_secret, settings.token_ttl), AccessLog(settings.token_secret)
    )


def build_server(service: StudentRecordService, settings: Settings, token_provider: TokenProvider = request_token,
                 protected: bool = True):  # fmt: skip
    verifier = mcp_compat.SessionTokenVerifier(service.signer) if protected else None
    server = mcp_compat.make_server(NAME, INSTRUCTIONS, host=settings.host, port=settings.port, verifier=verifier,
                                    issuer_url=settings.auth_issuer_url)  # fmt: skip

    def run(name: str, args: dict) -> str:
        res = service.call(name, token_provider(), args)
        return json.dumps(res.model_dump(mode="json", exclude_none=True), ensure_ascii=False)

    fns = _tool_functions(run)
    assert set(fns) == set(STUDENT_RECORD_TOOLS), "MCP entry points out of sync with the contract registry"
    for name, spec in STUDENT_RECORD_TOOLS.items():
        server.add_tool(fns[name], name=name, description=spec.description, annotations=READ_ONLY,
                        structured_output=False)  # fmt: skip
        # Advertise the contract schema (patterns, descriptions, additionalProperties=false) to clients.
        server._tool_manager.get_tool(name).parameters = spec.input_schema()
    return server


def serve(settings: Settings, transport: str = "http", stdio_token: str | None = None) -> None:
    service = build_service(settings)
    if transport == "stdio":
        # Single-user dev mode: no HTTP layer, so the token is fixed at start-up.
        server = build_server(service, settings, token_provider=lambda: stdio_token, protected=False)
        mcp_compat.run(server, "stdio", host=settings.host, port=settings.port)
        return
    server = build_server(service, settings)
    logger.info("Student Record MCP on http://%s:%d/mcp (Bearer token required)", settings.host, settings.port)
    mcp_compat.run(server, "streamable-http", host=settings.host, port=settings.port)
