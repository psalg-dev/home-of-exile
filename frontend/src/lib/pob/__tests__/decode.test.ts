/**
 * Unit tests for decodePobCode().
 *
 * Tests the round-trip decode of a known PoB code fixture, ensuring that
 * URL-safe base64 normalisation and zlib decompression work correctly.
 */

import { deflate } from 'pako';
import { decodePobCode } from '../decode';
import { PobDecodeError } from '../types';

/**
 * Helper: create a valid PoB code from an XML string (mirrors what PoB exports).
 * Uses pako.deflate() + standard base64 encoding (converted to URL-safe).
 */
function encodeAsPobCode(xml: string): string {
  const encoded = new TextEncoder().encode(xml);
  const compressed = deflate(encoded);
  // Convert Uint8Array to base64 (browser-safe, no Node Buffer dependency)
  const binary = Array.from(compressed).map(b => String.fromCharCode(b)).join('');
  const base64 = btoa(binary);
  // Convert to URL-safe base64 (PoB format)
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

const FIXTURE_XML = `<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding>
  <Build level="100" className="Witch" ascendClassName="Necromancer" characterName="TestChar" bandit="None" mainSocketGroup="1">
    <PlayerStat stat="Life" value="4500"/>
    <PlayerStat stat="EnergyShield" value="1200"/>
    <PlayerStat stat="CombinedDPS" value="999999"/>
    <PlayerStat stat="FireResist" value="75"/>
    <PlayerStat stat="ColdResist" value="75"/>
    <PlayerStat stat="LightningResist" value="75"/>
    <PlayerStat stat="ChaosResist" value="-60"/>
  </Build>
  <Skills>
    <Skill slot="Body Armour" enabled="true" label="">
      <Gem nameSpec="Raise Zombie" skillId="Metadata/Items/Gems/SkillGemRaiseZombie" level="20" quality="20" enabled="true"/>
      <Gem nameSpec="Minion Damage Support" skillId="Metadata/Items/Gems/SupportGemMinionDamage" level="20" quality="20" enabled="true"/>
    </Skill>
  </Skills>
  <Tree>
    <Spec nodes="10001 10002 10003"/>
  </Tree>
  <Items>
    <Slot name="Helmet" itemId="1"/>
    <Item id="1">
Rarity: Rare
Death Crown
Hubris Circlet
--------
LevelReq: 69
--------
+50 to maximum Energy Shield
+30 to maximum Life
--------
Corrupted
</Item>
  </Items>
</PathOfBuilding>`;

describe('decodePobCode', () => {
  it('round-trips a known PoB v2.40 style fixture without error', () => {
    const code = encodeAsPobCode(FIXTURE_XML);
    const result = decodePobCode(code);
    expect(result).toContain('<PathOfBuilding>');
    expect(result).toContain('className="Witch"');
  });

  it('handles URL-safe base64 characters (- and _)', () => {
    // Create code with + and / then convert to URL-safe form to test normalisation
    const code = encodeAsPobCode(FIXTURE_XML);
    // Ensure no + or / present (it's URL-safe encoded), meaning normalisation was needed
    expect(code).not.toMatch(/\+/);
    const result = decodePobCode(code);
    expect(result).toContain('PathOfBuilding');
  });

  it('throws PobDecodeError for empty string', () => {
    expect(() => decodePobCode('')).toThrow(PobDecodeError);
    expect(() => decodePobCode('')).toThrow('Invalid PoB code: code is empty');
  });

  it('throws PobDecodeError for whitespace-only string', () => {
    expect(() => decodePobCode('   ')).toThrow(PobDecodeError);
  });

  it('throws PobDecodeError for invalid base64', () => {
    expect(() => decodePobCode('not!!valid!!base64!!')).toThrow(PobDecodeError);
  });

  it('throws PobDecodeError for valid base64 that is not zlib-compressed data', () => {
    // "hello world" in base64 - valid b64 but not zlib
    expect(() => decodePobCode('aGVsbG8gd29ybGQ=')).toThrow(PobDecodeError);
  });
});
