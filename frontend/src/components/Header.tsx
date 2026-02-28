/**
 * Header — app-wide navigation bar with logo, nav links, league selector,
 * and a trade-session settings button.
 */
import { useState, useRef, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { useLeague, type League } from '@/contexts/league-context';
import { usePoeSession } from '@/contexts/poe-session-context';

const LEAGUE_OPTIONS: { value: League; label: string }[] = [
  { value: 'Keepers', label: 'Keepers of the Flame (Current)' },
  { value: 'Settlers', label: 'Settlers (Previous)' },
  { value: 'Standard', label: 'Standard' },
];

export default function Header() {
  const { league, setLeague } = useLeague();
  const { poeSessionId, setPoeSessionId } = usePoeSession();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draft, setDraft] = useState(poeSessionId);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside.
  useEffect(() => {
    function onOutside(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
      }
    }
    if (settingsOpen) document.addEventListener('mousedown', onOutside);
    return () => document.removeEventListener('mousedown', onOutside);
  }, [settingsOpen]);

  function handleOpen() {
    setDraft(poeSessionId);
    setSettingsOpen(v => !v);
  }

  function handleSave() {
    setPoeSessionId(draft);
    setSettingsOpen(false);
  }

  function handleClear() {
    setDraft('');
    setPoeSessionId('');
    setSettingsOpen(false);
  }

  const hasSession = Boolean(poeSessionId);

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

        {/* Nav + controls */}
        <div className="flex items-center gap-3">
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

          {/* Trade session settings */}
          <div className="relative" ref={panelRef}>
            <button
              type="button"
              onClick={handleOpen}
              aria-label="Trade session settings"
              title={hasSession ? 'Trade session active' : 'Set POESESSID for live trade prices'}
              className={`w-8 h-8 flex items-center justify-center rounded transition-colors ${
                hasSession
                  ? 'text-green-400 hover:bg-green-900/30'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
              }`}
            >
              <span className="text-base" aria-hidden="true">⚿️</span>
              {hasSession && (
                <span
                  className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-green-400"
                  aria-hidden="true"
                />
              )}
            </button>

            {settingsOpen && (
              <div
                className="absolute right-0 top-10 w-80 bg-gray-900 border border-gray-700 rounded-lg
                           shadow-xl p-4 space-y-3 z-50"
                role="dialog"
                aria-label="Trade session settings"
              >
                <div>
                  <h3 className="text-sm font-semibold text-gray-100 mb-0.5">Trade Session ID</h3>
                  <p className="text-xs text-gray-500 leading-relaxed">
                    Paste your <code className="text-amber-400">POESESSID</code> cookie to enable
                    live trade price lookups. Find it in your browser’s DevTools while logged in
                    to <span className="text-gray-300">pathofexile.com</span>.
                  </p>
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="poesessid-input" className="text-xs text-gray-400">
                    POESESSID
                  </label>
                  <input
                    id="poesessid-input"
                    type="password"
                    value={draft}
                    onChange={e => setDraft(e.target.value)}
                    placeholder="Paste your POESESSID here…"
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-xs rounded
                               px-3 py-2 focus:outline-none focus:border-amber-500 font-mono"
                  />
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleSave}
                    className="flex-1 text-xs bg-amber-600 hover:bg-amber-500 text-gray-950
                               font-semibold px-3 py-1.5 rounded transition-colors"
                  >
                    Save
                  </button>
                  {hasSession && (
                    <button
                      type="button"
                      onClick={handleClear}
                      className="text-xs bg-gray-700 hover:bg-red-800/60 text-gray-300
                                 px-3 py-1.5 rounded transition-colors"
                    >
                      Clear
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setSettingsOpen(false)}
                    className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-300
                               px-3 py-1.5 rounded transition-colors"
                  >
                    Cancel
                  </button>
                </div>

                <p className="text-xs text-gray-600">
                  Your session ID is stored only in your browser’s local storage and is sent
                  exclusively to this app’s backend trade proxy.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

