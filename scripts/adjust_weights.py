#!/usr/bin/env python3
"""Feedback weight adjustment batch script — M6 D6.4.

Queries the feedback table for a given league, calculates
approval ratios per (archetype, slot, category) group, and
writes an updated weights JSON file.

Designed to run weekly (manually or via cron).  Weights are
league-specific and expire when a new league starts.

Usage
-----
::

    python scripts/adjust_weights.py --league Keepers --output weights.json

Requirements
------------
* DATABASE_URL environment variable must point to a live PostgreSQL instance.
* Minimum 50 votes per group are required before adjusting weights; groups
  with fewer votes fall back to the default weight of 1.0.

Output format
-------------
The output JSON has the following structure::

    {
        "league": "Keepers",
        "generated_at": "2026-02-27T12:00:00Z",
        "min_votes_required": 50,
        "weights": {
            "<archetype_damage>.<archetype_defense>.<slot>.<category>": <float>
        }
    }

"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Groups with fewer votes than this threshold fall back to weight=1.0
DEFAULT_MIN_VOTES = 50

# Weight scaling: approval ratio is mapped to [MIN_WEIGHT, MAX_WEIGHT]
MIN_WEIGHT = 0.5
MAX_WEIGHT = 2.0


def _calc_weight(up_ratio: float) -> float:
    """Map an approval ratio to a scoring weight in [MIN_WEIGHT, MAX_WEIGHT].

    A ratio of 1.0 maps to MAX_WEIGHT; 0.0 maps to MIN_WEIGHT; 0.5 maps
    to ~1.0 (neutral).

    Args:
        up_ratio: Float in [0.0, 1.0].

    Returns:
        Adjusted weight float.
    """
    # Linear interpolation: ratio 0.5 → 1.0, 1.0 → MAX_WEIGHT, 0.0 → MIN_WEIGHT
    weight = MIN_WEIGHT + up_ratio * (MAX_WEIGHT - MIN_WEIGHT)
    return round(weight, 4)


async def adjust_weights(
    dsn: str,
    league: str,
    output_path: str,
    min_votes: int = DEFAULT_MIN_VOTES,
) -> None:
    """Query feedback and write updated weights JSON.

    Args:
        dsn: PostgreSQL connection string.
        league: League name to filter by.
        output_path: Path to write the weights JSON file.
        min_votes: Minimum votes per group to apply weight adjustment.
    """
    logger.info("Connecting to database…")
    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:
        logger.error("Cannot connect to database: %s", exc)
        sys.exit(1)

    logger.info("Querying feedback for league=%r…", league)
    try:
        rows = await conn.fetch(
            """
            SELECT
                archetype_damage,
                archetype_defense,
                slot,
                recommendation_category,
                COUNT(*) AS total,
                SUM(CASE WHEN vote = 'up' THEN 1.0 ELSE 0.0 END) AS up_votes
            FROM feedback
            WHERE league = $1
            GROUP BY
                archetype_damage, archetype_defense, slot, recommendation_category
            ORDER BY total DESC
            """,
            league,
        )
    finally:
        await conn.close()

    weights: dict[str, float] = {}
    adjusted = 0
    skipped = 0

    for row in rows:
        total = int(row["total"])
        up_votes = float(row["up_votes"])
        key = ".".join([
            row["archetype_damage"],
            row["archetype_defense"],
            row["slot"],
            row["recommendation_category"],
        ])

        if total < min_votes:
            # Insufficient data — use neutral weight
            weights[key] = 1.0
            skipped += 1
            logger.debug("  %s: %d votes (below threshold) → weight=1.0", key, total)
        else:
            ratio = up_votes / total
            w = _calc_weight(ratio)
            weights[key] = w
            adjusted += 1
            logger.info(
                "  %s: %d votes, ratio=%.3f → weight=%.4f", key, total, ratio, w
            )

    output = {
        "league": league,
        "generated_at": datetime.now(UTC).isoformat(),
        "min_votes_required": min_votes,
        "total_groups": len(rows),
        "adjusted_groups": adjusted,
        "skipped_groups": skipped,
        "weights": weights,
    }

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    logger.info(
        "Weights written to %s (%d adjusted, %d skipped)",
        output_path,
        adjusted,
        skipped,
    )


def main() -> None:
    """Entry point for the weight adjustment script."""
    parser = argparse.ArgumentParser(
        description="Adjust recommendation scoring weights based on feedback."
    )
    parser.add_argument(
        "--league",
        required=True,
        help="League name to process (e.g. Keepers).",
    )
    parser.add_argument(
        "--output",
        default="weights.json",
        help="Path to write the weights JSON file (default: weights.json).",
    )
    parser.add_argument(
        "--min-votes",
        type=int,
        default=DEFAULT_MIN_VOTES,
        help=(
            f"Minimum votes per group before adjusting (default: {DEFAULT_MIN_VOTES})."
        ),
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help=(
            "PostgreSQL DSN (default: DATABASE_URL env variable)."
        ),
    )
    args = parser.parse_args()

    dsn = args.dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        logger.error(
            "No database URL provided. "
            "Pass --dsn or set the DATABASE_URL env variable."
        )
        sys.exit(1)

    asyncio.run(
        adjust_weights(
            dsn=dsn,
            league=args.league,
            output_path=args.output,
            min_votes=args.min_votes,
        )
    )


if __name__ == "__main__":
    main()
