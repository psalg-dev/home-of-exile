import { inflate } from 'pako';
import { PobDecodeError } from './types';

/**
 * Decode a Path of Building export code into raw XML.
 *
 * PoB codes are URL-safe base64-encoded, zlib-compressed XML.
 * Steps:
 *   1. Strip any markdown code-block fencing (```plaintext ... ``` or ``` ... ```)
 *   2. Strip all internal whitespace (newlines, spaces, tabs) from the code
 *   3. Normalise URL-safe base64 (replace `-`→`+`, `_`→`/`, pad with `=`)
 *   4. Decode with atob() → Uint8Array → pako.inflate() → UTF-8 string
 *
 * @param code - The PoB export code string (URL-safe base64), optionally
 *   wrapped in a markdown code fence block.
 * @returns Decompressed XML string
 * @throws {PobDecodeError} If the code is empty, not valid base64, or
 *   cannot be decompressed
 */
export function decodePobCode(code: string): string {
  // Step 0: strip markdown code fences, e.g. ```plaintext\n...\n```
  // Handles optional language identifier after the opening fence.
  const fenceMatch = code.match(/^`{3}[a-z]*\s*([\s\S]*?)\s*`{3}$/);
  const extracted = fenceMatch ? fenceMatch[1] : code;

  // Remove all internal whitespace (newlines, spaces, tabs that users may
  // inadvertently include when copying a PoB code from a text file).
  const trimmed = extracted.replace(/\s+/g, '');

  if (!trimmed) {
    throw new PobDecodeError('Invalid PoB code: code is empty');
  }

  // Step 1: normalise URL-safe base64 to standard base64
  const standard = trimmed
    .replace(/-/g, '+')
    .replace(/_/g, '/');

  // Add padding if needed
  const padded = standard + '='.repeat((4 - (standard.length % 4)) % 4);

  let binaryString: string;
  try {
    binaryString = atob(padded);
  } catch {
    throw new PobDecodeError('Invalid PoB code: not valid base64');
  }

  // Step 2: Convert binary string to Uint8Array
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }

  // Step 3: Inflate (decompress zlib stream)
  let decompressed: Uint8Array;
  try {
    decompressed = inflate(bytes);
  } catch {
    throw new PobDecodeError('Invalid PoB code: decompression failed');
  }

  // Step 4: Decode UTF-8 bytes to string
  try {
    return new TextDecoder('utf-8').decode(decompressed);
  } catch {
    throw new PobDecodeError('Invalid PoB code: UTF-8 decode failed');
  }
}
