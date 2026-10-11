import pytest

from student_server.audit import AccessLog
from student_server.auth import TokenSigner, login
from student_server.db import StudentDB
from student_server.service import StudentRecordService

TEST_SECRET = b"test-secret"


@pytest.fixture(scope="session")
def db():
    return StudentDB()


@pytest.fixture(scope="session")
def signer():
    return TokenSigner(TEST_SECRET)


@pytest.fixture
def service(db, signer):
    return StudentRecordService(db, signer, AccessLog(b"audit-key"))


@pytest.fixture(scope="session")
def token(db, signer):
    """token("sv001") → a valid session token for that demo account."""
    cache = {}

    def make(username):
        if username not in cache:
            cache[username] = login(db, signer, username, "demo")
        return cache[username]

    return make
