import pytest

from student_server.config import Settings


def test_defaults_warn_about_dev_secret():
    with pytest.warns(UserWarning, match="insecure dev secret"):
        s = Settings.from_env({})
    assert s.port == 8102 and s.db_path == ":memory:"


def test_env_overrides():
    s = Settings.from_env(
        {"STUDENT_MCP_TOKEN_SECRET": "s3cret", "STUDENT_MCP_PORT": "9000", "STUDENT_MCP_TOKEN_TTL": "60"}
    )
    assert s.token_secret == b"s3cret" and s.port == 9000 and s.token_ttl == 60
