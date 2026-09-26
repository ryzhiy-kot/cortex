from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from cortex.api.routes import router
from cortex.context import Cortex
from cortex.settings import Settings
from cortex.telemetry import logger, tracer


def create_app(settings: Settings | None = None, cortex: Cortex | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.cortex is None:
            app.state.cortex = Cortex(app.state.settings)
        yield

    app = FastAPI(title="Cortex", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.state.cortex = cortex

    @app.middleware("http")
    async def record_unhandled(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(
                "unhandled error %s %s", request.method, request.url.path, exc_info=True
            )
            span = tracer().start_span(
                f"{request.method} {request.url.path}",
            )
            span.set_attribute("cortex.method", request.method)
            span.set_attribute("cortex.path", request.url.path)
            span.record_exception(exc)
            span.end()
            raise

    app.include_router(router)
    return app


app = create_app()