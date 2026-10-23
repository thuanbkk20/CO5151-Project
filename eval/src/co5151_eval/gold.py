"""Gold facts are copied into tasks.json by hand; this module checks them against the mock records.

It reads records through the Student Record service in-process — the integration path documented in
mcp/student-server/README.md — so a regenerated mock dataset that changes a persona fails the check
instead of silently invalidating the benchmark.
"""

from functools import cached_property

from student_server.auth import login
from student_server.config import Settings
from student_server.server import build_service

from .tasks import Task

DEMO_PASSWORD = "demo"


class RecordOracle:
    """Reads the ground-truth summary and warning history of each demo account."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings(token_secret=b"eval-oracle")

    @cached_property
    def service(self):
        return build_service(self._settings)

    def token(self, user: str) -> str:
        return login(self.service.db, self.service.signer, user, DEMO_PASSWORD)

    def _data(self, tool: str, user: str):
        res = self.service.call(tool, self.token(user))
        if not res.ok:
            raise LookupError(f"{tool} failed for {user}: {res.error.code.value}")
        return res.data

    def actual(self, user: str, field: str) -> list:
        """All values of `field` for `user`; `warnings.<attr>` ranges over the warning history."""
        if field.startswith("warnings."):
            attr = field.removeprefix("warnings.")
            return [getattr(w, attr) for w in self._data("get_my_warnings", user).history]
        return [getattr(self._data("get_my_academic_summary", user), field)]


def check_gold(tasks: list[Task], oracle: RecordOracle | None = None) -> list[str]:
    """Return one message per fact that no longer matches the mock records (empty = all good)."""
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
