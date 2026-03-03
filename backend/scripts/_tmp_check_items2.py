import base64, zlib, xml.etree.ElementTree as ET

pob = open('C:/dev/workspace/home-of-exile/examples/standard/cws-chief.txt').read().strip()
raw_bytes = base64.b64decode(pob.replace('-','+').replace('_','/') + '==')
xml_str = zlib.decompress(raw_bytes).decode('utf-8')
root = ET.fromstring(xml_str)
items_elem = root.find('Items')
active_id = items_elem.get('activeItemSet', '1')
item_set = next((c for c in items_elem if c.tag == 'ItemSet' and c.get('id') == active_id), None)
container = item_set or items_elem

item_map = {}
for item in items_elem.findall('Item'):
    iid = item.get('id', '')
    raw = item.text or ''
    lines = [l.strip() for l in raw.strip().split('\n') if l.strip()]
    name = lines[1] if len(lines) > 1 else ''
    base = lines[2] if len(lines) > 2 else ''
    rarity = lines[0].split(':')[1].strip().lower() if lines and lines[0].startswith('Rarity:') else 'normal'
    item_map[iid] = {'name': name, 'base': base, 'rarity': rarity}

print("=== Equipped Items ===")
for slot in container.findall('Slot'):
    iid = slot.get('itemId', '0')
    sname = slot.get('name', '')
    skip_tags = ['Abyssal', 'Swap', 'Socket', 'Graft', 'Flask']
    if iid != '0' and not any(x in sname for x in skip_tags):
        item = item_map.get(iid, {})
        display = item.get('name') or item.get('base', '?')
        base = item.get('base', '')
        print(f"  {sname:20s}: [{item.get('rarity',''):8}] {display} ({base})")

# Check CombinedDPS
print("\n=== DPS stats ===")
build_elem = root.find('Build')
for ps in build_elem.findall('PlayerStat'):
    name = ps.get('stat', '')
    val = ps.get('value', '')
    if any(x in name.lower() for x in ['dps', 'combined', 'full', 'total']):
        print(f"  {name}: {val}")
