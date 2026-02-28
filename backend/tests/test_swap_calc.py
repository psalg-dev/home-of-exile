"""Tests for LuaJITWorker.calculate_with_swap().

Verifies baseline/modified stat comparison, error propagation, and
calc-counter increments — all using mocked _call to avoid requiring
a live LuaJIT process.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.luajit_pool import LuaJITWorker, LuaJITWorkerError

# ---------------------------------------------------------------------------
# Sample item text (PoE item format)
# ---------------------------------------------------------------------------

_ITEM_TEXT = """\
Hrimnor's Resolve
Sallow Mask
Quality: 20
Sockets: R-R-R-G
Item Level: 86
+30 to Strength
+25% to Cold Resistance
30% increased Damage over Time
Covered in Frost cannot be Frozen
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_worker() -> LuaJITWorker:
    """Return a LuaJITWorker with a fake-ready process."""
    worker = LuaJITWorker(
        worker_id=1,
        pob_src_dir="/fake/pob/src",
        luajit_cmd="luajit",
    )
    worker._ready = True
    worker._process = AsyncMock()
    worker._process.returncode = None
    return worker


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_swap_returns_baseline_and_modified_stats() -> None:
    """calculate_with_swap() must include both baseline and modified dicts."""
    worker = _make_worker()
    baseline_stats = {"Life": 5000.0, "CombinedDPS": 1_200_000.0}
    modified_stats = {"Life": 4800.0, "CombinedDPS": 1_500_000.0}
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},  # load_build_xml
            {"ok": True, "stats": baseline_stats},  # get_stats (baseline)
            {"ok": True, "item": {"name": "Hrimnor's Resolve"}},  # add_item_text
            {"ok": True, "stats": modified_stats},  # get_stats (modified)
        ]
    )

    result = await worker.calculate_with_swap("<xml/>", _ITEM_TEXT, "Helmet")

    assert result["baseline"]["Life"] == 5000.0
    assert result["modified"]["Life"] == 4800.0
    assert result["baseline"]["CombinedDPS"] == 1_200_000.0
    assert result["modified"]["CombinedDPS"] == 1_500_000.0


@pytest.mark.asyncio
async def test_swap_includes_item_info_from_add_item_text() -> None:
    """calculate_with_swap() must pass through item info from add_item_text."""
    worker = _make_worker()
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},
            {"ok": True, "stats": {}},
            {"ok": True, "item": {"name": "Hrimnor's Resolve", "slot": "Helmet"}},
            {"ok": True, "stats": {}},
        ]
    )

    result = await worker.calculate_with_swap("<xml/>", _ITEM_TEXT, "Helmet")

    assert result["item"]["name"] == "Hrimnor's Resolve"
    assert result["item"]["slot"] == "Helmet"


@pytest.mark.asyncio
async def test_swap_increments_num_calcs() -> None:
    """calculate_with_swap() must increment _num_calcs after success."""
    worker = _make_worker()
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},
            {"ok": True, "stats": {}},
            {"ok": True},
            {"ok": True, "stats": {}},
        ]
    )
    assert worker._num_calcs == 0
    await worker.calculate_with_swap("<xml/>", _ITEM_TEXT, "Helmet")
    assert worker._num_calcs == 1


@pytest.mark.asyncio
async def test_swap_empty_item_info_when_add_returns_none() -> None:
    """calculate_with_swap() must default item to {} when add_item_text omits it."""
    worker = _make_worker()
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},
            {"ok": True, "stats": {"Life": 1000.0}},
            {"ok": True},  # no 'item' key
            {"ok": True, "stats": {"Life": 1100.0}},
        ]
    )

    result = await worker.calculate_with_swap("<xml/>", _ITEM_TEXT, "Body Armour")
    assert result["item"] == {}


# ---------------------------------------------------------------------------
# Error propagation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_swap_raises_on_load_failure() -> None:
    """calculate_with_swap() must raise LuaJITWorkerError when load_build_xml fails."""
    worker = _make_worker()
    worker._call = AsyncMock(return_value={"ok": False, "error": "bad xml"})

    with pytest.raises(LuaJITWorkerError, match="load_build_xml failed"):
        await worker.calculate_with_swap("<bad/>", _ITEM_TEXT, "Helmet")


@pytest.mark.asyncio
async def test_swap_raises_on_baseline_stats_failure() -> None:
    """calculate_with_swap() must raise when baseline get_stats fails."""
    worker = _make_worker()
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},  # load_build_xml
            {"ok": False, "error": "engine crash"},  # get_stats baseline
        ]
    )

    with pytest.raises(LuaJITWorkerError, match="get_stats.*baseline"):
        await worker.calculate_with_swap("<xml/>", _ITEM_TEXT, "Helmet")


@pytest.mark.asyncio
async def test_swap_raises_on_add_item_failure() -> None:
    """calculate_with_swap() must raise when add_item_text fails."""
    worker = _make_worker()
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},
            {"ok": True, "stats": {}},
            {"ok": False, "error": "invalid item text"},
        ]
    )

    with pytest.raises(LuaJITWorkerError, match="add_item_text failed"):
        await worker.calculate_with_swap("<xml/>", "bad item text", "Helmet")


@pytest.mark.asyncio
async def test_swap_raises_on_modified_stats_failure() -> None:
    """calculate_with_swap() must raise when modified get_stats fails."""
    worker = _make_worker()
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},
            {"ok": True, "stats": {"Life": 5000.0}},
            {"ok": True},
            {"ok": False, "error": "engine crash"},
        ]
    )

    with pytest.raises(LuaJITWorkerError, match="get_stats.*modified"):
        await worker.calculate_with_swap("<xml/>", _ITEM_TEXT, "Helmet")

