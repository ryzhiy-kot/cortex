from fastapi import FastAPI

from cortex.api.routes import router
from cortex.context import Cortex
from cortex.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Cortex", version="0.1.0")
    app.state.settings = settings or Settings()

    @app.on_event("startup")
    def build_cortex() -> None:
        app.state.cortex = Cortex(app.state.settings)

    app.include_router(router)
    return app


app = create_app()