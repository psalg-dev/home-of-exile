/**
 * Unit tests for parsePobXml().
 *
 * Tests that the parser correctly extracts all BuildData fields from
 * a known PoB XML fixture.
 */

import { parsePobXml } from '../parse';
import { PobParseError } from '../types';

// ---------------------------------------------------------------------------
// Fixture XML - representative PoB 2.40 export format
// ---------------------------------------------------------------------------

const FIXTURE_XML = `<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding>
  <Build level="95" className="Duelist" ascendClassName="Slayer" characterName="MySlayer" bandit="Oak" mainSocketGroup="1">
    <PlayerStat stat="Life" value="5432.5"/>
    <PlayerStat stat="EnergyShield" value="0"/>
    <PlayerStat stat="CombinedDPS" value="1234567.89"/>
    <PlayerStat stat="FireResist" value="75"/>
    <PlayerStat stat="ColdResist" value="72"/>
    <PlayerStat stat="LightningResist" value="75"/>
    <PlayerStat stat="ChaosResist" value="-60"/>
  </Build>
  <Skills>
    <Skill slot="Weapon 1" enabled="true" label="Main Skill">
      <Gem nameSpec="Cyclone" skillId="Metadata/Items/Gems/SkillGemCyclone" level="21" quality="20" enabled="true"/>
      <Gem nameSpec="Melee Physical Damage Support" skillId="Metadata/Items/Gems/SupportGemMeleePhysicalDamage" level="20" quality="20" enabled="true"/>
      <Gem nameSpec="Infused Channelling Support" skillId="Metadata/Items/Gems/SupportGemInfusedChannelling" level="20" quality="0" enabled="true"/>
    </Skill>
    <Skill slot="Body Armour" enabled="true" label="Auras">
      <Gem nameSpec="Pride" skillId="Metadata/Items/Gems/SkillGemPride" level="20" quality="20" enabled="true"/>
      <Gem nameSpec="War Banner" skillId="Metadata/Items/Gems/SkillGemWarBanner" level="20" quality="20" enabled="true"/>
    </Skill>
  </Skills>
  <Tree>
    <Spec nodes="10001 10002 10003 20001 20002"/>
  </Tree>
  <Items>
    <Slot name="Helmet" itemId="1"/>
    <Slot name="Body Armour" itemId="2"/>
    <Slot name="Gloves" itemId="3"/>
    <Item id="1">
Rarity: Rare
Death Mask
Eternal Burgonet
--------
LevelReq: 67
--------
Requires 138 Str
--------
+92 to maximum Life
+52 to maximum Energy Shield
15% increased maximum Life
--------
</Item>
    <Item id="2">
Rarity: Unique
Dendrobate
Sentinel Jacket
--------
LevelReq: 59
--------
+30 to Dexterity
--------
Has 6 Sockets
5 to 15 Added Chaos Damage per Poison on Enemy against you
Socketed Gems are Supported by Level 18 Viper Strike Support
Socketed Non-Channelling Skills have -7 to Total Mana Cost
--------
Corrupted
</Item>
    <Item id="3">
Rarity: Normal
Spiked Gloves
--------
LevelReq: 50
--------
+12 to Strength
--------
</Item>
  </Items>
</PathOfBuilding>`;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('parsePobXml', () => {
  describe('character fields', () => {
    it('extracts class correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.class).toBe('Duelist');
    });

    it('extracts ascendancy correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.ascendancy).toBe('Slayer');
    });

    it('extracts level as integer', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.level).toBe(95);
    });

    it('extracts characterName', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.characterName).toBe('MySlayer');
    });

    it('extracts bandit', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.bandit).toBe('Oak');
    });
  });

  describe('stats', () => {
    it('extracts life correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.stats.life).toBeCloseTo(5432.5);
    });

    it('extracts energyShield correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.stats.energyShield).toBe(0);
    });

    it('extracts CombinedDPS correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.stats.dps).toBeCloseTo(1234567.89);
    });

    it('extracts fireRes correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.stats.fireRes).toBe(75);
    });

    it('extracts coldRes correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.stats.coldRes).toBe(72);
    });

    it('extracts lightningRes correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.stats.lightningRes).toBe(75);
    });

    it('extracts chaosRes (negative) correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.stats.chaosRes).toBe(-60);
    });
  });

  describe('mainSkill', () => {
    it('resolves mainSkill from mainSocketGroup index', () => {
      const data = parsePobXml(FIXTURE_XML);
      // mainSocketGroup="1" → skillGroups[0] → first active gem is Cyclone
      expect(data.mainSkill).toBe('Cyclone');
    });
  });

  describe('passiveTree', () => {
    it('parses passive node IDs as number array', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.passiveTree).toEqual([10001, 10002, 10003, 20001, 20002]);
    });
  });

  describe('items', () => {
    it('parses helmet item with mods', () => {
      const data = parsePobXml(FIXTURE_XML);
      const helmet = data.items.get('Helmet');
      expect(helmet).toBeDefined();
      expect(helmet!.baseName).toBe('Eternal Burgonet');
      expect(helmet!.rarity).toBe('rare');
      expect(helmet!.levelReq).toBe(67);
      expect(helmet!.mods.length).toBeGreaterThan(0);
    });

    it('returns non-empty mods array for rare/unique items', () => {
      const data = parsePobXml(FIXTURE_XML);
      const helmet = data.items.get('Helmet');
      const body = data.items.get('Body Armour');
      expect(helmet!.mods).not.toHaveLength(0);
      expect(body!.mods).not.toHaveLength(0);
    });

    it('parses unique item name and baseName separately', () => {
      const data = parsePobXml(FIXTURE_XML);
      const body = data.items.get('Body Armour');
      expect(body).toBeDefined();
      expect(body!.name).toBe('Dendrobate');
      expect(body!.baseName).toBe('Sentinel Jacket');
      expect(body!.rarity).toBe('unique');
    });

    it('marks corrupted items correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      const body = data.items.get('Body Armour');
      expect(body!.corrupted).toBe(true);
    });

    it('parses normal item without name', () => {
      const data = parsePobXml(FIXTURE_XML);
      const gloves = data.items.get('Gloves');
      expect(gloves).toBeDefined();
      expect(gloves!.rarity).toBe('normal');
    });
  });

  describe('skillGroups', () => {
    it('returns correct number of skill groups', () => {
      const data = parsePobXml(FIXTURE_XML);
      expect(data.skillGroups).toHaveLength(2);
    });

    it('returns gems with correct nameSpec', () => {
      const data = parsePobXml(FIXTURE_XML);
      const mainGroup = data.skillGroups[0];
      expect(mainGroup.gems[0].nameSpec).toBe('Cyclone');
    });

    it('identifies support gems correctly', () => {
      const data = parsePobXml(FIXTURE_XML);
      const mainGroup = data.skillGroups[0];
      // Cyclone is not a support; others contain "Support" in nameSpec
      expect(mainGroup.gems[0].isSupport).toBe(false);
      expect(mainGroup.gems[1].isSupport).toBe(true);
    });

    it('parses gem level and quality', () => {
      const data = parsePobXml(FIXTURE_XML);
      const cyclone = data.skillGroups[0].gems[0];
      expect(cyclone.level).toBe(21);
      expect(cyclone.quality).toBe(20);
    });
  });

  describe('error handling', () => {
    it('throws PobParseError for non-PathOfBuilding XML', () => {
      expect(() => parsePobXml('<NotPoB/>')).toThrow(PobParseError);
      expect(() => parsePobXml('<NotPoB/>')).toThrow(
        'Unsupported PoB version — please export from v2.35+',
      );
    });

    it('throws PobParseError for non-XML plain text', () => {
      // fast-xml-parser is lenient but the result won't have PathOfBuilding root
      expect(() => parsePobXml('not xml at all')).toThrow(PobParseError);
    });
  });
});
