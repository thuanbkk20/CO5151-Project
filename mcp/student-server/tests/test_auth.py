import pytest

from co5151_contracts import Role
from student_server.auth import AuthError, TokenSigner, authenticate, claims_for, login


@pytest.fixture
def signer():
    return TokenSigner(b"test-secret", ttl=600)


def test_login_student_and_advisor(db, signer):
    s = signer.verify(login(db, signer, "sv002", "demo"))
    assert s.role is Role.STUDENT and s.student_id == "2310002"
    a = authenticate(db, "cvht01", "demo")
    assert a["role"] == "advisor" and "2310001" in a["advisees"]


@pytest.mark.parametrize("user, pw", [("sv001", "wrong"), ("ghost", "demo"), ("sv001", "")])
def test_login_failures_share_one_message(db, user, pw):
    with pytest.raises(AuthError, match="^invalid credentials$"):
        authenticate(db, user, pw)


def test_claims_for_an_authenticated_user_match_the_login_claims(db):
    for username in ("sv002", "cvht01"):
        assert claims_for(db, username) == authenticate(db, username, "demo")
    assert claims_for(db, "nobody") is None


def test_accounts_file_has_no_plaintext_passwords(db):
    rows = db.conn.execute("SELECT password_hash FROM accounts").fetchall()
    assert rows and all(r[0].startswith("pbkdf2_sha256$") for r in rows)
