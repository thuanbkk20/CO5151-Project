import os
from collections.abc import Iterable
from functools import cached_property

from student_server.auth import login
from student_server.config import Settings
from student_server.server import build_service

from .conversations import Conversation
from .tasks import Fact, Task

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
        if field == "remaining_credits":  # derived: what is left of the programme
            summary = self._data("get_my_academic_summary", user)
            return [summary.program_credits - summary.credits_earned]
        if field.startswith("decisions."):
            attr = field.removeprefix("decisions.")
            return [getattr(d, attr) for d in self._data("get_my_academic_decisions", user).decisions]
        return [getattr(self._data("get_my_academic_summary", user), field)]


def _check(items: Iterable[tuple[str, str | None, list[Fact]]], oracle: RecordOracle) -> list[str]:
    problems = []
    for item_id, user, facts in items:
        for f in facts:
            try:
                values = oracle.actual(user, f.field)
            except (AttributeError, LookupError) as e:
                problems.append(f"{item_id}: {f.field}: {e}")
                continue
            if f.value not in values:
                problems.append(f"{item_id}: {f.field} = {f.value!r} but record has {values!r}")
    return problems


def check_gold(tasks: list[Task], oracle: RecordOracle | None = None) -> list[str]:
    return _check(((t.id, t.user, t.facts) for t in tasks), oracle or RecordOracle())


def check_gold_conversations(conversations: list[Conversation], oracle: RecordOracle | None = None) -> list[str]:
    """The facts of every turn against the record of the conversation's user."""
    items = ((t.id, c.user, t.facts) for c in conversations for t in c.turns)
    return _check(items, oracle or RecordOracle())
