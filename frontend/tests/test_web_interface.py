"""The Chainlit interface: Vietnamese for every browser, every string of Chainlit translated."""

import json
from pathlib import Path

import chainlit
from chainlit.config import config

FRONTEND = Path(__file__).resolve().parents[1]


def _keys(tree: dict, prefix: str = "") -> set[str]:
    keys = set()
    for k, v in tree.items():
        keys |= _keys(v, f"{prefix}{k}.") if isinstance(v, dict) else {prefix + k}
    return keys


def test_the_interface_is_vietnamese_for_every_browser():
    assert config.root == str(FRONTEND)  # conftest: Chainlit reads frontend/.chainlit/config.toml
    assert config.ui.language == "vi-VN"  # the server uses it instead of the browser's language
    assert config.load_translation(config.ui.language)["navigation"]["newChat"]["button"] == "Hội thoại mới"


def test_every_chainlit_string_has_a_vietnamese_translation():
    english = json.loads((Path(chainlit.__file__).parent / "translations" / "en-US.json").read_text(encoding="utf-8"))
    vietnamese = json.loads((FRONTEND / ".chainlit" / "translations" / "vi-VN.json").read_text(encoding="utf-8"))
    assert _keys(vietnamese) == _keys(english)  # a Chainlit upgrade that adds strings makes this red


def test_light_theme_logo_and_favicon():
    assert config.ui.default_theme == "light" and config.ui.description
    public = FRONTEND / "public"
    theme = json.loads((public / "theme.json").read_text(encoding="utf-8"))
    assert {"light", "dark"} <= theme["variables"].keys()
    assert all(name.startswith("--") for v in theme["variables"].values() for name in v)  # CSS variables of the UI
    assert config.ui.login_page_image == "/public/login.svg"
    # the UI's name has Vietnamese letters, which /avatars/<name> refuses: the avatar must not depend on it
    assert config.ui.default_avatar_file_url == "/public/favicon.svg"
    for name in ("logo_light.svg", "logo_dark.svg", "favicon.svg", "login.svg"):  # favicon = assistant avatar too
        assert (public / name).read_text(encoding="utf-8").startswith("<svg")
