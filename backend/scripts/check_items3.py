"""Check ItemSet structure in phantasm summoner XML."""
import base64
import zlib
import xml.etree.ElementTree as ET

with open(r'c:\dev\workspace\home-of-exile\examples\keepers\phantasm-summoner\pob.txt') as f:
    raw = f.read().strip()

code = raw.replace('-', '+').replace('_', '/')
code += '=' * ((4 - len(code) % 4) % 4)
xml_str = zlib.decompress(base64.b64decode(code)).decode()

root = ET.fromstring(xml_str)
items_elem = root.find('Items')

# Find ItemSet
item_set = items_elem.find('ItemSet') if items_elem is not None else None
if item_set is not None:
    print(f"ItemSet attribs: {dict(item_set.attrib)}")
    for child in item_set:
        print(f"  <{child.tag}> attribs={dict(child.attrib)}")
else:
    print("No ItemSet found")

# Also dump the raw XML around Items section for direct inspection
start_idx = xml_str.find('<Items')
end_idx = xml_str.find('</Items>') + len('</Items>')
items_xml = xml_str[start_idx:end_idx]
print("\n== First 2000 chars of Items XML ==")
print(items_xml[:2000])
