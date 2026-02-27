"""Home of Exile — FastAPI application factory."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.calculate import router as calculate_router
from app.api.v1.health import router as health_router
from app.api.v1.prices import router as prices_router
from app.core.config import settings
from app.services.luajit_pool import init_pool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan — start/stop the LuaJIT pool
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage the LuaJIT worker pool lifecycle.

    Creates and starts the pool before the first request; shuts it down
    cleanly when the server exits.
    """
    pool = init_pool(
        pool_size=settings.luajit_pool_size,
        pob_src_dir=settings.pob_src_dir,
        luajit_cmd=settings.luajit_cmd,
    )
    await pool.startup()
    logger.info(
        "LuaJIT pool initialised (available=%s)", pool.is_available
    )

    yield  # server is running

    await pool.shutdown()


app = FastAPI(
    title="Home of Exile API",
    version="0.2.0",
    description="Backend API for the Home of Exile PoE build analyser.",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the Vite dev server during development
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health_router)
app.include_router(prices_router, prefix="/api/v1")
app.include_router(calculate_router)
