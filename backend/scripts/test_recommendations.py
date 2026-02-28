"""
Test the full recommendations endpoint end-to-end with the phantasm summoner build.
Constructs a minimal BuildData from the pob.txt and posts to /api/v1/recommendations.
"""
import json
import sys
import base64
import zlib
import re
import urllib.request
import xml.etree.ElementTree as ET


POB_CODE_FILE = r"c:\dev\workspace\home-of-exile\examples\keepers\phantasm-summoner\pob.txt"
BASE_URL = "http://localhost:8000"


def decode_pob_code(code: str) -> str:
    code = code.strip()
    code = code.replace('-', '+').replace('_', '/')
    code += '=' * ((4 - len(code) % 4) % 4)
    return zlib.decompress(base64.b64decode(code)).decode('utf-8')


def post_json(url: str, data: dict) -> dict:
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url, data=body, method='POST',
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode('utf-8'))


def parse_pob_xml_to_build_data(xml: str) -> dict:
    """Parse PoB XML into the backend's BuildData format."""
    root = ET.fromstring(xml)
    build_elem = root.find('Build')

    def attr(elem, name, default=''):
        return elem.get(name, default) if elem is not None else default

    # Stats from PlayerStat
    stats = {}
    for ps in build_elem.findall('PlayerStat') if build_elem is not None else []:
        k = ps.get('stat', '')
        v = ps.get('value', '0')
        stats[k] = v

    # Parse skills
    skills_elem = root.find('Skills')
    skill_groups = []
    if skills_elem is not None:
        # Handle both flat Skill and SkillSet>Skill
        skill_elems = []
        skill_sets = skills_elem.findall('SkillSet')
        if skill_sets:
            for ss in skill_sets:
                skill_elems.extend(ss.findall('Skill'))
        else:
            skill_elems = skills_elem.findall('Skill')

        for skill in skill_elems:
            gems = []
            for gem in skill.findall('Gem'):
                gems.append({
                    'name_spec': gem.get('nameSpec', ''),
                    'skill_id': gem.get('skillId', ''),
                    'level': int(gem.get('level', '1')),
                    'quality': int(gem.get('quality', '0')),
                    'enabled': gem.get('enabled', 'true').lower() == 'true',
                    'is_support': 'Support' in gem.get('nameSpec', ''),
                })
            skill_groups.append({
                'slot': skill.get('slot', ''),
                'label': skill.get('label', ''),
                'enabled': skill.get('enabled', 'true').lower() == 'true',
                'gems': gems,
                'main_active_gem_index': 0,
            })

    # Parse items — handle PoB v2 format:
    # <Items activeItemSet="1">
    #   <Item id="X">...</Item>
    #   <ItemSet id="1">
    #     <Slot name="Helmet" itemId="X"/>
    #   </ItemSet>
    # </Items>
    items_elem = root.find('Items')
    items = {}
    if items_elem is not None:
        # Build item_id → item data map
        item_map = {}
        for item in items_elem.findall('Item'):
            item_id = item.get('id', '')
            raw = item.text or ''
            lines = [l.strip() for l in raw.strip().split('\n') if l.strip()]
            name = lines[1] if len(lines) > 1 else ''
            base = lines[2] if len(lines) > 2 else ''
            rarity = 'normal'
            if lines and lines[0].startswith('Rarity:'):
                rarity = lines[0].split(':', 1)[1].strip().lower()
            if item_id:
                item_map[item_id] = {'name': name, 'base_name': base, 'rarity': rarity}

        # Find active ItemSet
        active_set_id = items_elem.get('activeItemSet', '1')
        item_set = None
        for elem in items_elem.findall('ItemSet'):
            if elem.get('id') == active_set_id:
                item_set = elem
                break
        if item_set is None and items_elem.findall('ItemSet'):
            item_set = items_elem.findall('ItemSet')[0]

        # Map slot names from Slot elements
        slot_container = item_set if item_set is not None else items_elem
        for slot_elem in slot_container.findall('Slot'):
            slot_name = slot_elem.get('name', '')
            item_id = slot_elem.get('itemId', '0')
            # Skip abyssal sockets, swap slots, empty slots, jewel sockets
            if item_id == '0':
                continue
            if any(x in slot_name for x in ['Abyssal', 'Swap', 'Socket', 'Graft']):
                continue
            if slot_name and item_id and item_id in item_map:
                i = item_map[item_id]
                items[slot_name] = {
                    'name': i['name'],
                    'base_name': i['base_name'],
                    'slot': slot_name,
                    'rarity': i['rarity'],
                    'mods': [],
                }

    return {
        'character_name': attr(build_elem, 'characterName'),
        'class': attr(build_elem, 'className', 'Witch'),
        'ascendancy': attr(build_elem, 'ascendClassName', ''),
        'level': int(attr(build_elem, 'level', '1')),
        'bandit': attr(build_elem, 'bandit', 'None'),
        'main_skill': '',
        'stats': {
            'life': int(float(stats.get('Life', '0'))),
            'energy_shield': int(float(stats.get('EnergyShield', '0'))),
            'dps': float(stats.get('CombinedDPS', stats.get('TotalDPS', '0'))),
            'fire_res': int(float(stats.get('FireResist', '0'))),
            'cold_res': int(float(stats.get('ColdResist', '0'))),
            'lightning_res': int(float(stats.get('LightningResist', '0'))),
            'chaos_res': int(float(stats.get('ChaosResist', '0'))),
        },
        'items': items,
        'skill_groups': skill_groups,
        'passive_tree': [],
    }


def main():
    with open(POB_CODE_FILE, encoding='utf-8') as f:
        raw = f.read().strip()

    xml = decode_pob_code(raw)
    print(f"XML decoded, length={len(xml)}")

    build_data = parse_pob_xml_to_build_data(xml)
    print(f"BuildData: class={build_data['class']}, asc={build_data['ascendancy']}, "
          f"level={build_data['level']}, items={len(build_data['items'])}")

    request_body = {
        'build': build_data,
        'build_code': raw,
        'league': 'Keepers',
        'max_candidates_per_slot': 3,
    }

    print(f"\nPosting to {BASE_URL}/api/v1/recommendations...")
    try:
        result = post_json(f"{BASE_URL}/api/v1/recommendations", request_body)
    except Exception as e:
        print(f"ERROR: {e}")
        return

    print(f"\n=== Recommendations Response ===")
    print(f"  simulation_count: {result.get('simulation_count', 0)}")
    print(f"  critical_issues: {len(result.get('critical_issues', []))}")
    print(f"  recommendations: {len(result.get('recommendations', []))}")
    print(f"  elapsed_seconds: {result.get('elapsed_seconds', 0)}")

    if result.get('critical_issues'):
        print("\n  Critical Issues:")
        for issue in result['critical_issues']:
            print(f"    [{issue.get('severity')}] {issue.get('description')}")

    if result.get('recommendations'):
        print("\n  Top Recommendations:")
        for i, rec in enumerate(result['recommendations'], 1):
            deltas = rec.get('deltas', {})
            print(f"  {i}. [{rec.get('category')}] {rec.get('suggested_item', '?')} "
                  f"({rec.get('slot', '?')}) "
                  f"score={rec.get('score', 0):.3f} "
                  f"dps_delta={deltas.get('dps', 0):+,.0f} "
                  f"life_delta={deltas.get('life', 0):+,.0f}")
    else:
        print("  No recommendations returned.")


main()
