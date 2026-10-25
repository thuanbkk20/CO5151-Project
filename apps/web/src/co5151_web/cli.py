import argparse
import os
import sys
from pathlib import Path

from co5151_contracts.env import find_env_file, load_env_file

APP = Path(__file__).with_name("app.py")
WEB_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="co5151-web", description="Giao diện chat Chainlit cho Advisor")
    p.add_argument("--env-file", type=Path, help="mặc định: file .env gần nhất, tìm ngược lên tới gốc repo")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    a = p.parse_args(argv)
    load_env_file(a.env_file or find_env_file())
    if not os.environ.get("CHAINLIT_AUTH_SECRET"):
        print("CHAINLIT_AUTH_SECRET trống: điền vào .env (xem .env.example)", file=sys.stderr)
        return 2
    os.environ.setdefault("CHAINLIT_APP_ROOT", str(WEB_ROOT))
    if a.host:
        os.environ["CHAINLIT_HOST"] = a.host
    if a.port:
        os.environ["CHAINLIT_PORT"] = str(a.port)
    from chainlit.cli import run_chainlit

    run_chainlit(str(APP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
