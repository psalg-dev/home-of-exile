/**
 * LeagueContext — tracks the currently selected PoE league for recommendations.
 *
 * Wrapped around the app root so all pages can read/update the league.
 */
import { createContext, useContext, useState, type ReactNode } from 'react';

export type League = 'Keepers' | 'Settlers' | 'Standard';

interface LeagueContextValue {
  league: League;
  setLeague: (l: League) => void;
}

const LeagueContext = createContext<LeagueContextValue | null>(null);

export function LeagueProvider({ children }: { children: ReactNode }) {
  const [league, setLeague] = useState<League>('Keepers');
  return (
    <LeagueContext.Provider value={{ league, setLeague }}>
      {children}
    </LeagueContext.Provider>
  );
}

export function useLeague(): LeagueContextValue {
  const ctx = useContext(LeagueContext);
  if (!ctx) throw new Error('useLeague must be used inside LeagueProvider');
  return ctx;
}
