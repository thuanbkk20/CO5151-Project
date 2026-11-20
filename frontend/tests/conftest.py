import os
from pathlib import Path

import pytest

# Importing chainlit has two side effects, both blocked before any test module imports it:
# - it loads `<current directory>/.env`, i.e. the developer's real keys when pytest runs from the repo root, for the
#   whole test session (other packages' tests could then call the LLM with that key);
# - it reads, and writes if missing, `.chainlit/` in its app root; frontend already has one.
os.environ["CHAINLIT_ENV_FILE"] = os.devnull
os.environ.setdefault("CHAINLIT_APP_ROOT", str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def anyio_backend():
    return "asyncio"
