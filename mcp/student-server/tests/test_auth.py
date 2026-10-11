import pytest

from co5151_contracts import Role
from student_server.auth import AuthError, TokenSigner, authenticate, login
from student_server.auth.passwords import hash_password, verify_password
from student_server.auth.tokens import _b64

NOW = 1_800_000_000
STUDENT = {"sub": "sv001", "role": "student", "student_id": "2310001"}


@pytest.fixture
def signer():
    return TokenSigner(b"test-secret", ttl=600)


def test_issue_and_verify_round_trip(signer):
    claims = signer.verify(signer.issue(STUDENT, now=NOW), now=NOW + 1)
    assert claims.student_id == "2310001" and claims.exp == NOW + 600


def test_expired_token_rejected(signer):
    token = signer.issue(STUDENT, now=NOW)
    with pytest.raises(AuthError, match="expired"):
        signer.verify(token, now=NOW + 600)


def test_token_from_other_secret_rejected(signer):
    with pytest.raises(AuthError, match="signature"):
        signer.verify(TokenSigner(b"other").issue(STUDENT))


def test_tampered_payload_rejected(signer):
    """Swapping student_id in the payload must break the signature."""
    payload, sig = signer.issue(STUDENT).split(".")
    forged = _b64(f'{{"sub":"sv001","role":"student","student_id":"2310002","iat":{NOW},"exp":{NOW + 10**9}}}'.encode())
    with pytest.raises(AuthError, match="signature"):
        signer.verify(f"{forged}.{sig}")


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", None, 123])
def test_malformed_tokens_rejected(signer, token):
    with pytest.raises(AuthError):
        signer.verify(token)


def test_signed_garbage_claims_rejected(signer):
    payload = _b64(b'{"sub":"x","role":"root"}')
    with pytest.raises(AuthError, match="malformed claims"):
        signer.verify(f"{payload}.{signer._sign(payload)}")


def test_password_hashing():
    h = hash_password("demo", salt="abcd")
    assert verify_password("demo", h) and not verify_password("Demo", h)
    assert not verify_password("demo", "plaintext") and not verify_password("demo", None)


def test_login_student_and_advisor(db, signer):
    s = signer.verify(login(db, signer, "sv002", "demo"))
    assert s.role is Role.STUDENT and s.student_id == "2310002"
    a = authenticate(db, "cvht01", "demo")
    assert a["role"] == "advisor" and "2310001" in a["advisees"]


@pytest.mark.parametrize("user, pw", [("sv001", "wrong"), ("ghost", "demo"), ("sv001", "")])
def test_login_failures_share_one_message(db, user, pw):
    with pytest.raises(AuthError, match="^invalid credentials$"):
        authenticate(db, user, pw)


def test_accounts_file_has_no_plaintext_passwords(db):
    rows = db.conn.execute("SELECT password_hash FROM accounts").fetchall()
    assert rows and all(r[0].startswith("pbkdf2_sha256$") for r in rows)
