"""Helpers every page uses: the container and rendering a template."""

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from ..container import Container


def container(request: Request) -> Container:
    return request.app.state.container


def render(request: Request, template: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, context, status_code=status_code)
