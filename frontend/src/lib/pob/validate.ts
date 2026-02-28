/** Reasonable upper bound — anything longer is suspicious. */
export const MAX_POB_LENGTH = 20_000;

/**
 * Validate the raw PoB input before decoding.
 *
 * Accepts URL-safe and standard base64 variants, optional '=' padding,
 * and copied whitespace/newlines inside the code.
 *
 * @param code - Raw user input from the PoB textarea.
 * @returns Error message when invalid, or null when acceptable.
 */
export function validatePobInput(code: string): string | null {
  const trimmed = code.trim();
  const compact = trimmed.replace(/\s+/g, '');

  if (!trimmed) return 'Please paste a PoB export code.';
  if (compact.length < 20) return 'This looks too short to be a valid PoB code.';
  if (compact.length > MAX_POB_LENGTH) {
    return 'This code is too long. Make sure you copied the PoB export code and nothing else.';
  }

  if (!/^[A-Za-z0-9+/_-]+=*$/.test(compact)) {
    return 'This does not look like a valid PoB code. Make sure you copied the base64 export from Path of Building.';
  }

  return null;
}
