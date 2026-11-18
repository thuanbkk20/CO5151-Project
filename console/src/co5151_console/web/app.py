"""The FastAPI application: one HTML page per route, rendered with Jinja2 from `templates/`."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..container import Container
from . import auth, evaluation, question_sets, sessions, traces

HERE = Path(__file__).parent
# The features: (path, name, what it does). Both the sidebar and the cards of the home page list them.
FEATURES: list[tuple[str, str, str]] = [
    ("/sessions", "Sessions", "Các hội thoại; mở một session để xem các lượt hỏi–đáp theo thứ tự và trace từng lượt."),
    (
        "/traces",
        "Traces",
        "Câu trả lời gần đây; mở một trace để xem từng node (Planner, MCP, Advisor, Verifier) đã nhận gì, trả về gì.",
    ),
    ("/eval", "Đánh giá", "Chạy một bộ câu hỏi qua backend, chấm điểm từng câu và tổng, link sang trace."),
    ("/question-sets", "Bộ câu hỏi", "Tạo, sửa bộ câu hỏi đánh giá; nhập bộ mặc định 24 câu."),
]
NAV: list[tuple[str, str]] = [("/", "Tổng quan")] + [(path, name) for path, name, _ in FEATURES]


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="CO5151 G3 console", docs_url=None, redoc_url=None)
    app.state.container = container
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals["nav"] = NAV
    app.state.templates = templates
    auth.install(app, auth.Sessions(container.settings.username, container.settings.password))
    app.include_router(traces.router)
    app.include_router(sessions.router)
    app.include_router(question_sets.router)
    app.include_router(evaluation.router)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse(request, "home.html", {"features": FEATURES})

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
