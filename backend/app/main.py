"""Home of Exile — FastAPI application factory."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.analyze import router as analyze_router
from app.api.v1.calculate import router as calculate_router
from app.api.v1.candidates import router as candidates_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.health import router as health_router
from app.api.v1.prices import router as prices_router
from app.api.v1.recommendations import router as recommendations_router
from app.core.config import settings
from app.core.limiter import limiter
from app.services.database import close_db_pool, init_db_pool
from app.services.luajit_pool import init_pool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan — start/stop the LuaJIT pool and DB pool
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application resource lifecycle.

    On startup:
    * Initialise the LuaJIT worker pool.
    * Initialise the PostgreSQL connection pool (graceful degradation if
      the database is unreachable).

    On shutdown:
    * Shut down the LuaJIT pool and close the DB pool cleanly.
    """
    # LuaJIT pool
    pool = init_pool(
        pool_size=settings.luajit_pool_size,
        pob_src_dir=settings.pob_src_dir,
        luajit_cmd=settings.luajit_cmd,
    )
    await pool.startup()
    logger.info(
        "LuaJIT pool initialised (available=%s)", pool.is_available
    )

    # PostgreSQL pool (optional — skip if DATABASE_URL is not set to a real DB)
    await init_db_pool(settings.database_url)

    yield  # server is running

    await pool.shutdown()
    await close_db_pool()


app = FastAPI(
    title="Home of Exile API",
    version="0.6.0",
    description="Backend API for the Home of Exile PoE build analyser.",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Rate limiter middleware
# ---------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# CORS — configurable via ALLOWED_ORIGINS env variable
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler — always return structured JSON
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all exception handler — returns structured JSON error.

    Args:
        request: The incoming request.
        exc: The unhandled exception.

    Returns:
        JSON response with ``detail`` and ``path`` fields.
    """
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error.",
            "path": request.url.path,
        },
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health_router)
app.include_router(prices_router, prefix="/api/v1")
app.include_router(calculate_router)
app.include_router(candidates_router)
app.include_router(recommendations_router)
app.include_router(analyze_router)
app.include_router(feedback_router)
