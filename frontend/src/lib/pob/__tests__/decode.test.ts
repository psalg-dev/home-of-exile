/**
 * Unit tests for decodePobCode().
 *
 * Tests the round-trip decode of a known PoB code fixture, ensuring that
 * URL-safe base64 normalisation and zlib decompression work correctly.
 * Also tests stripping of markdown code-fence wrappers and internal whitespace.
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';
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

describe('decodePobCode – markdown fence stripping', () => {
  it('decodes a code wrapped in ```plaintext ... ``` fences', () => {
    const code = encodeAsPobCode(FIXTURE_XML);
    const fenced = `\`\`\`plaintext\n${code}\n\`\`\``;
    const result = decodePobCode(fenced);
    expect(result).toContain('<PathOfBuilding>');
  });

  it('decodes a code wrapped in plain ``` ... ``` fences (no language tag)', () => {
    const code = encodeAsPobCode(FIXTURE_XML);
    const fenced = `\`\`\`\n${code}\n\`\`\``;
    const result = decodePobCode(fenced);
    expect(result).toContain('<PathOfBuilding>');
  });

  it('decodes a code that contains internal newlines/whitespace', () => {
    const code = encodeAsPobCode(FIXTURE_XML);
    // Introduce random line breaks inside the code (as if copied from a text editor)
    const withBreaks = code.slice(0, 80) + '\n' + code.slice(80, 160) + '\n  ' + code.slice(160);
    const result = decodePobCode(withBreaks);
    expect(result).toContain('<PathOfBuilding>');
  });

  it('throws PobDecodeError for a fenced block containing only whitespace', () => {
    expect(() => decodePobCode('```plaintext\n   \n```')).toThrow(PobDecodeError);
    expect(() => decodePobCode('```plaintext\n   \n```')).toThrow('Invalid PoB code: code is empty');
  });
});

describe('decodePobCode – cws-dd real fixture', () => {
  /**
   * Reads the cws-dd pob.txt fixture from the examples directory and verifies
   * that decodePobCode can handle it end-to-end including the markdown fence.
   */
  it('decodes the cws-dd pob.txt keeper fixture into valid PoB XML', () => {
    // Resolve path relative to the repository root (five levels above __tests__)
    const fixturePath = resolve(__dirname, '../../../../../examples/keepers/cws-dd/pob.txt');
    const raw = readFileSync(fixturePath, 'utf-8');
    const result = decodePobCode(raw);
    expect(result).toContain('<PathOfBuilding>');
    expect(result).toContain('</PathOfBuilding>');
  });
});
