/**
 * Price data returned by the poe.ninja API (via our backend proxy).
 */
export interface PoeNinjaPrice {
  name: string;
  chaosValue: number;
  divineValue: number;
  listingCount: number;
}
