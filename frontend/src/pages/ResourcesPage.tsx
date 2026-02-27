/**
 * ResourcesPage — /resources
 *
 * Curated links to PoE tools. Fandom wiki links are explicitly excluded.
 */

interface ResourceLink {
  label: string;
  url: string;
  description: string;
}

interface ResourceCategory {
  title: string;
  links: ResourceLink[];
}

const CATEGORIES: ResourceCategory[] = [
  {
    title: 'Build Tools',
    links: [
      {
        label: 'Path of Building Community Fork',
        url: 'https://github.com/PathOfBuildingCommunity/PathOfBuilding',
        description: 'The go-to offline build planner for Path of Exile. Required for generating PoB codes used by this app.',
      },
      {
        label: 'pob.cool',
        url: 'https://pob.cool',
        description: 'Browser-based PoB viewer — share and preview builds without installing software.',
      },
    ],
  },
  {
    title: 'Databases',
    links: [
      {
        label: 'poewiki.net',
        url: 'https://www.poewiki.net',
        description: 'The official community wiki. Comprehensive item, passive, and mechanic documentation.',
      },
      {
        label: 'poedb.tw',
        url: 'https://poedb.tw',
        description: 'Data-mining database for PoE. Excellent for item mods, boss data, and atlas info.',
      },
    ],
  },
  {
    title: 'Economy',
    links: [
      {
        label: 'poe.ninja',
        url: 'https://poe.ninja',
        description: 'Real-time pricing data for currencies, items, and builds. Used by this app for price estimates.',
      },
    ],
  },
  {
    title: 'Trading',
    links: [
      {
        label: 'Official Trade Site',
        url: 'https://www.pathofexile.com/trade',
        description: "Grinding Gear Games' official trade search engine. Used for all trade links in recommendations.",
      },
      {
        label: 'Awakened PoE Trade',
        url: 'https://github.com/SnosMe/awakened-poe-trade',
        description: 'In-game overlay for instant price checking (Ctrl+D). The fastest way to price items.',
      },
    ],
  },
  {
    title: 'Data',
    links: [
      {
        label: 'RePoE',
        url: 'https://github.com/bryansteiner/RePoE',
        description: 'Machine-readable PoE game data (items, mods, gems). Used to power the candidate pipeline in this app.',
      },
    ],
  },
];

export default function ResourcesPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10 space-y-10">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold text-amber-400">Resource Hub</h1>
          <p className="text-gray-400">
            Curated tools and databases for Path of Exile theorycrafting and trading.
            All links open in a new tab.
          </p>
        </div>

        {CATEGORIES.map(cat => (
          <section key={cat.title} aria-labelledby={`cat-${cat.title}`}>
            <h2
              id={`cat-${cat.title}`}
              className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-3 border-b border-gray-800 pb-2"
            >
              {cat.title}
            </h2>
            <ul className="space-y-3">
              {cat.links.map(link => (
                <li key={link.url}>
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block bg-gray-800/60 hover:bg-gray-800 border border-gray-700/50 hover:border-gray-600 rounded-lg px-4 py-3 transition-colors group"
                    aria-label={`${link.label} – opens in new tab`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-gray-100 group-hover:text-amber-300 transition-colors">
                        {link.label}
                      </span>
                      <span className="text-gray-600 text-xs shrink-0" aria-hidden="true">↗</span>
                    </div>
                    <p className="text-sm text-gray-400 mt-0.5">{link.description}</p>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
