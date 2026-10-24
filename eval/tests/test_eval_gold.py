from collections import Counter

import pytest

from co5151_eval.gold import RecordOracle, check_gold
from co5151_eval.tasks import Fact, Group, Outcome, Task, load_tasks


@pytest.fixture(scope="module")
def tasks():
    return load_tasks()


@pytest.fixture(scope="module")
def oracle():
    return RecordOracle()


def test_bundled_set_matches_the_proposal(tasks):
    assert Counter(t.group for t in tasks) == {
        Group.BASIC: 6,
        Group.PERSONAL: 8,
        Group.MISSING_INFO: 4,
        Group.OUT_OF_SCOPE: 6,
    }


def test_expected_outcome_follows_the_group(tasks):
    expected = {
        Group.BASIC: Outcome.ANSWER,
        Group.PERSONAL: Outcome.ANSWER,
        Group.MISSING_INFO: Outcome.CLARIFY,
        Group.OUT_OF_SCOPE: Outcome.REFUSE,
    }
    assert all(t.expected is expected[t.group] for t in tasks)


def test_personal_tasks_have_gold_facts(tasks):
    assert all(t.user and t.facts for t in tasks if t.group is Group.PERSONAL)


def test_gold_facts_match_mock_records(tasks, oracle):
    assert check_gold(tasks, oracle) == []


def test_check_gold_reports_drift(oracle):
    t = Task(id="X01", group="personal", question="?", user="sv001", expected="answer",
             facts=[Fact(field="credits_earned", value=999, mention=["999"])])  # fmt: skip
    [msg] = check_gold([t], oracle)
    assert "X01" in msg and "113" in msg
