import pytest

from co5151_backend.domain.errors import Unauthenticated
from co5151_backend.domain.principal import Principal, Role
from co5151_backend.infrastructure.identity import DemoAccountDirectory, JwtAccessTokens, SignedStudentTokens
from co5151_contracts.security import TokenSigner


def test_demo_accounts_check_the_password():
    directory = DemoAccountDirectory()
    account = directory.authenticate("sv001", "demo")
    assert account.role is Role.STUDENT and account.claims["student_id"] == "2310001"
    assert directory.authenticate("sv001", "wrong") is None and directory.authenticate("ghost", "demo") is None
    assert directory.get("cvht01").role is Role.ADVISOR and directory.get("ghost") is None


def test_access_token_round_trip_and_rejections():
    tokens = JwtAccessTokens(b"secret", ttl=60)
    token, ttl = tokens.issue(Principal("sv001", Role.STUDENT, "sv001"))
    assert ttl == 60 and tokens.verify(token) == Principal("sv001", Role.STUDENT, "sv001")
    with pytest.raises(Unauthenticated):
        JwtAccessTokens(b"other", ttl=60).verify(token)
    with pytest.raises(Unauthenticated):
        JwtAccessTokens(b"secret", ttl=-1).verify(
            JwtAccessTokens(b"secret", ttl=-1).issue(Principal("x", Role.GUEST))[0]
        )
    with pytest.raises(Unauthenticated):
        tokens.verify("not-a-token")


def test_student_token_is_what_student_mcp_verifies():
    account = DemoAccountDirectory().get("sv002")
    token = SignedStudentTokens(b"shared", ttl=300).issue(account)
    claims = TokenSigner(b"shared").verify(token)
    assert claims.student_id == "2310002" and claims.exp - claims.iat == 300
