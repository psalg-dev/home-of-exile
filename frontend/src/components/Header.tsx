/**
 * Header — app-wide navigation bar with logo, nav links, and league selector.
 */
import { NavLink } from 'react-router-dom';
import { useLeague, type League } from '@/contexts/league-context';

const LEAGUE_OPTIONS: { value: League; label: string }[] = [
  { value: 'Keepers', label: 'Keepers of the Flame (Current)' },
  { value: 'Settlers', label: 'Settlers (Previous)' },
  { value: 'Standard', label: 'Standard' },
];

export default function Header() {
  const { league, setLeague } = useLeague();

  return (
    <header className="sticky top-0 z-50 bg-gray-900/95 border-b border-gray-800 backdrop-blur-sm">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
        {/* Logo + app name */}
        <NavLink
          to="/"
          className="flex items-center gap-2 shrink-0 group"
          aria-label="Home of Exile – Home"
        >
          <span className="text-2xl leading-none select-none" aria-hidden="true">⚔️</span>
          <span className="text-lg font-bold text-amber-400 group-hover:text-amber-300 transition-colors">
            Home of Exile
          </span>
        </NavLink>

        {/* Nav + league selector */}
        <div className="flex items-center gap-4">
          <nav className="hidden sm:flex items-center gap-1" aria-label="Main navigation">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-700 text-gray-100'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800'
                }`
              }
            >
              Home
            </NavLink>
            <NavLink
              to="/resources"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-700 text-gray-100'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800'
                }`
              }
            >
              Resources
            </NavLink>
          </nav>

          {/* League selector */}
          <div className="flex items-center gap-2">
            <label htmlFor="league-select" className="text-xs text-gray-500 hidden sm:block whitespace-nowrap">
              League:
            </label>
            <select
              id="league-select"
              value={league}
              onChange={e => setLeague(e.target.value as League)}
              aria-label="Select league"
              className="bg-gray-800 border border-gray-700 text-gray-200 text-xs rounded px-2 py-1.5
                         focus:outline-none focus:border-amber-500 cursor-pointer"
            >
              {LEAGUE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </header>
  );
}
