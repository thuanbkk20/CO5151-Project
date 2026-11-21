"""Sessions page: the conversations (sessions), and one conversation as its turns in order; a turn's trace
opens in the side panel."""

from fastapi import APIRouter, Request

from ..ports import BackendError
from .render import container, render

router = APIRouter(prefix="/sessions")


@router.get("")
def sessions(request: Request, limit: int = 50):
    rows, error = [], None
    try:
        rows = container(request).sessions.all(max(1, min(limit, 200)))
    except BackendError as e:
        error = str(e)
    return render(request, "sessions.html", rows=rows, limit=limit, error=error)


@router.get("/{session_id}")
def session(request: Request, session_id: str, panel: bool = False):
    """The session as its own page, or with `panel=1` only its content, for the side panel (static/panel.js)."""
    template = "session_panel.html" if panel else "session.html"
    try:
        detail = container(request).sessions.detail(session_id)
    except BackendError as e:
        return render(request, template, status_code=502, detail=None, session_id=session_id, error=str(e))
    return render(request, template, detail=detail, session_id=session_id, error=None)
