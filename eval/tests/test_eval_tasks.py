import json

import pytest
from pydantic import ValidationError

from co5151_eval.tasks import Group, Outcome, Task, load_tasks


def _task(**kw):
    base = {"id": "T01", "group": "basic", "question": "?", "expected": "answer"}
    return Task.model_validate({**base, **kw})


def test_minimal_task():
    t = _task()
    assert t.group is Group.BASIC and t.expected is Outcome.ANSWER and t.facts == []


def test_facts_require_a_user():
    with pytest.raises(ValidationError, match="logged-in user"):
        _task(facts=[{"field": "credits_earned", "value": 1, "mention": ["1"]}])


def test_verified_citations_cannot_be_empty():
    with pytest.raises(ValidationError, match="citations_verified"):
        _task(citations_verified=True)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        _task(answer="typo for reference_answer")


def test_duplicate_ids_are_rejected(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps([_task().model_dump(mode="json")] * 2))
    with pytest.raises(ValueError, match="duplicate"):
        load_tasks(p)
