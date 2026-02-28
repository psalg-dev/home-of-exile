"""
Quick smoke-test for LLM explanation integration.

Posts the phantasm-summoner PoB to /api/v1/recommendations and prints
each recommendation's explanation text and explanation_source field
('llm' = OpenAI was called, 'template' = fallback).

Also queries GET /api/v1/admin/llm-usage to show token/cost metrics.
"""
import base64
import json
import sys
import urllib.request
import urllib.error
import zlib

import hashlib

POB_CODE_FILE = r"c:\dev\workspace\home-of-exile\examples\keepers\phantasm-summoner\pob.txt"
BASE_URL = "http://localhost:8000"


def _llm_ab_group(session_id: str) -> bool:
    """Mirror of simulation._is_llm_ab_group — True means LLM group."""
    digest = hashlib.md5(session_id.encode(), usedforsecurity=False).hexdigest()
    return int(digest[:4], 16) % 2 == 0


def _find_llm_session_id() -> str:
    """Return a session UUID that's guaranteed to fall in the LLM A/B group."""
    import uuid
    for _ in range(1000):
        sid = str(uuid.uuid4())
        if _llm_ab_group(sid):
            return sid
    raise RuntimeError("Could not find an LLM-group session ID")


# ── helpers ──────────────────────────────────────────────────────────────────

def decode_pob(code: str) -> str:
    code = code.strip().replace("-", "+").replace("_", "/")
    code += "=" * ((4 - len(code) % 4) % 4)
    return zlib.decompress(base64.b64decode(code)).decode("utf-8")


def http_post(url: str, data: dict) -> dict:
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def http_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def parse_pob(xml: str) -> dict:
    """Minimal parse — enough to drive the recommendations endpoint."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml)
    b = root.find("Build")

    def _attr(el, k, d=""):
        return el.get(k, d) if el is not None else d

    stats: dict = {}
    for ps in (b.findall("PlayerStat") if b is not None else []):
        stats[ps.get("stat", "")] = ps.get("value", "0")

    # Skills
    skill_groups = []
    se = root.find("Skills")
    if se is not None:
        skill_elems = []
        for ss in se.findall("SkillSet"):
            skill_elems.extend(ss.findall("Skill"))
        if not skill_elems:
            skill_elems = se.findall("Skill")
        for sk in skill_elems:
            gems = [
                {
                    "name_spec": g.get("nameSpec", ""),
                    "skill_id": g.get("skillId", ""),
                    "level": int(g.get("level", "1")),
                    "quality": int(g.get("quality", "0")),
                    "enabled": g.get("enabled", "true").lower() == "true",
                    "is_support": "Support" in g.get("nameSpec", ""),
                }
                for g in sk.findall("Gem")
            ]
            skill_groups.append(
                {
                    "slot": sk.get("slot", ""),
                    "label": sk.get("label", ""),
                    "enabled": sk.get("enabled", "true").lower() == "true",
                    "gems": gems,
                    "main_active_gem_index": 0,
                }
            )

    # Items
    ie = root.find("Items")
    items: dict = {}
    if ie is not None:
        item_map: dict = {}
        for item in ie.findall("Item"):
            iid = item.get("id", "")
            lines = [l.strip() for l in (item.text or "").strip().splitlines() if l.strip()]
            rarity = "normal"
            if lines and lines[0].startswith("Rarity:"):
                rarity = lines[0].split(":", 1)[1].strip().lower()
            item_map[iid] = {
                "name": lines[1] if len(lines) > 1 else "",
                "base_name": lines[2] if len(lines) > 2 else "",
                "rarity": rarity,
            }
        active_id = ie.get("activeItemSet", "1")
        item_set = next(
            (e for e in ie.findall("ItemSet") if e.get("id") == active_id),
            ie.findall("ItemSet")[0] if ie.findall("ItemSet") else ie,
        )
        for slot in item_set.findall("Slot"):
            sn, sid = slot.get("name", ""), slot.get("itemId", "0")
            if sid == "0" or any(x in sn for x in ("Abyssal", "Swap", "Socket", "Graft")):
                continue
            if sn and sid in item_map:
                d = item_map[sid]
                items[sn] = {"name": d["name"], "base_name": d["base_name"],
                             "slot": sn, "rarity": d["rarity"], "mods": []}

    return {
        "character_name": _attr(b, "characterName"),
        "class": _attr(b, "className", "Witch"),
        "ascendancy": _attr(b, "ascendClassName", ""),
        "level": int(_attr(b, "level", "1")),
        "bandit": _attr(b, "bandit", "None"),
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


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    raw = open(POB_CODE_FILE, encoding="utf-8").read().strip()
    xml = decode_pob(raw)
    build_data = parse_pob(xml)

    print(f"Build: {build_data['class']}/{build_data['ascendancy']} lv{build_data['level']}")
    print(f"Items: {len(build_data['items'])}  Skills: {len(build_data['skill_groups'])}")

    session_id = _find_llm_session_id()
    print(f"Session ID (LLM group): {session_id}")

    body = {
        "build": build_data,
        "build_code": raw,
        "league": "Keepers",
        "max_candidates_per_slot": 3,
        "session_id": session_id,
    }

    print(f"\nPOST {BASE_URL}/api/v1/recommendations …")
    try:
        result = http_post(f"{BASE_URL}/api/v1/recommendations", body)
    except urllib.error.URLError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    recs = result.get("recommendations", [])
    sims = result.get("simulation_count", 0)
    elapsed = result.get("elapsed_seconds", 0)
    print(f"\n  simulations={sims}  recs={len(recs)}  elapsed={elapsed:.1f}s")

    if not recs:
        print("  No recommendations returned.")
        return

    print("\n" + "=" * 72)
    for i, rec in enumerate(recs, 1):
        slot = rec.get("slot", "?")
        item = rec.get("suggested_item", "?")
        score = rec.get("score", 0)
        source = rec.get("explanation_source", "unknown")
        explanation = rec.get("explanation", "")
        deltas = rec.get("deltas", {})
        price = rec.get("price_divine")

        src_tag = f"[{source.upper()}]"
        print(f"\n{i}. {src_tag} {slot}: {item}")
        print(f"   score={score:.3f}  dps={deltas.get('dps', 0):+,.0f}  "
              f"life={deltas.get('life', 0):+,.0f}  "
              f"price={'—' if price is None else f'{price:.1f}div'}")
        print(f"   Explanation: {explanation}")

    # LLM usage stats
    print("\n" + "=" * 72)
    try:
        usage = http_get(f"{BASE_URL}/api/v1/admin/llm-usage")
        print("\nLLM usage stats:")
        for k, v in usage.items():
            print(f"  {k}: {v}")
    except Exception as exc:
        print(f"\n(Could not fetch LLM usage: {exc})")


main()
