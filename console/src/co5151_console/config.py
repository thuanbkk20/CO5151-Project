"""Settings of the console, read once at start-up from the environment (`.env` is loaded by the CLI)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE = Path(__file__).resolve().parents[2] / ".data" / "console.db"


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"  # no sign-in yet: keep it on this machine
    port: int = 8200
    backend_url: str = "http://127.0.0.1:8100"
    admin_token: str | None = None  # BACKEND_ADMIN_TOKEN, shared with the backend
    database: Path = DEFAULT_DATABASE  # question sets, evaluation runs, prompts
    eval_password: str = "demo"  # password of the demo accounts an evaluation run signs in with

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        database = env.get("CONSOLE_DATABASE", "").strip()
        return cls(
            host=env.get("CONSOLE_HOST", cls.host),
            port=int(env.get("CONSOLE_PORT", cls.port)),
            backend_url=(env.get("BACKEND_URL", "").strip() or cls.backend_url).rstrip("/"),
            admin_token=env.get("BACKEND_ADMIN_TOKEN", "").strip() or None,
            database=Path(database) if database else DEFAULT_DATABASE,
            eval_password=env.get("CONSOLE_EVAL_PASSWORD", cls.eval_password),
        )
