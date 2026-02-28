"""Examine the PoB XML to understand build structure."""
import re

xml = open('/tmp/phantasm_build.xml').read()

tv = re.search(r'treeVersion="([^"]+)"', xml)
print('Tree version:', tv.group(1) if tv else 'not found')

# Find main active skill setting
main = re.search(r'mainActiveSkill="([^"]+)"', xml)
print('Main active skill index:', main.group(1) if main else 'not found')

# Show socket groups
for m in re.finditer(r'<Skill([^>]+)>', xml[:5000]):
    print('Skill group attrs:', m.group(1).strip()[:120])

# Show first few gems
for m in re.finditer(r'<Gem([^>]+)>', xml[:3000]):
    print('Gem:', m.group(1).strip()[:100])

# Find the active skill list
selected = re.search(r'activeSkillSet="([^"]+)"', xml)
print('Active skill set:', selected.group(1) if selected else 'not found')

# Check the build class
char_class = re.search(r'className="([^"]+)"', xml)
print('Class:', char_class.group(1) if char_class else 'not found')
ascend = re.search(r'ascendClassName="([^"]+)"', xml)
print('Ascend:', ascend.group(1) if ascend else 'not found')
