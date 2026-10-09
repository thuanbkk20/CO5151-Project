"""Runtime settings, read from environment variables (or a .env loaded by the host)."""

import os
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEV_SECRET = "dev-secret-change-me"
PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    token_secret: bytes
    token_ttl: int = 3600
    host: str = "127.0.0.1"
    port: int = 8102
    db_path: str = ":memory:"
    data_dir: Path = PACKAGE_DIR / "mockdata"
    auth_issuer_url: str = "http://127.0.0.1:8000"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        secret = env.get("STUDENT_MCP_TOKEN_SECRET", DEV_SECRET)
        if secret == DEV_SECRET:
            warnings.warn("STUDENT_MCP_TOKEN_SECRET is not set; using the insecure dev secret", stacklevel=2)
        return cls(
            token_secret=secret.encode(),
            token_ttl=int(env.get("STUDENT_MCP_TOKEN_TTL", cls.token_ttl)),
            host=env.get("STUDENT_MCP_HOST", cls.host),
            port=int(env.get("STUDENT_MCP_PORT", cls.port)),
            db_path=env.get("STUDENT_MCP_DB_PATH", cls.db_path),
            data_dir=Path(env.get("STUDENT_MCP_DATA_DIR", cls.data_dir)),
            auth_issuer_url=env.get("STUDENT_MCP_AUTH_ISSUER_URL", cls.auth_issuer_url),
        )
