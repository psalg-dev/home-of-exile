"""Database service — PostgreSQL connection management via asyncpg.

Provides an optional async connection pool. All operations degrade
gracefully when the database is unavailable (analysis still works,
but feedback persistence is skipped).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from asyncpg import Pool

logger = logging.getLogger(__name__)

# Module-level pool (lazily created via init_db_pool)
_pool: Pool | None = None


async def init_db_pool(dsn: str) -> None:
    """Initialise the asyncpg connection pool.

    Args:
        dsn: PostgreSQL connection string (e.g.
            ``postgresql://user:pass@host:port/db``).
    """
    global _pool
    try:
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        logger.info("PostgreSQL pool initialised (dsn=%s)", dsn)
        await run_migrations()
    except Exception:
        logger.warning(
            "PostgreSQL unavailable — feedback persistence disabled",
            exc_info=True,
        )
        _pool = None


async def close_db_pool() -> None:
    """Close the connection pool on application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")


def get_pool() -> Pool | None:
    """Return the current connection pool, or ``None`` if unavailable.

    Returns:
        Active :class:`asyncpg.Pool` or ``None``.
    """
    return _pool


async def is_db_healthy() -> bool:
    """Check whether the database is reachable.

    Returns:
        ``True`` if a quick query succeeds, ``False`` otherwise.
    """
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Schema migrations (idempotent DDL)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Build context
    archetype_damage TEXT NOT NULL DEFAULT '',
    archetype_defense TEXT NOT NULL DEFAULT '',
    archetype_playstyle TEXT NOT NULL DEFAULT '',
    character_level INT NOT NULL DEFAULT 0,
    league TEXT NOT NULL DEFAULT '',
    -- Recommendation context
    recommendation_rank INT NOT NULL,
    recommendation_category TEXT NOT NULL DEFAULT '',
    slot TEXT NOT NULL DEFAULT '',
    suggested_item TEXT NOT NULL DEFAULT '',
    dps_delta FLOAT,
    ehp_delta FLOAT,
    price_divine FLOAT,
    -- Feedback
    vote TEXT NOT NULL CHECK (vote IN ('up', 'down')),
    -- Tracking
    session_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_clicks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id TEXT NOT NULL,
    recommendation_rank INT NOT NULL,
    suggested_item TEXT NOT NULL DEFAULT '',
    league TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_feedback_league
    ON feedback(league);
CREATE INDEX IF NOT EXISTS idx_feedback_archetype
    ON feedback(archetype_damage, archetype_defense);
CREATE INDEX IF NOT EXISTS idx_feedback_session
    ON feedback(session_id, recommendation_rank);
CREATE INDEX IF NOT EXISTS idx_trade_clicks_league
    ON trade_clicks(league);
"""


async def run_migrations() -> None:
    """Create tables and indexes if they do not already exist.

    This is a lightweight idempotent migration for the MVP.  A proper
    migration tool (e.g. alembic) should be adopted before scaling.
    """
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(_SCHEMA_SQL)
        logger.info("Database schema migrations applied")
    except Exception:
        logger.warning("Failed to run DB migrations", exc_info=True)


async def insert_feedback(record: dict) -> bool:  # type: ignore[type-arg]
    """Insert a feedback row into the ``feedback`` table.

    Args:
        record: Dict with keys matching the ``feedback`` table columns.

    Returns:
        ``True`` on success, ``False`` if the database is unavailable.
    """
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feedback (
                    archetype_damage, archetype_defense, archetype_playstyle,
                    character_level, league,
                    recommendation_rank, recommendation_category,
                    slot, suggested_item, dps_delta, ehp_delta, price_divine,
                    vote, session_id
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
                )
                """,
                record.get("archetype_damage", ""),
                record.get("archetype_defense", ""),
                record.get("archetype_playstyle", ""),
                record.get("character_level", 0),
                record.get("league", ""),
                record["recommendation_rank"],
                record.get("recommendation_category", ""),
                record.get("slot", ""),
                record.get("suggested_item", ""),
                record.get("dps_delta"),
                record.get("ehp_delta"),
                record.get("price_divine"),
                record["vote"],
                record["session_id"],
            )
        return True
    except Exception:
        logger.warning("Failed to insert feedback", exc_info=True)
        return False


async def insert_trade_click(record: dict) -> bool:  # type: ignore[type-arg]
    """Insert a trade-click tracking row.

    Args:
        record: Dict with keys matching ``trade_clicks`` columns.

    Returns:
        ``True`` on success, ``False`` if the database is unavailable.
    """
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO trade_clicks (
                    session_id, recommendation_rank, suggested_item, league
                ) VALUES ($1, $2, $3, $4)
                """,
                record["session_id"],
                record["recommendation_rank"],
                record.get("suggested_item", ""),
                record.get("league", ""),
            )
        return True
    except Exception:
        logger.warning("Failed to insert trade click", exc_info=True)
        return False


async def get_feedback_stats(
    league: str | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    """Return aggregate feedback stats grouped by archetype, slot, category.

    Args:
        league: If provided, filter to this league.

    Returns:
        List of dicts with keys: archetype_damage, archetype_defense,
        slot, recommendation_category, total, up_votes, down_votes,
        up_ratio.
    """
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    archetype_damage,
                    archetype_defense,
                    slot,
                    recommendation_category,
                    league,
                    COUNT(*) AS total,
                    SUM(CASE WHEN vote = 'up' THEN 1 ELSE 0 END) AS up_votes,
                    SUM(CASE WHEN vote = 'down' THEN 1 ELSE 0 END) AS down_votes,
                    ROUND(
                        SUM(CASE WHEN vote = 'up' THEN 1.0 ELSE 0.0 END) /
                        NULLIF(COUNT(*), 0), 3
                    ) AS up_ratio
                FROM feedback
                WHERE ($1::text IS NULL OR league = $1)
                GROUP BY archetype_damage, archetype_defense,
                         slot, recommendation_category, league
                ORDER BY total DESC
                """,
                league,
            )
        return [dict(r) for r in rows]
    except Exception:
        logger.warning("Failed to query feedback stats", exc_info=True)
        return []


async def count_session_feedback(
    session_id: str, recommendation_rank: int
) -> int:
    """Count how many votes a session has cast for a given recommendation.

    Args:
        session_id: Frontend session UUID.
        recommendation_rank: Recommendation rank (1-5).

    Returns:
        Number of feedback rows (0 or 1 expected).
    """
    if _pool is None:
        return 0
    try:
        async with _pool.acquire() as conn:
            return int(
                await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM feedback
                    WHERE session_id = $1 AND recommendation_rank = $2
                    """,
                    session_id,
                    recommendation_rank,
                )
                or 0
            )
    except Exception:
        return 0
