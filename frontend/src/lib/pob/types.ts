// ---- Primitive types ----

export type ItemRarity = 'normal' | 'magic' | 'rare' | 'unique';

export type ItemSlot =
  | 'Helmet'
  | 'Body Armour'
  | 'Gloves'
  | 'Boots'
  | 'Weapon'
  | 'Weapon 2'
  | 'Shield'
  | 'Amulet'
  | 'Ring'
  | 'Ring 2'
  | 'Belt'
  | 'Flask'
  | 'Jewel';

export type Bandit = 'None' | 'Oak' | 'Kraityn' | 'Alira';

// ---- Core domain types ----

export interface BuildStats {
  life: number;
  energyShield: number;
  dps: number; // CombinedDPS stat from PoB
  fireRes: number;
  coldRes: number;
  lightningRes: number;
  chaosRes: number;
}

export interface AttrReq {
  str: number;
  dex: number;
  int: number;
}

export interface Item {
  id: number; // <Item id="N"> from XML
  name: string; // unique/rare name; '' for normal/magic
  baseName: string;
  slot: ItemSlot;
  rarity: ItemRarity;
  levelReq: number;
  attrReq: AttrReq;
  sockets: string; // e.g. "R-R-G G-B" (- = linked, space = unlinked)
  mods: string[]; // raw mod lines from item text
  corrupted: boolean;
}

export interface Gem {
  skillId: string; // e.g. "Metadata/Items/Gems/SkillGemFireball"
  nameSpec: string; // display name, e.g. "Fireball"
  level: number;
  quality: number;
  enabled: boolean;
  isSupport: boolean;
}

export interface SkillGroup {
  slot: string; // e.g. "Weapon 1", "Body Armour"
  label: string; // optional user label from PoB
  enabled: boolean;
  gems: Gem[];
  mainActiveGemIndex: number; // index into gems[] of the primary active skill
}

export interface BuildData {
  characterName: string;
  class: string;
  ascendancy: string;
  level: number;
  bandit: Bandit;
  mainSkill: string; // display name of the primary active skill
  stats: BuildStats;
  passiveTree: number[]; // allocated node IDs
  items: Map<ItemSlot, Item>;
  skillGroups: SkillGroup[];
}

// ---- Parser errors ----

export class PobDecodeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PobDecodeError';
  }
}

export class PobParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PobParseError';
  }
}
