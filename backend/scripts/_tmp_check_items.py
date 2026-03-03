import base64, zlib, xml.etree.ElementTree as ET

pob = open('C:/dev/workspace/home-of-exile/examples/standard/cws-chief.txt').read().strip()
std = pob.replace('-','+').replace('_','/')
padded = std + '=' * ((4 - len(std)%4)%4)
raw_bytes = base64.b64decode(padded)
xml_str = zlib.decompress(raw_bytes).decode('utf-8')
root = ET.fromstring(xml_str)
items_elem = root.find('Items')

print('activeItemSet attr:', items_elem.get('activeItemSet'))
print('Direct children of Items (non-Item):')
print([c.tag for c in items_elem if c.tag not in ['Item', 'ModRange']])

# Show first ItemSet
for child in items_elem:
    if child.tag == 'ItemSet':
        print(f'\nItemSet id={child.get("id")}:')
        for slot in child.findall('Slot')[:10]:
            print(f'  <Slot name="{slot.get("name")}" itemId="{slot.get("itemId")}"/>')
        break

# Direct slots under Items
direct_slots = items_elem.findall('Slot')
print(f'\nDirect Slot count under Items (not ItemSet): {len(direct_slots)}')
for s in direct_slots[:5]:
    print(f'  <Slot name="{s.get("name")}" itemId="{s.get("itemId")}"/>')

# Show equipped slots (non-zero itemId in active ItemSet)
print('\nEquipped slots (active ItemSet):')
active_id = items_elem.get('activeItemSet', '1')
item_set = None
for child in items_elem:
    if child.tag == 'ItemSet' and child.get('id') == active_id:
        item_set = child
        break
if item_set is None:
    # Try first ItemSet
    for child in items_elem:
        if child.tag == 'ItemSet':
            item_set = child
            break

container = item_set if item_set is not None else items_elem
for slot in container.findall('Slot'):
    name = slot.get('name','')
    iid = slot.get('itemId','0')
    if iid != '0' and 'Abyssal' not in name and 'Swap' not in name and 'Socket' not in name and 'Graft' not in name:
        print(f'  {name}: itemId={iid}')

# Also list all PlayerStat names
build_elem = root.find('Build')
print('\nPlayerStat DPS-related:')
for ps in build_elem.findall('PlayerStat'):
    name = ps.get('stat','')
    val = ps.get('value','')
    if any(x in name.lower() for x in ['dps', 'damage']):
        print(f'  {name}: {val}')
