"""Pydantic models for the M6 feedback system.

These models describe the request and response payloads for the
``/api/v1/feedback`` and ``/api/v1/track/trade-click`` endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Feedback context (build + recommendation snapshot)
# ---------------------------------------------------------------------------


class FeedbackContext(BaseModel):
    """Snapshot of the build and recommendation at the time of feedback.

    Attributes:
        archetype_damage: Damage archetype label (e.g. ``'phys'``).
        archetype_defense: Defense archetype label (e.g. ``'life'``).
        archetype_playstyle: Playstyle label (e.g. ``'caster'``).
        character_level: Level of the character at time of analysis.
        league: Active league name.
        recommendation_category: Category of the recommendation voted on.
        slot: Equipment or gem slot of the recommendation.
        suggested_item: Name of the suggested upgrade.
        dps_delta: Change in DPS from the simulation, if available.
        ehp_delta: Change in effective HP from the simulation, if available.
        price_divine: Price in divine orbs for the suggested item, if known.
    """

    archetype_damage: str = Field(default="")
    archetype_defense: str = Field(default="")
    archetype_playstyle: str = Field(default="")
    character_level: int = Field(default=0, ge=0)
    league: str = Field(default="")
    recommendation_category: str = Field(default="")
    slot: str = Field(default="")
    suggested_item: str = Field(default="")
    dps_delta: float | None = Field(default=None)
    ehp_delta: float | None = Field(default=None)
    price_divine: float | None = Field(default=None)


# ---------------------------------------------------------------------------
# Feedback request / response
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    """Request body for ``POST /api/v1/feedback``.

    Attributes:
        session_id: Frontend session UUID (persisted in sessionStorage).
        recommendation_rank: Rank of the recommendation voted on (1-5).
        vote: ``'up'`` or ``'down'``.
        context: Build and recommendation context snapshot.
    """

    session_id: str = Field(min_length=1, max_length=128)
    recommendation_rank: int = Field(ge=1, le=5)
    vote: str = Field(pattern="^(up|down)$")
    context: FeedbackContext = Field(default_factory=FeedbackContext)


class FeedbackResponse(BaseModel):
    """Response for ``POST /api/v1/feedback``.

    Attributes:
        stored: ``True`` if the vote was persisted to PostgreSQL.
        message: Human-readable status message.
    """

    stored: bool
    message: str


# ---------------------------------------------------------------------------
# Trade click tracking
# ---------------------------------------------------------------------------


class TradeClickRequest(BaseModel):
    """Request body for ``POST /api/v1/track/trade-click``.

    Attributes:
        session_id: Frontend session UUID.
        recommendation_rank: Rank of the recommendation whose trade link
            was clicked (1-5).
        suggested_item: Name of the suggested item.
        league: Active league name.
    """

    session_id: str = Field(min_length=1, max_length=128)
    recommendation_rank: int = Field(ge=1, le=5)
    suggested_item: str = Field(default="")
    league: str = Field(default="")


class TradeClickResponse(BaseModel):
    """Response for ``POST /api/v1/track/trade-click``.

    Attributes:
        stored: ``True`` if the click was persisted.
    """

    stored: bool


# ---------------------------------------------------------------------------
# Feedback stats (admin)
# ---------------------------------------------------------------------------


class FeedbackStatRow(BaseModel):
    """One row of aggregated feedback statistics.

    Attributes:
        archetype_damage: Damage archetype.
        archetype_defense: Defense archetype.
        slot: Equipment or gem slot.
        recommendation_category: Recommendation category.
        league: League name.
        total: Total votes.
        up_votes: Number of thumbs-up votes.
        down_votes: Number of thumbs-down votes.
        up_ratio: Approval ratio (0.0-1.0); ``None`` when ``total == 0``.
    """

    archetype_damage: str
    archetype_defense: str
    slot: str
    recommendation_category: str
    league: str
    total: int
    up_votes: int
    down_votes: int
    up_ratio: float | None


class FeedbackStatsResponse(BaseModel):
    """Response for ``GET /api/v1/feedback/stats``.

    Attributes:
        rows: List of aggregate feedback stat rows.
        db_available: Whether PostgreSQL was reachable.
    """

    rows: list[FeedbackStatRow]
    db_available: bool
