import { readFileSync } from 'fs';
import { resolve } from 'path';
import { MAX_POB_LENGTH, validatePobInput } from '../validate';

describe('validatePobInput', () => {
  it('accepts a valid real PoB export fixture', () => {
    const fixturePath = resolve(__dirname, '../../../../../examples/keepers/phantasm-summoner/pob.txt');
    const raw = readFileSync(fixturePath, 'utf-8');
    expect(validatePobInput(raw)).toBeNull();
  });

  it('accepts standard base64 with plus/slash and equals padding', () => {
    const standardBase64 = 'QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=';
    expect(validatePobInput(standardBase64)).toBeNull();
  });

  it('accepts valid code with internal whitespace/newlines', () => {
    const base = 'QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=';
    const withWhitespace = `${base.slice(0, 12)}\n  ${base.slice(12)}`;
    expect(validatePobInput(withWhitespace)).toBeNull();
  });

  it('rejects empty input', () => {
    expect(validatePobInput('   ')).toBe('Please paste a PoB export code.');
  });

  it('rejects suspiciously short input', () => {
    expect(validatePobInput('abc123')).toBe('This looks too short to be a valid PoB code.');
  });

  it('rejects input over max length', () => {
    const tooLong = 'A'.repeat(MAX_POB_LENGTH + 1);
    expect(validatePobInput(tooLong)).toBe(
      'This code is too long. Make sure you copied the PoB export code and nothing else.',
    );
  });

  it('rejects non-base64 characters', () => {
    expect(validatePobInput('@@@@@@@@@@@@@@@@@@@@')).toBe(
      'This does not look like a valid PoB code. Make sure you copied the base64 export from Path of Building.',
    );
  });
});
