"""Tests for the XML structure of decoded PoB keeper builds.

Verifies structural expectations for the phantasm-summoner keeper fixture
by decoding the base64/zlib PoB export code and asserting on XML content.
The tests are automatically skipped when the fixture file is absent.
"""

from __future__ import annotations

import base64
import re
import zlib
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "examples" / "keepers"
_PHANTASM_PATH = _FIXTURE_DIR / "phantasm-summoner" / "pob.txt"

skip_if_no_fixture = pytest.mark.skipif(
    not _PHANTASM_PATH.exists(),
    reason="phantasm-summoner fixture not found",
)


def _decode_pob(path: Path) -> str:
    """Decode a PoB export code file to its raw XML string.

    Args:
        path: Path to the ``.txt`` file containing the base64 PoB code.

    Returns:
        Decompressed UTF-8 XML string.
    """
    code = path.read_text(encoding="utf-8").strip()
    code = re.sub(r"\s+", "", code)
    # Normalise URL-safe → standard base64
    code = code.replace("-", "+").replace("_", "/")
    code += "=" * ((-len(code)) % 4)
    return zlib.decompress(base64.b64decode(code)).decode("utf-8")


# ---------------------------------------------------------------------------
# Tests: root element
# ---------------------------------------------------------------------------


@skip_if_no_fixture
def test_phantasm_has_pob_root_element() -> None:
    """Decoded XML must contain a PathOfBuilding root element."""
    xml = _decode_pob(_PHANTASM_PATH)
    assert re.search(r"<PathOfBuilding[\s>]", xml), (
        "PathOfBuilding root element not found"
    )


# ---------------------------------------------------------------------------
# Tests: Build attributes
# ---------------------------------------------------------------------------


@skip_if_no_fixture
def test_phantasm_has_tree_version() -> None:
    """Decoded XML must contain a treeVersion attribute."""
    xml = _decode_pob(_PHANTASM_PATH)
    match = re.search(r'treeVersion="([^"]+)"', xml)
    assert match is not None, "treeVersion attribute not found in XML"
    assert match.group(1), "treeVersion must be non-empty"


@skip_if_no_fixture
def test_phantasm_class_is_witch() -> None:
    """Phantasm-summoner fixture must have className='Witch'."""
    xml = _decode_pob(_PHANTASM_PATH)
    m = re.search(r'className="([^"]+)"', xml)
    assert m is not None, "className attribute not found"
    assert m.group(1) == "Witch", (
        f"Expected Witch, got {m.group(1)!r}"
    )


@skip_if_no_fixture
def test_phantasm_ascendancy_is_necromancer() -> None:
    """Phantasm-summoner fixture must have ascendClassName='Necromancer'."""
    xml = _decode_pob(_PHANTASM_PATH)
    m = re.search(r'ascendClassName="([^"]+)"', xml)
    assert m is not None, "ascendClassName attribute not found"
    assert m.group(1) == "Necromancer", (
        f"Expected Necromancer, got {m.group(1)!r}"
    )


# ---------------------------------------------------------------------------
# Tests: Skill structure
# ---------------------------------------------------------------------------


@skip_if_no_fixture
def test_phantasm_has_skill_groups() -> None:
    """Decoded XML must contain at least one Skill element."""
    xml = _decode_pob(_PHANTASM_PATH)
    count = len(re.findall(r"<Skill\b", xml))
    assert count >= 1, f"Expected ≥1 Skill elements, found {count}"


@skip_if_no_fixture
def test_phantasm_has_gem_elements() -> None:
    """Decoded XML must contain Gem elements inside skills."""
    xml = _decode_pob(_PHANTASM_PATH)
    count = len(re.findall(r"<Gem\b", xml))
    assert count >= 1, f"Expected ≥1 Gem elements, found {count}"


@skip_if_no_fixture
def test_phantasm_has_main_skill_reference() -> None:
    """Build element must reference a main skill via mainActiveSkill or mainSocketGroup."""
    xml = _decode_pob(_PHANTASM_PATH)
    has_main_active = re.search(r"mainActiveSkill=", xml) is not None
    has_socket_group = re.search(r"mainSocketGroup=", xml) is not None
    assert has_main_active or has_socket_group, (
        "Neither mainActiveSkill nor mainSocketGroup found in Build element"
    )


# ---------------------------------------------------------------------------
# Tests: active skill set (SkillSet wrapper format)
# ---------------------------------------------------------------------------


@skip_if_no_fixture
def test_phantasm_active_skill_set_is_valid() -> None:
    """If activeSkillSet attribute is present it must be a positive integer."""
    xml = _decode_pob(_PHANTASM_PATH)
    m = re.search(r'activeSkillSet="([^"]+)"', xml)
    if m is None:
        pytest.skip("activeSkillSet not present in this fixture")
    value = int(m.group(1))
    assert value >= 1, f"activeSkillSet must be ≥1, got {value}"
