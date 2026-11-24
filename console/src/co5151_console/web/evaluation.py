"""Evaluation pages: pick a set, confirm (every answer costs LLM calls), follow the run, read its results."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..models import InvalidInput
from ..services.evaluation import MAX_LLM_CALLS_PER_TASK
from .render import container, render

router = APIRouter(prefix="/eval")

# Metrics of co5151_eval.runner.summarize shown on a run's page: (key, label, is a rate)
METRICS = [
    ("n", "Số câu", False),
    ("pass_rate", "Pass", True),
    ("needs_human", "Cần chấm tay", False),
    ("outcome_accuracy", "Đúng kết cục", True),
    ("fact_recall", "Fact recall", True),
    ("citation_recall", "Citation recall", True),
    ("false_refusal_rate", "Từ chối nhầm", True),
    ("leaks", "Lộ (mẫu cấm)", False),
    ("errors", "Lỗi", False),
    ("latency_p50_s", "p50 (s)", False),
    ("tokens_mean", "Token/câu", False),
    ("verifier_rewrites", "Verifier viết lại", False),
]


@router.get("")
def runs(request: Request, error: str = ""):
    c = container(request)
    return render(request, "eval_runs.html", runs=c.evaluation.runs(), sets=c.question_sets.all(), error=error)


@router.get("/confirm")
def confirm(request: Request, set_id: int):
    question_set = container(request).question_sets.get(set_id)
    if question_set is None:
        return render(request, "message.html", status_code=404, title="Không có bộ câu hỏi này", back="/eval")
    return render(request, "eval_confirm.html", qs=question_set, max_calls=MAX_LLM_CALLS_PER_TASK)


@router.post("/runs")
def start(request: Request, set_id: int = Form(...)):
    c = container(request)
    try:
        run_id = c.evaluation.start(set_id)
    except InvalidInput as e:
        return render(request, "eval_runs.html", status_code=422, runs=c.evaluation.runs(),
                      sets=c.question_sets.all(), error=str(e))  # fmt: skip
    return RedirectResponse(f"/eval/runs/{run_id}", status_code=303)


@router.get("/runs/{run_id}")
def run(request: Request, run_id: int):
    report = container(request).evaluation.report(run_id)
    if report is None:
        return render(request, "message.html", status_code=404, title="Không có lần chạy này", back="/eval")
    return render(request, "eval_run.html", report=report, metrics=METRICS)
