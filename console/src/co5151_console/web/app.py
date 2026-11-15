"""The FastAPI application: one HTML page per route, rendered with Jinja2 from `templates/`."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..container import Container

HERE = Path(__file__).parent
# The sidebar: (path, label). A page is added here when it is built.
NAV: list[tuple[str, str]] = [("/", "Tổng quan")]


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="CO5151 G3 console", docs_url=None, redoc_url=None)
    app.state.container = container
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals["nav"] = NAV
    app.state.templates = templates

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse(request, "home.html", {"settings": container.settings})

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
