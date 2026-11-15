"""`co5151-console`: run the operator console (default http://127.0.0.1:8200)."""

import argparse
import sys
from pathlib import Path

from co5151_contracts.env import find_env_file, load_env_file


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="co5151-console", description=__doc__)
    p.add_argument("--env-file", type=Path, help="mặc định: file .env gần nhất, tìm ngược lên tới gốc repo")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    a = p.parse_args(argv)
    load_env_file(a.env_file or find_env_file())

    import uvicorn

    from .config import Settings
    from .container import build_container
    from .web.app import create_app

    settings = Settings.from_env()
    uvicorn.run(create_app(build_container(settings)), host=a.host or settings.host, port=a.port or settings.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
