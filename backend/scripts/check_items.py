"""Check items structure in phantasm summoner XML."""
import base64
import zlib
import xml.etree.ElementTree as ET

with open(r'c:\dev\workspace\home-of-exile\examples\keepers\phantasm-summoner\pob.txt') as f:
    raw = f.read().strip()

code = raw.replace('-', '+').replace('_', '/')
code += '=' * ((4 - len(code) % 4) % 4)
xml = zlib.decompress(base64.b64decode(code)).decode()

root = ET.fromstring(xml)

# Check Items section
items_elem = root.find('Items')
if items_elem is not None:
    slots = items_elem.findall('Slot')
    items = items_elem.findall('Item')
    print(f'Items section: {len(items)} items, {len(slots)} slots')
    for s in slots[:5]:
        print(f'  Slot: name={s.get("name")} itemId={s.get("itemId")}')
    for i in items[:3]:
        lines = (i.text or '').strip().split('\n')
        print(f'  Item id={i.get("id")}: {lines[0] if lines else "(empty)"}')
else:
    print('No Items section found')

# Check Skills section
skills_elem = root.find('Skills')
if skills_elem is not None:
    skill_sets = skills_elem.findall('SkillSet')
    flat_skills = skills_elem.findall('Skill')
    print(f'Skills: {len(skill_sets)} skill sets, {len(flat_skills)} flat skills')
