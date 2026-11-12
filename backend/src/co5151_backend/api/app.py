"""The FastAPI application. Routes only translate HTTP to use-case calls; the container holds the use cases."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..container import Container


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

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
