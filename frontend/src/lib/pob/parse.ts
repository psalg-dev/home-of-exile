import { XMLParser } from 'fast-xml-parser';
import type {
  Bandit,
  BuildData,
  BuildStats,
  Gem,
  Item,
  ItemRarity,
  ItemSlot,
  SkillGroup,
} from './types';
import { PobParseError } from './types';

/**
 * Parse raw PoB XML into a structured BuildData object.
 *
 * @param xml - Raw decompressed PoB XML string
 * @returns Parsed BuildData
 * @throws {PobParseError} If the XML does not have a PathOfBuilding root
 */
export function parsePobXml(xml: string): BuildData {
  const parser = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: '@_',
    isArray: (name) =>
      ['Skill', 'Gem', 'Item', 'Slot', 'PlayerStat', 'Socket', 'SkillSet'].includes(name),
  });

  let doc: Record<string, unknown>;
  try {
    doc = parser.parse(xml) as Record<string, unknown>;
  } catch {
    throw new PobParseError(
      'Unsupported PoB version — please export from v2.35+',
    );
  }

  const pob = doc['PathOfBuilding'] as Record<string, unknown> | undefined;
  if (!pob) {
    throw new PobParseError(
      'Unsupported PoB version — please export from v2.35+',
    );
  }

  const build = (pob['Build'] ?? {}) as Record<string, unknown>;

  // Parse PlayerStat array
  const playerStats = getArray<Record<string, unknown>>(build, 'PlayerStat');
  const statMap = new Map<string, number>();
  for (const stat of playerStats) {
    const key = getString(stat, '@_stat');
    const val = parseFloat(getString(stat, '@_value') || '0');
    if (key) statMap.set(key, isNaN(val) ? 0 : val);
  }

  const stats: BuildStats = {
    life: statMap.get('Life') ?? 0,
    energyShield: statMap.get('EnergyShield') ?? 0,
    dps: statMap.get('CombinedDPS') ?? 0,
    fireRes: statMap.get('FireResist') ?? 0,
    coldRes: statMap.get('ColdResist') ?? 0,
    lightningRes: statMap.get('LightningResist') ?? 0,
    chaosRes: statMap.get('ChaosResist') ?? 0,
  };

  // Parse skills — support both flat Skills>Skill and Skills>SkillSet>Skill layouts
  const skillsSection = (pob['Skills'] ?? {}) as Record<string, unknown>;
  const skillGroups = parseSkillGroups(skillsSection);

  // Resolve mainSkill from mainSocketGroup index
  const mainSocketGroupRaw = getString(build, '@_mainSocketGroup');
  const mainSocketGroupIdx = parseInt(mainSocketGroupRaw || '1', 10) - 1; // 1-based in XML
  let mainSkill = '';
  if (skillGroups[mainSocketGroupIdx]) {
    const group = skillGroups[mainSocketGroupIdx];
    const firstActiveGem = group.gems.find((g) => !g.isSupport && g.enabled);
    mainSkill = firstActiveGem?.nameSpec ?? group.gems[0]?.nameSpec ?? '';
  }

  // Parse passive tree
  const treeSection = (pob['Tree'] ?? {}) as Record<string, unknown>;
  const spec = (treeSection['Spec'] ?? {}) as Record<string, unknown>;
  const nodesRaw = getString(spec, 'nodes') || getString(spec, '@_nodes') || '';
  const passiveTree = nodesRaw
    .split(/[\s,]+/)
    .filter(Boolean)
    .map((n) => parseInt(n, 10))
    .filter((n) => !isNaN(n));

  // Parse items
  const itemsSection = (pob['Items'] ?? {}) as Record<string, unknown>;
  const items = parseItems(itemsSection);

  return {
    characterName: getString(build, '@_characterName'),
    class: getString(build, '@_className'),
    ascendancy: getString(build, '@_ascendClassName'),
    level: parseInt(getString(build, '@_level') || '0', 10) || 0,
    bandit: (getString(build, '@_bandit') || 'None') as Bandit,
    mainSkill,
    stats,
    passiveTree,
    items,
    skillGroups,
  };
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function getString(obj: Record<string, unknown>, key: string): string {
  const val = obj[key];
  if (val === undefined || val === null) return '';
  return String(val);
}

function getArray<T>(obj: Record<string, unknown>, key: string): T[] {
  const val = obj[key];
  if (!val) return [];
  if (Array.isArray(val)) return val as T[];
  return [val] as T[];
}

