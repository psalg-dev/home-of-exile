"""Tests for minion-specific stat field coverage in the LuaJIT pool.

Verifies that _DEFAULT_STAT_FIELDS includes all minion-relevant keys
and that LuaJITWorker.calculate() dispatches and assembles results
correctly using mocked _call responses.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.luajit_pool import (
    LuaJITPoolManager,
    LuaJITWorker,
    LuaJITWorkerError,
    _DEFAULT_STAT_FIELDS,
)

# ---------------------------------------------------------------------------
# _DEFAULT_STAT_FIELDS coverage
# ---------------------------------------------------------------------------


def test_default_stat_fields_includes_minion_dps() -> None:
    """_DEFAULT_STAT_FIELDS must expose MinionTotalDPS and related DPS fields."""
    required = {"MinionTotalDPS", "MinionFullDPS", "MinionCombinedDPS", "MinionAverageDamage"}
    missing = required - set(_DEFAULT_STAT_FIELDS)
    assert not missing, f"Missing minion DPS fields: {missing}"


def test_default_stat_fields_includes_minion_defences() -> None:
    """_DEFAULT_STAT_FIELDS must expose MinionLife and MinionEnergyShield."""
    required = {"MinionLife", "MinionEnergyShield"}
    missing = required - set(_DEFAULT_STAT_FIELDS)
    assert not missing, f"Missing minion defence fields: {missing}"


def test_default_stat_fields_includes_player_core_stats() -> None:
    """_DEFAULT_STAT_FIELDS must include Life, EnergyShield, resistances, and DPS."""
    required = {
        "Life", "EnergyShield", "Armour", "Evasion",
        "FireResist", "ColdResist", "LightningResist", "ChaosResist",
        "CombinedDPS",
    }
    missing = required - set(_DEFAULT_STAT_FIELDS)
    assert not missing, f"Missing player core stat fields: {missing}"


def test_default_stat_fields_has_no_duplicates() -> None:
    """_DEFAULT_STAT_FIELDS must not contain duplicate entries."""
    assert len(_DEFAULT_STAT_FIELDS) == len(set(_DEFAULT_STAT_FIELDS)), (
        "Duplicate entries in _DEFAULT_STAT_FIELDS"
    )


# ---------------------------------------------------------------------------
# LuaJITWorker.calculate() – mocked _call
# ---------------------------------------------------------------------------


def _make_worker(max_calcs: int = 500) -> LuaJITWorker:
    """Return a LuaJITWorker with a fake-ready process."""
    worker = LuaJITWorker(
        worker_id=1,
        pob_src_dir="/fake/pob/src",
        luajit_cmd="luajit",
        max_calcs=max_calcs,
    )
    worker._ready = True
    worker._process = AsyncMock()
    worker._process.returncode = None  # still running
    return worker


@pytest.mark.asyncio
async def test_calculate_returns_stats_including_minion_dps() -> None:
    """calculate() must surface MinionTotalDPS when the worker returns it."""
    worker = _make_worker()
    expected_stats = {
        "Life": 3200.0,
        "EnergyShield": 0.0,
        "MinionTotalDPS": 2_500_000.0,
        "MinionLife": 8000.0,
    }
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},  # load_build_xml
            {"ok": True, "stats": expected_stats},  # get_stats
        ]
    )

    result = await worker.calculate("<xml><Build level='90'/></xml>")

    assert result["stats"]["MinionTotalDPS"] == 2_500_000.0
    assert result["stats"]["MinionLife"] == 8000.0


@pytest.mark.asyncio
async def test_calculate_raises_on_load_failure() -> None:
    """calculate() must raise LuaJITWorkerError when load_build_xml fails."""
    worker = _make_worker()
    worker._call = AsyncMock(return_value={"ok": False, "error": "parse failed"})

    with pytest.raises(LuaJITWorkerError, match="load_build_xml failed"):
        await worker.calculate("<bad/>")


@pytest.mark.asyncio
async def test_calculate_raises_on_stats_failure() -> None:
    """calculate() must raise LuaJITWorkerError when get_stats fails."""
    worker = _make_worker()
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},  # load_build_xml succeeds
            {"ok": False, "error": "stats error"},  # get_stats fails
        ]
    )

    with pytest.raises(LuaJITWorkerError, match="get_stats failed"):
        await worker.calculate("<xml/>")


@pytest.mark.asyncio
async def test_calculate_increments_num_calcs() -> None:
    """calculate() must increment _num_calcs after each successful call."""
    worker = _make_worker()
    worker._call = AsyncMock(
        side_effect=[
            {"ok": True},
            {"ok": True, "stats": {"Life": 1000.0}},
        ]
    )
    assert worker._num_calcs == 0
    await worker.calculate("<xml/>")
    assert worker._num_calcs == 1


# ---------------------------------------------------------------------------
# LuaJITWorker properties
# ---------------------------------------------------------------------------


def test_is_ready_false_when_not_started() -> None:
    """is_ready must be False for a freshly created worker."""
    worker = LuaJITWorker(worker_id=1, pob_src_dir="/fake", luajit_cmd="luajit")
    assert not worker.is_ready


def test_needs_recycle_false_below_max() -> None:
    """needs_recycle must be False when _num_calcs < max_calcs."""
    worker = LuaJITWorker(worker_id=1, pob_src_dir="/fake", luajit_cmd="luajit", max_calcs=5)
    worker._num_calcs = 4
    assert not worker.needs_recycle


def test_needs_recycle_true_at_max() -> None:
    """needs_recycle must be True when _num_calcs >= max_calcs."""
    worker = LuaJITWorker(worker_id=1, pob_src_dir="/fake", luajit_cmd="luajit", max_calcs=5)
    worker._num_calcs = 5
    assert worker.needs_recycle


@pytest.mark.asyncio
async def test_needs_recycle_after_max_successful_calcs() -> None:
    """Worker should need recycling after max_calcs successful calculations."""
    worker = _make_worker(max_calcs=2)
    responses = [
        {"ok": True}, {"ok": True, "stats": {}},
        {"ok": True}, {"ok": True, "stats": {}},
    ]
    worker._call = AsyncMock(side_effect=responses)

    assert not worker.needs_recycle
    await worker.calculate("<xml/>")
    assert not worker.needs_recycle
    await worker.calculate("<xml/>")
    assert worker.needs_recycle


# ---------------------------------------------------------------------------
# LuaJITWorker.ping()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_returns_true_when_pong_received() -> None:
    """ping() must return True when the worker responds with pong=true."""
    worker = _make_worker()
    worker._call = AsyncMock(return_value={"ok": True, "pong": True})
    assert await worker.ping() is True


@pytest.mark.asyncio
async def test_ping_returns_false_on_worker_error() -> None:
    """ping() must return False (not raise) when _call raises LuaJITWorkerError."""
    worker = _make_worker()
    worker._call = AsyncMock(side_effect=LuaJITWorkerError("timeout"))
    result = await worker.ping()
    assert result is False


@pytest.mark.asyncio
async def test_ping_marks_worker_not_ready_on_error() -> None:
    """ping() must set _ready=False when the worker fails to respond."""
    worker = _make_worker()
    worker._call = AsyncMock(side_effect=LuaJITWorkerError("io error"))
    await worker.ping()
    assert not worker._ready


@pytest.mark.asyncio
async def test_ping_returns_false_when_pong_missing() -> None:
    """ping() must return False when pong key is absent from the response."""
    worker = _make_worker()
    worker._call = AsyncMock(return_value={"ok": True})
    result = await worker.ping()
    assert result is False


# ---------------------------------------------------------------------------
# LuaJITWorker._call() – process not running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_raises_when_process_is_none() -> None:
    """_call() must raise LuaJITWorkerError when process has not been started."""
    worker = LuaJITWorker(worker_id=1, pob_src_dir="/fake", luajit_cmd="luajit")
    # _process is None by default
    with pytest.raises(LuaJITWorkerError, match="process is not running"):
        await worker._call("ping")


# ---------------------------------------------------------------------------
# LuaJITPoolManager – initial state
# ---------------------------------------------------------------------------


def test_pool_manager_not_available_before_startup() -> None:
    """LuaJITPoolManager.is_available must be False before startup() is called."""
    manager = LuaJITPoolManager(
        pool_size=2,
        pob_src_dir="/fake/pob/src",
        luajit_cmd="luajit",
    )
    assert not manager.is_available


@pytest.mark.asyncio
async def test_pool_manager_stays_unavailable_when_luajit_missing() -> None:
    """startup() must leave pool unavailable when luajit binary is not found."""
    manager = LuaJITPoolManager(
        pool_size=1,
        pob_src_dir="/fake/pob/src",
        luajit_cmd="definitely_does_not_exist_luajit_binary_xyz",
    )
    await manager.startup()
    assert not manager.is_available


@pytest.mark.asyncio
async def test_pool_manager_shutdown_marks_unavailable() -> None:
    """shutdown() must set is_available to False."""
    manager = LuaJITPoolManager(
        pool_size=1,
        pob_src_dir="/fake/pob/src",
        luajit_cmd="luajit",
    )
    # Manually set available to True to simulate a started pool
    manager._available = True
    await manager.shutdown()
    assert not manager.is_available

