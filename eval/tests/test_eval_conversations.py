import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from co5151_eval.conversations import Conversation, load_conversations
from co5151_eval.gold import check_gold_conversations
from co5151_eval.tasks import Outcome

DOC = Path(__file__).parents[2] / "docs/design/test-conversations.md"


@pytest.fixture(scope="module")
def conversations():
    return load_conversations()


def test_twenty_conversations_of_sixty_two_turns_all_signed_in(conversations):
    assert len(conversations) == 20 and sum(len(c.turns) for c in conversations) == 62
    assert all(c.user for c in conversations) and {"limit", "clarify", "refuse", "answer"} == {
        t.expected.value for c in conversations for t in c.turns}  # fmt: skip


def test_every_turn_is_a_question_of_the_reviewed_document(conversations):
    doc = DOC.read_text("utf-8")
    missing = [t.id for c in conversations for t in c.turns if t.question not in doc]
    assert missing == []


def test_the_facts_match_the_mock_student_record(conversations):
    assert check_gold_conversations(conversations) == []


def test_h18_prefills_ten_questions_then_starts_a_new_conversation(conversations):
    h18 = next(c for c in conversations if c.id == "H18")
    assert len(h18.prefill_turns) == 10 and [t.id for t in h18.turns] == ["H18-11", "H18-12"]
    assert h18.turns[0].expected is Outcome.LIMIT and h18.turns[1].new_conversation


def _conv(**kw):
    base = {"id": "H99", "user": "sv001", "title": "t", "use_cases": ["UC1"],
            "turns": [{"id": "H99-1", "question": "?", "expected": "answer"}]}  # fmt: skip
    return Conversation.model_validate({**base, **kw})


def test_invalid_conversations_are_rejected(tmp_path):
    with pytest.raises(ValidationError, match="another conversation"):
        _conv(turns=[{"id": "H01-1", "question": "?", "expected": "answer"}])
    with pytest.raises(ValidationError, match="unknown use cases"):
        _conv(use_cases=["UC10"])
    with pytest.raises(ValidationError):
        _conv(user="")
    p = tmp_path / "c.json"
    p.write_text(json.dumps([_conv().model_dump(mode="json")] * 2))
    with pytest.raises(ValueError, match="duplicate"):
        load_conversations(p)
