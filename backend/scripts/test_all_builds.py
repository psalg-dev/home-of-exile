"""
Test the recommendations endpoint with every example PoB export.
Validates that each build produces exactly 5 recommendations.

Usage (from repo root):
    python backend/scripts/test_all_builds.py [--base-url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"


def _discover_pob_files() -> list[tuple[str, Path]]:
    """Return (label, path) pairs for every *.txt in examples/."""
    results = []
    for subdir in sorted(EXAMPLES_DIR.rglob("*.txt")):
        label = subdir.relative_to(EXAMPLES_DIR).with_suffix("").as_posix()
        results.append((label, subdir))
    return results


# ---------------------------------------------------------------------------
# Decode helpers (mirrors test_recommendations.py)
# ---------------------------------------------------------------------------

def decode_pob_code(code: str) -> str:
    code = code.strip()
    code = code.replace("-", "+").replace("_", "/")
    code += "=" * ((4 - len(code) % 4) % 4)
    return zlib.decompress(base64.b64decode(code)).decode("utf-8")


def post_json(url: str, data: dict, timeout: int = 600) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# PoB XML → BuildData parser
# ---------------------------------------------------------------------------

def parse_pob_xml_to_build_data(xml: str) -> dict:
    """Parse PoB XML into the backend BuildData format."""
    root = ET.fromstring(xml)
    build_elem = root.find("Build")

    def attr(elem, name, default=""):
        return elem.get(name, default) if elem is not None else default

    # PlayerStat → stats dict
    stats: dict[str, str] = {}
    if build_elem is not None:
        for ps in build_elem.findall("PlayerStat"):
            k = ps.get("stat", "")
            v = ps.get("value", "0")
            if k:
                stats[k] = v

    # Skills
    skills_elem = root.find("Skills")
    skill_groups = []
    if skills_elem is not None:
        skill_elems: list[ET.Element] = []
        skill_sets = skills_elem.findall("SkillSet")
        if skill_sets:
            for ss in skill_sets:
                skill_elems.extend(ss.findall("Skill"))
        else:
            skill_elems = skills_elem.findall("Skill")

        for skill in skill_elems:
            gems = []
            for gem in skill.findall("Gem"):
                gems.append({
                    "name_spec": gem.get("nameSpec", ""),
                    "skill_id": gem.get("skillId", ""),
                    "level": int(gem.get("level", "1")),
                    "quality": int(gem.get("quality", "0")),
                    "enabled": gem.get("enabled", "true").lower() == "true",
                    "is_support": "Support" in gem.get("nameSpec", ""),
                })
            skill_groups.append({
                "slot": skill.get("slot", ""),
                "label": skill.get("label", ""),
                "enabled": skill.get("enabled", "true").lower() == "true",
                "gems": gems,
                "main_active_gem_index": 0,
            })

    # Items (PoB v2 format)
    items_elem = root.find("Items")
    items: dict[str, dict] = {}
    if items_elem is not None:
        item_map: dict[str, dict] = {}
        for item in items_elem.findall("Item"):
            item_id = item.get("id", "")
            raw = item.text or ""
            lines = [ln.strip() for ln in raw.strip().split("\n") if ln.strip()]
            name = lines[1] if len(lines) > 1 else ""
            base = lines[2] if len(lines) > 2 else ""
            rarity = "normal"
            if lines and lines[0].startswith("Rarity:"):
                rarity = lines[0].split(":", 1)[1].strip().lower()
            if item_id:
                item_map[item_id] = {"name": name, "base_name": base, "rarity": rarity}

        active_set_id = items_elem.get("activeItemSet", "1")
        item_set = None
        for elem in items_elem.findall("ItemSet"):
            if elem.get("id") == active_set_id:
                item_set = elem
                break
        if item_set is None and items_elem.findall("ItemSet"):
            item_set = items_elem.findall("ItemSet")[0]

        slot_container = item_set if item_set is not None else items_elem
        for slot_elem in slot_container.findall("Slot"):
            slot_name = slot_elem.get("name", "")
            item_id = slot_elem.get("itemId", "0")
            if item_id == "0":
                continue
            if any(x in slot_name for x in ["Abyssal", "Swap", "Socket", "Graft"]):
                continue
            if slot_name and item_id and item_id in item_map:
                i = item_map[item_id]
                items[slot_name] = {
                    "name": i["name"],
                    "base_name": i["base_name"],
                    "slot": slot_name,
                    "rarity": i["rarity"],
                    "mods": [],
                }

    # Infer league from the pob—absent from XML, so leave as-is
    return {
        "character_name": attr(build_elem, "characterName"),
        "class": attr(build_elem, "className", "Unknown"),
        "ascendancy": attr(build_elem, "ascendClassName", ""),
        "level": int(attr(build_elem, "level", "1")),
        "bandit": attr(build_elem, "bandit", "None"),
        "main_skill": "",
        "stats": {
            "life": int(float(stats.get("Life", "0"))),
            "energy_shield": int(float(stats.get("EnergyShield", "0"))),
            "dps": float(stats.get("CombinedDPS", stats.get("TotalDPS", "0"))),
            "fire_res": int(float(stats.get("FireResist", "0"))),
            "cold_res": int(float(stats.get("ColdResist", "0"))),
            "lightning_res": int(float(stats.get("LightningResist", "0"))),
            "chaos_res": int(float(stats.get("ChaosResist", "0"))),
        },
        "items": items,
        "skill_groups": skill_groups,
        "passive_tree": [],
    }


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

PASS = "✓"
FAIL = "✗"
WARN = "!"


def run_build(label: str, path: Path, base_url: str, league: str = "Standard") -> dict:
    """Test one build; return a result dict."""
    result: dict = {
        "label": label,
        "path": str(path),
        "status": "unknown",
        "error": None,
        "class": None,
        "ascendancy": None,
        "level": None,
        "items_parsed": 0,
        "rec_count": 0,
        "sim_count": 0,
        "critical_issues": 0,
        "elapsed": 0.0,
        "recommendations": [],
    }

    # 1. Read raw code
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        result["status"] = "file_error"
        result["error"] = str(exc)
        return result

    # 2. Decode
    try:
        xml = decode_pob_code(raw)
    except Exception as exc:
        result["status"] = "decode_error"
        result["error"] = str(exc)
        return result

    # 3. Parse
    try:
        build_data = parse_pob_xml_to_build_data(xml)
    except Exception as exc:
        result["status"] = "parse_error"
        result["error"] = str(exc)
        return result

    result["class"] = build_data["class"]
    result["ascendancy"] = build_data["ascendancy"]
    result["level"] = build_data["level"]
    result["items_parsed"] = len(build_data["items"])

    # 4. POST to API
    body = {
        "build": build_data,
        "build_code": raw,
        "league": league,
        "max_candidates_per_slot": 3,
    }

    try:
        resp = post_json(f"{base_url}/api/v1/recommendations", body)
    except urllib.error.HTTPError as exc:
        result["status"] = "http_error"
        try:
            detail = json.loads(exc.read().decode())
        except Exception:
            detail = str(exc)
        result["error"] = detail
        return result
    except Exception as exc:
        result["status"] = "request_error"
        result["error"] = str(exc)
        return result

    rec_count = len(resp.get("recommendations", []))
    result["rec_count"] = rec_count
    result["sim_count"] = resp.get("simulation_count", 0)
    result["critical_issues"] = len(resp.get("critical_issues", []))
    result["elapsed"] = resp.get("elapsed_seconds", 0.0)
    result["recommendations"] = resp.get("recommendations", [])
    result["status"] = "ok" if rec_count >= 5 else "low_recs"

    return result


def print_result(r: dict) -> None:
    icon = PASS if r["status"] == "ok" else FAIL
    label = r["label"]
    if r["status"] in ("file_error", "decode_error", "parse_error",
                        "http_error", "request_error"):
        print(f"  {icon} {label}  [{r['status']}] {r['error']}")
        return

    rec_str = f"{r['rec_count']}/5 recs"
    sim_str = f"{r['sim_count']} sims"
    build_str = f"{r['class']}/{r['ascendancy']} lv{r['level']}"
    items_str = f"{r['items_parsed']} items"
    elapsed_str = f"{r['elapsed']:.1f}s"

    ok_marker = PASS if r["rec_count"] >= 5 else FAIL
    print(f"  {ok_marker} {label:<40} {build_str:<28} {items_str:<10} "
          f"{rec_str:<10} {sim_str:<12} {elapsed_str}")

    if r["rec_count"] > 0:
        for rec in r["recommendations"][:5]:
            d = rec.get("deltas", {})
            print(f"       [{rec.get('category','?')}] {rec.get('suggested_item','?')[:35]:<35} "
                  f"({rec.get('slot','?'):<12}) score={rec.get('score',0):.3f} "
                  f"dps={d.get('dps',0):+,.0f} life={d.get('life',0):+,.0f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test all PoB builds → recommendations")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="Backend API URL (default: http://localhost:8000)")
    parser.add_argument("--league", default="Standard",
                        help="League name to pass (default: Standard)")
    args = parser.parse_args()

    builds = _discover_pob_files()
    if not builds:
        print("No PoB files found under examples/")
        sys.exit(1)

    print(f"\n{'='*80}")
    print(f"Testing {len(builds)} build(s) → {args.base_url}")
    print(f"{'='*80}\n")

    results = []
    for label, path in builds:
        print(f"  → {label} ...")
        sys.stdout.flush()
        r = run_build(label, path, args.base_url, args.league)
        print_result(r)
        results.append(r)
        print()

    # Summary
    ok = [r for r in results if r["status"] == "ok"]
    fail = [r for r in results if r["status"] != "ok"]

    print(f"\n{'='*80}")
    print(f"SUMMARY: {len(ok)}/{len(results)} builds returned 5 recommendations")
    if fail:
        print("\nFailed builds:")
        for r in fail:
            print(f"  {FAIL} {r['label']} — {r['status']}: "
                  f"{r.get('rec_count','?')}/5 recs | {r.get('error','')}")
    print(f"{'='*80}\n")

    sys.exit(0 if not fail else 1)


if __name__ == "__main__":
    main()
