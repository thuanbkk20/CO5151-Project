from dataclasses import replace

import pytest

from co5151_console.adapters.sqlite_store import SqliteStore
from co5151_console.models import InvalidInput
from co5151_console.services.question_sets import DEFAULT_SET_NAME, QuestionSets, TaskForm

FACTS = '[{"field": "remaining_credits", "value": 15, "mention": ["15"]}]'
FORM = TaskForm(id="n01", group="personal", question="  Em còn bao nhiêu tín chỉ? ", expected="answer", user="sv001",
                citations="QD-Đ22\n\n", facts=FACTS)  # fmt: skip


@pytest.fixture
def sets(tmp_path) -> QuestionSets:
    return QuestionSets(SqliteStore(tmp_path / "console.db"))


def test_default_set_is_a_copy_of_the_eval_tasks(sets):
    set_id = sets.import_default()
    [summary] = sets.all()
    assert (summary.id, summary.name, summary.size) == (set_id, DEFAULT_SET_NAME, 24)
    assert sets.get(set_id).tasks[0].id == "B01"
    with pytest.raises(InvalidInput, match="Đã có bộ câu hỏi"):
        sets.import_default()


def test_add_edit_and_delete_a_task(sets):
    set_id = sets.create("Bộ thử")
    task = sets.save_task(set_id, FORM)
    assert (task.id, task.question, task.citations, task.facts[0].value) == ("N01", "Em còn bao nhiêu tín chỉ?",
                                                                              ["QD-Đ22"], 15)  # fmt: skip
    with pytest.raises(InvalidInput, match="đã có câu N01"):
        sets.save_task(set_id, FORM)
    renamed = replace(TaskForm.of(task), id="N02", notes="sửa")
    sets.save_task(set_id, renamed, replacing="N01")
    assert [(t.id, t.notes) for t in sets.get(set_id).tasks] == [("N02", "sửa")]
    sets.delete_task(set_id, "N02")
    assert sets.get(set_id).tasks == []
    sets.delete(set_id)
    assert sets.get(set_id) is None and sets.all() == []


def test_bad_forms_are_explained(sets):
    set_id = sets.create("Bộ thử")
    with pytest.raises(InvalidInput, match="id"):
        sets.save_task(set_id, TaskForm(id="sai id", group="basic", question="q", expected="answer"))
    with pytest.raises(InvalidInput, match="Facts không phải JSON"):
        sets.save_task(set_id, TaskForm(id="B99", group="basic", question="q", expected="answer", facts="{"))
    with pytest.raises(InvalidInput, match="facts need a logged-in user"):
        sets.save_task(set_id, TaskForm(id="B99", group="basic", question="q", expected="answer", facts=FORM.facts))
    with pytest.raises(InvalidInput, match="trống"):
        sets.create("  ")
    with pytest.raises(InvalidInput, match="Không có bộ"):
        sets.save_task(999, FORM)
