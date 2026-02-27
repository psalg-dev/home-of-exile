/**
 * TypeScript types mirroring the RePoE JSON data format.
 * Reference: https://github.com/brather1ng/RePoE
 */

export interface RePoEBaseItem {
  name: string;
  item_class: string;
  requirements: {
    level?: number;
    str?: number;
    dex?: number;
    int?: number;
  };
  implicit_mods: string[];
  tags: string[];
}

export interface RePoEGem {
  base_item: { display_name: string; release_state: string } | null;
  tags: string[];
  is_support: boolean;
}

export interface RePoEMod {
  name: string;
  generation_type: 'prefix' | 'suffix' | 'corrupted' | string;
  groups: string[];
  stats: { id: string; min: number; max: number }[];
  spawn_weights: { tag: string; weight: number }[];
}
