"""`co5151-api`: run the backend API (default http://127.0.0.1:8100, docs at /docs)."""

import argparse
import logging
import os
import sys
from pathlib import Path

from co5151_contracts.env import find_env_file, load_env_file


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="co5151-api", description=__doc__)
    p.add_argument("--env-file", type=Path, help="mặc định: file .env gần nhất, tìm ngược lên tới gốc repo")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    a = p.parse_args(argv)
    load_env_file(a.env_file or find_env_file())
    logging.basicConfig(level=os.environ.get("BACKEND_LOG_LEVEL", "INFO"), stream=sys.stderr)

    import uvicorn

    from .api.app import create_app
    from .container import build_container
    from .infrastructure.config import Settings

    settings = Settings.from_env()
    app = create_app(build_container(settings))
    uvicorn.run(app, host=a.host or settings.host, port=a.port or settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
