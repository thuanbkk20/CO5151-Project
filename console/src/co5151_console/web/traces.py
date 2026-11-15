"""Traces page: newest answers, filter by session id (conversation id), one trace as its flow of nodes."""

from fastapi import APIRouter, Request

from ..ports import BackendError
from .render import container, render

router = APIRouter()


@router.get("/traces")
def traces(request: Request, session: str = "", limit: int = 50):
    rows, error = [], None
    try:
        rows = container(request).traces.recent(session.strip() or None, max(1, min(limit, 200)))
    except BackendError as e:
        error = str(e)
    return render(request, "traces.html", rows=rows, session=session.strip(), limit=limit, error=error)


@router.get("/traces/{trace_id}")
def trace(request: Request, trace_id: str, panel: bool = False):
    """The trace as its own page, or with `panel=1` only its content, for the side panel (static/panel.js)."""
    template = "trace_panel.html" if panel else "trace.html"
    try:
        detail = container(request).traces.detail(trace_id)
    except BackendError as e:
        return render(request, template, status_code=502, detail=None, trace_id=trace_id, error=str(e))
    status = 200 if detail else 404
    return render(request, template, status_code=status, detail=detail, trace_id=trace_id, error=None)
