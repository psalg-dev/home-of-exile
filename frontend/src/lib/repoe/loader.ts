/**
 * Loaders for RePoE static data files bundled via Vite's JSON import.
 *
 * For the frontend we load data from the /data/repoe/ directory by fetching
 * the JSON files at runtime. The files are available under /data/repoe/
 * via the Vite dev server (served from the project root).
 */

import type { RePoEBaseItem, RePoEGem, RePoEMod } from './types';

const DATA_BASE = '/data/repoe';

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${path}: ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

/**
 * Load all base items from the RePoE data file.
 *
 * @returns Record mapping item ID → RePoEBaseItem
 */
export async function loadBaseItems(): Promise<Record<string, RePoEBaseItem>> {
  return fetchJson<Record<string, RePoEBaseItem>>(
    `${DATA_BASE}/base_items.json`,
  );
}

/**
 * Load all gem data from the RePoE data file.
 *
 * @returns Record mapping gem ID → RePoEGem
 */
export async function loadGems(): Promise<Record<string, RePoEGem>> {
  return fetchJson<Record<string, RePoEGem>>(`${DATA_BASE}/gems.json`);
}

/**
 * Load all mod data from the RePoE data file.
 *
 * @returns Record mapping mod ID → RePoEMod
 */
export async function loadMods(): Promise<Record<string, RePoEMod>> {
  return fetchJson<Record<string, RePoEMod>>(`${DATA_BASE}/mods.json`);
}
