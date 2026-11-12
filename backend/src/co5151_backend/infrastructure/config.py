"""Settings of the backend, read once at start-up from the environment (`.env` is loaded by the CLI)."""

import os
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEV_SECRET = "dev-secret-change-me"
TRUE_VALUES = {"1", "true", "yes", "on"}
OFF_VALUES = {"off", "none", "false", "0"}
DEFAULT_DATABASE_FILE = Path(__file__).resolve().parents[3] / ".data" / "chat.db"


def _secret(env: Mapping[str, str], name: str) -> bytes:
    value = env.get(name, "").strip() or DEV_SECRET
    if value == DEV_SECRET:
        warnings.warn(f"{name} is not set; using the insecure dev secret", stacklevel=3)
    return value.encode()


@dataclass(frozen=True)
class Settings:
    token_secret: bytes  # signs the backend's access tokens
    student_token_secret: bytes  # signs Student Record tokens, shared with student-mcp
    token_ttl: int = 24 * 3600  # as long as a Chainlit sign-in (user_session_timeout)
    student_token_ttl: int = 300
    host: str = "127.0.0.1"
    port: int = 8100
    database_url: str | None = None  # None: chat history is not stored
    student_mcp_url: str = "http://127.0.0.1:8102/mcp"
    regulation_mcp_url: str = "http://127.0.0.1:8103/mcp"
    accounts_file: Path | None = None  # None: the demo accounts of student-server
    planner_mode: str = "llm"  # llm | rule | laya
    laya_url: str | None = None
    verifier_mode: str = "llm"  # llm | rules | off
    verifier_model: str | None = None
    history_messages: int = 10

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        student_url = env.get("STUDENT_MCP_URL", "").strip() or (
            f"http://{env.get('STUDENT_MCP_HOST', '127.0.0.1')}:{env.get('STUDENT_MCP_PORT', '8102')}/mcp"
        )
        regulation_url = env.get("REGULATION_MCP_URL", "").strip() or (
            f"http://{env.get('REGULATION_MCP_HOST', '127.0.0.1')}:{env.get('REGULATION_MCP_PORT', '8103')}/mcp"
        )
        database = env.get("CHAT_DATABASE_URL", "").strip()
        accounts = env.get("DEMO_ACCOUNTS_FILE", "").strip()
        return cls(
            token_secret=_secret(env, "BACKEND_TOKEN_SECRET"),
            student_token_secret=_secret(env, "STUDENT_MCP_TOKEN_SECRET"),
            token_ttl=int(env.get("BACKEND_TOKEN_TTL", cls.token_ttl)),
            student_token_ttl=int(env.get("STUDENT_MCP_TOKEN_TTL", cls.student_token_ttl)),
            host=env.get("BACKEND_HOST", cls.host),
            port=int(env.get("BACKEND_PORT", cls.port)),
            database_url=None
            if database.lower() in OFF_VALUES
            else (database or f"sqlite+aiosqlite:///{DEFAULT_DATABASE_FILE}"),
            student_mcp_url=student_url,
            regulation_mcp_url=regulation_url,
            accounts_file=Path(accounts) if accounts else None,
            planner_mode=env.get("ADVISOR_PLANNER_MODE", cls.planner_mode).strip().lower(),
            laya_url=env.get("LAYA_SERVER_URL", "").strip() or None,
            verifier_mode=env.get("ADVISOR_VERIFIER", cls.verifier_mode).strip().lower(),
            verifier_model=env.get("VERIFIER_LLM_MODEL", "").strip() or None,
            history_messages=int(env.get("ADVISOR_HISTORY_MESSAGES", cls.history_messages)),
        )
