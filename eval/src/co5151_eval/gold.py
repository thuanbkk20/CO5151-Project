import os
from functools import cached_property

from student_server.auth import login
from student_server.config import Settings
from student_server.server import build_service

from .tasks import Task

DEMO_PASSWORD = "demo"
EVAL_SECRET = b"eval-local-secret"


def default_settings() -> Settings:
    if os.environ.get("STUDENT_MCP_TOKEN_SECRET"):
        return Settings.from_env()
    return Settings(token_secret=EVAL_SECRET)


class RecordOracle:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or default_settings()

    @cached_property
    def service(self):
        return build_service(self.settings)

    def token(self, user: str) -> str:
        return login(self.service.db, self.service.signer, user, DEMO_PASSWORD)

    def _data(self, tool: str, user: str):
        res = self.service.call(tool, self.token(user))
        if not res.ok:
            raise LookupError(f"{tool} failed for {user}: {res.error.code.value}")
        return res.data

    def actual(self, user: str, field: str) -> list:
        if field.startswith("warnings."):
            attr = field.removeprefix("warnings.")
            return [getattr(w, attr) for w in self._data("get_my_warnings", user).history]
        return [getattr(self._data("get_my_academic_summary", user), field)]


def check_gold(tasks: list[Task], oracle: RecordOracle | None = None) -> list[str]:
    oracle = oracle or RecordOracle()
    problems = []
    for t in tasks:
        for f in t.facts:
            try:
                values = oracle.actual(t.user, f.field)
            except (AttributeError, LookupError) as e:
                problems.append(f"{t.id}: {f.field}: {e}")
                continue
            if f.value not in values:
                problems.append(f"{t.id}: {f.field} = {f.value!r} but record has {values!r}")
    return problems
