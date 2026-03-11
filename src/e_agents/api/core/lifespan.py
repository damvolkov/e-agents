"""FastAPI lifespan factory — attaches shared State and handles adapter cleanup."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from e_agents.shared.core.logger import LogIcon, logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from e_agents.shared.state import State


def create_lifespan(state: State):
    """Build a FastAPI lifespan that registers *state* on ``app.state``."""

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.app_state = state
        logger.info("lifespan_up", adapters=len(state.adapters), icon=LogIcon.START)
        try:
            yield
        finally:
            await state.close()
            logger.info("lifespan_down", icon=LogIcon.COMPLETE, color_range=1)

    return _lifespan
