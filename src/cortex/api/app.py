from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cortex.api.routes import router
from cortex.context import Cortex
from cortex.settings import Settings


def create_app(settings: Settings | None = None, cortex: Cortex | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.cortex is None:
            app.state.cortex = Cortex(app.state.settings)
        yield

    app = FastAPI(title="Cortex", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.state.cortex = cortex
    app.include_router(router)
    return app


app = create_app()