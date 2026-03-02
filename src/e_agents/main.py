"""e-agents entry point."""

import asyncio
import contextlib

import uvicorn
from fastapi import FastAPI

from e_agents.api.router import router
from e_agents.cli.main import cli
from e_agents.core.settings import settings as st


def create_api_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title=st.API_NAME,
        description=st.API_DESCRIPTION,
        version=st.API_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.include_router(router)
    return app


async def run_api() -> None:
    """Run the API server as an async task."""
    config = uvicorn.Config(
        app=create_api_app(),
        host="0.0.0.0",
        port=st.API_PORT,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    api_task = asyncio.create_task(run_api())
    try:
        result = cli()
        if asyncio.iscoroutine(result):
            await result
    finally:
        api_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await api_task


if __name__ == "__main__":
    asyncio.run(main())
