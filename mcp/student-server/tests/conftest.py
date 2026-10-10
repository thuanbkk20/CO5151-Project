import pytest

from student_server.db import StudentDB


@pytest.fixture(scope="session")
def db():
    return StudentDB()
