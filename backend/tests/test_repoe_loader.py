"""
Integration tests for the RePoE loader service.

These tests require the data/repoe/ files to be present (run ingest_repoe.py first).
They are skipped automatically if the data files are not found.
"""

from pathlib import Path

import pytest

# Check if data files exist (skip tests if not)
_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "repoe"
_DATA_AVAILABLE = (_DATA_DIR / "base_items.json").exists()

skip_if_no_data = pytest.mark.skipif(
    not _DATA_AVAILABLE,
    reason="RePoE data files not found — run scripts/ingest_repoe.py first",
)


@skip_if_no_data
def test_load_base_items_returns_over_500_entries() -> None:
    """load_base_items() should return more than 500 entries."""
    # Import inside test to avoid import-time side effects during collection
    from app.services.repoe_loader import load_base_items  # noqa: PLC0415

    items = load_base_items()
    assert len(items) > 500, f"Expected >500 items, got {len(items)}"


@skip_if_no_data
def test_load_gems_returns_entries() -> None:
    """load_gems() should return a non-empty dict."""
    from app.services.repoe_loader import load_gems  # noqa: PLC0415

    gems = load_gems()
    assert len(gems) > 0


@skip_if_no_data
def test_load_mods_returns_entries() -> None:
    """load_mods() should return a non-empty dict."""
    from app.services.repoe_loader import load_mods  # noqa: PLC0415

    mods = load_mods()
    assert len(mods) > 0