function parseSkillGroups(skillsSection: Record<string, unknown>): SkillGroup[] {
  // Newer PoB exports wrap skills in a SkillSet element:
  //   <Skills activeSkillSet="1"><SkillSet id="1"><Skill>...</Skill></SkillSet></Skills>
  // Older exports place Skill directly under Skills.
  let skillSource: Record<string, unknown> = skillsSection;
  const skillSets = getArray<Record<string, unknown>>(skillsSection, 'SkillSet');
  if (skillSets.length > 0) {
    const activeId = getString(skillsSection, '@_activeSkillSet') || '1';
    const activeSet = skillSets.find((s) => getString(s, '@_id') === activeId) ?? skillSets[0];
    skillSource = activeSet;
  }

  const skillNodes = getArray<Record<string, unknown>>(skillSource, 'Skill');
  return skillNodes.map((skill): SkillGroup => {
    const gemNodes = getArray<Record<string, unknown>>(skill, 'Gem');
    const gems = gemNodes.map((gem): Gem => ({
      skillId: getString(gem, '@_skillId'),
      nameSpec: getString(gem, '@_nameSpec'),
      level: parseInt(getString(gem, '@_level') || '1', 10) || 1,
      quality: parseInt(getString(gem, '@_quality') || '0', 10) || 0,
      enabled: getString(gem, '@_enabled') !== 'false',
      isSupport: getString(gem, '@_gemId').toLowerCase().includes('support') ||
        getString(gem, '@_nameSpec').endsWith('Support') ||
        getString(gem, '@_support') === 'true',
    }));

    const mainActiveGemIndex = gems.findIndex((g) => !g.isSupport && g.enabled);

    return {
      slot: getString(skill, '@_slot'),
      label: getString(skill, '@_label'),
      enabled: getString(skill, '@_enabled') !== 'false',
      gems,
      mainActiveGemIndex: mainActiveGemIndex >= 0 ? mainActiveGemIndex : 0,
    };
  });
}

function parseItems(itemsSection: Record<string, unknown>): Map<ItemSlot, Item> {
  const itemNodes = getArray<Record<string, unknown>>(itemsSection, 'Item');
  const slotNodes = getArray<Record<string, unknown>>(itemsSection, 'Slot');

  // Build itemId → slot map
  const idToSlot = new Map<string, ItemSlot>();
  for (const slot of slotNodes) {
    const name = getString(slot, '@_name');
    const itemId = getString(slot, '@_itemId');
    if (name && itemId) {
      idToSlot.set(itemId, name as ItemSlot);
    }
  }

  const result = new Map<ItemSlot, Item>();

  for (const itemNode of itemNodes) {
    const id = parseInt(getString(itemNode, '@_id') || '0', 10);
    const rawText: string =
      typeof itemNode['#text'] === 'string'
        ? (itemNode['#text'] as string)
        : typeof itemNode === 'string'
          ? (itemNode as unknown as string)
          : '';

    const slot = idToSlot.get(String(id));
    if (!slot) continue; // skip unequipped items

    const parsed = parseItemText(rawText, id, slot);
    result.set(slot, parsed);
  }

  return result;
}

function parseItemText(text: string, id: number, slot: ItemSlot): Item {
  const lines = text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);

  let rarity: ItemRarity = 'normal';
  let name = '';
  let baseName = '';
  let levelReq = 0;
  let attrStr = 0;
  let attrDex = 0;
  let attrInt = 0;
  let sockets = '';
  let corrupted = false;
  const mods: string[] = [];

  // Track how many -------- separators we've seen to determine parsing phase:
  // Phase 0 (separatorCount === 0): header lines → rarity, name, baseName
  // Phase 1+: stat lines, then mod lines
  let separatorCount = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line === '--------') {
      separatorCount++;
      continue;
    }

    if (line.startsWith('Rarity:')) {
      const rarityStr = line.replace('Rarity:', '').trim().toLowerCase();
      rarity = rarityStr as ItemRarity;
      continue;
    }

    // Phase 0: header lines before the first separator
    if (separatorCount === 0) {
      // Rarity already handled above; remaining lines are name/baseName
      if (rarity === 'unique' || rarity === 'rare') {
        if (!name) {
          name = line;
          continue;
        }
        if (!baseName) {
          baseName = line;
          continue;
        }
      } else {
        if (!baseName) {
          baseName = line;
          continue;
        }
      }
      continue;
    }

    // Phase 1+: stat and mod lines
    if (line.startsWith('LevelReq:')) {
      levelReq = parseInt(line.replace('LevelReq:', '').trim(), 10) || 0;
      continue;
    }

    if (line.startsWith('Requires')) {
      continue;
    }

    const strMatch = line.match(/^(\d+) Str$/);
    if (strMatch) {
      attrStr = parseInt(strMatch[1], 10);
      continue;
    }

    const dexMatch = line.match(/^(\d+) Dex$/);
    if (dexMatch) {
      attrDex = parseInt(dexMatch[1], 10);
      continue;
    }

    const intMatch = line.match(/^(\d+) Int$/);
    if (intMatch) {
      attrInt = parseInt(intMatch[1], 10);
      continue;
    }

    if (line.startsWith('Sockets:')) {
      const socketsRaw = line.replace('Sockets:', '').trim();
      sockets = socketsRaw;
      continue;
    }

    if (line === 'Corrupted') {
      corrupted = true;
      continue;
    }

    // Any non-stat line after the first separator is treated as a mod
    // (this catches implicit and explicit mods)
    if (separatorCount >= 1) {
      mods.push(line);
    }
  }

  return {
    id,
    name,
    baseName,
    slot,
    rarity,
    levelReq,
    attrReq: { str: attrStr, dex: attrDex, int: attrInt },
    sockets,
    mods,
    corrupted,
  };
}
