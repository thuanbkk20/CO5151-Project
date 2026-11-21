"""Question set pages: list and create sets, show one set, add / edit / delete a task. Plain HTML forms;
every POST redirects (303) to a page, so reloading never submits twice."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..models import InvalidInput
from ..services.question_sets import GROUPS, OUTCOMES, TaskForm
from .render import container, render

router = APIRouter(prefix="/question-sets")


def _to(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _not_found(request: Request):
    return render(request, "message.html", status_code=404, title="Không có bộ câu hỏi này",
                  back="/question-sets")  # fmt: skip


@router.get("")
def list_sets(request: Request, error: str = ""):
    return render(request, "question_sets.html", sets=container(request).question_sets.all(), error=error)


@router.post("")
def create_set(request: Request, name: str = Form("")):
    sets = container(request).question_sets
    try:
        return _to(f"/question-sets/{sets.create(name)}")
    except InvalidInput as e:
        return render(request, "question_sets.html", status_code=422, sets=sets.all(), error=str(e))


@router.post("/import-default")
def import_default(request: Request):
    sets = container(request).question_sets
    try:
        return _to(f"/question-sets/{sets.import_default()}")
    except InvalidInput as e:
        return render(request, "question_sets.html", status_code=422, sets=sets.all(), error=str(e))


@router.get("/{set_id}")
def show_set(request: Request, set_id: int):
    question_set = container(request).question_sets.get(set_id)
    if question_set is None:
        return _not_found(request)
    return render(request, "question_set.html", qs=question_set)


@router.post("/{set_id}/delete")
def delete_set(request: Request, set_id: int):
    container(request).question_sets.delete(set_id)
    return _to("/question-sets")


def _task_page(request: Request, set_id: int, form: TaskForm | None, editing: str | None, error: str = ""):
    question_set = container(request).question_sets.get(set_id)
    if question_set is None:
        return _not_found(request)
    return render(request, "task_form.html", status_code=422 if error else 200, qs=question_set, form=form,
                  editing=editing, error=error, groups=GROUPS, outcomes=OUTCOMES)  # fmt: skip


@router.get("/{set_id}/tasks/new")
def new_task(request: Request, set_id: int):
    return _task_page(request, set_id, None, None)


@router.get("/{set_id}/tasks/{task_id}")
def edit_task(request: Request, set_id: int, task_id: str):
    question_set = container(request).question_sets.get(set_id)
    task = question_set.task(task_id) if question_set else None
    if task is None:
        return _not_found(request)
    return _task_page(request, set_id, TaskForm.of(task), task_id)


@router.post("/{set_id}/tasks")
def save_task(
    request: Request,
    set_id: int,
    editing: str = Form(""),
    id: str = Form(""),
    group: str = Form("basic"),
    question: str = Form(""),
    expected: str = Form("answer"),
    user: str = Form(""),
    also_accept: Annotated[list[str] | None, Form()] = None,
    citations: str = Form(""),
    forbidden: str = Form(""),
    facts: str = Form(""),
    reference_answer: str = Form(""),
    notes: str = Form(""),
):
    form = TaskForm(id=id, group=group, question=question, expected=expected, user=user,
                    also_accept=tuple(also_accept or ()), citations=citations, forbidden=forbidden, facts=facts,
                    reference_answer=reference_answer, notes=notes)  # fmt: skip
    try:
        container(request).question_sets.save_task(set_id, form, replacing=editing or None)
    except InvalidInput as e:
        return _task_page(request, set_id, form, editing or None, str(e))
    return _to(f"/question-sets/{set_id}")


@router.post("/{set_id}/tasks/{task_id}/delete")
def delete_task(request: Request, set_id: int, task_id: str):
    container(request).question_sets.delete_task(set_id, task_id)
    return _to(f"/question-sets/{set_id}")
