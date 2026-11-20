"""The FastAPI application: routes, and the mapping of domain errors to HTTP statuses."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..container import Container
from ..domain.errors import AnswerFailed, InvalidCredentials, InvalidRequest, NotFound, Unauthenticated
from .routes import router

STATUS = {InvalidCredentials: 401, Unauthenticated: 401, NotFound: 404, InvalidRequest: 422}
DETAIL = {InvalidCredentials: "invalid credentials", Unauthenticated: "not signed in", NotFound: "not found"}


def create_app(container: Container) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await container.start()
        try:
            yield
        finally:
            await container.close()

    app = FastAPI(title="CO5151 G3 backend", version="0.1.0", lifespan=lifespan)
    app.state.container = container
    app.include_router(router)

    for error, code in STATUS.items():

        async def handle(_request: Request, exc: Exception, code: int = code) -> JSONResponse:
            headers = {"WWW-Authenticate": "Bearer"} if code == 401 else None
            return JSONResponse({"detail": DETAIL.get(type(exc), str(exc))}, status_code=code, headers=headers)

        app.add_exception_handler(error, handle)

    @app.exception_handler(AnswerFailed)
    async def answer_failed(_request: Request, exc: AnswerFailed) -> JSONResponse:
        return JSONResponse({"detail": "answer failed", "trace_id": exc.trace_id}, status_code=500)

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
