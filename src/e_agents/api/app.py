"""FastAPI application factory — standalone-capable."""

from __future__ import annotations

from fastapi import FastAPI

from e_agents.api.core.exception_handler import register_exception_handlers
from e_agents.api.core.lifespan import create_lifespan
from e_agents.api.router.endpoints.livekit import router
from e_agents.shared.core.settings import settings as st
from e_agents.shared.state import State


def create_app(state: State) -> FastAPI:
    """Create the FastAPI application with shared state attached via lifespan."""
    app = FastAPI(
        title=st.API_NAME,
        description=st.API_DESCRIPTION,
        version=st.API_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=create_lifespan(state),
    )
    register_exception_handlers(app)
    app.include_router(router)
    return app


if __name__ == "__main__":
    import uvicorn

    from e_agents.shared.adapters.searxng import SearXNGAdapter

    _state = State()
    _state.register_adapter(SearXNGAdapter(base_url=str(st.SEARXNG_URL)))
    _app = create_app(_state)
    uvicorn.run(_app, host="0.0.0.0", port=st.API_PORT)
