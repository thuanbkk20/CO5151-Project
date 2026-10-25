import os
from pathlib import Path


def find_env_file(start: Path | None = None) -> Path | None:
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        if (directory / ".env").is_file():
            return directory / ".env"
        if (directory / "uv.lock").is_file():
            return None
    return None


def load_env_file(path: Path | None) -> None:
    if path is None or not path.is_file():
        return
    for line in path.read_text("utf-8").splitlines():
        line = line.strip().removeprefix("export ").strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
