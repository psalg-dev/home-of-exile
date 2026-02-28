"""Check detailed items structure in phantasm summoner XML."""
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

# Check ActiveItemSet and ItemSet elements too
print("== Items element attributes ==")
if items_elem is not None:
    print(dict(items_elem.attrib))
    
# List all child tag names
if items_elem is not None:
    child_tags = {}
    for child in items_elem:
        child_tags[child.tag] = child_tags.get(child.tag, 0) + 1
    print(f"Child tags: {child_tags}")
    
    # Look at first few items
    for item in list(items_elem)[:3]:
        print(f"\n  <{item.tag}> attribs={dict(item.attrib)}")
        if item.tag == 'Item':
            lines = (item.text or '').strip().split('\n')[:4]
            for line in lines:
                print(f"    {line}")
