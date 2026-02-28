/**
 * PoeSessionContext — persists the player's POESESSID cookie value for
 * authenticated PoE Trade API requests.
 *
 * The value is stored in localStorage so it survives page reloads.
 * It is never sent anywhere except the backend trade proxy endpoint.
 */
import { createContext, useContext, useState, type ReactNode } from 'react';

const STORAGE_KEY = 'poe_session_id';

interface PoeSessionContextValue {
  /** Raw POESESSID value, or empty string if not set. */
  poeSessionId: string;
  setPoeSessionId: (id: string) => void;
}

const PoeSessionContext = createContext<PoeSessionContextValue | null>(null);

export function PoeSessionProvider({ children }: { children: ReactNode }) {
  const [poeSessionId, setPoeSessionIdState] = useState<string>(
    () => localStorage.getItem(STORAGE_KEY) ?? '',
  );

  function setPoeSessionId(id: string) {
    const trimmed = id.trim();
    setPoeSessionIdState(trimmed);
    if (trimmed) {
      localStorage.setItem(STORAGE_KEY, trimmed);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }

  return (
    <PoeSessionContext.Provider value={{ poeSessionId, setPoeSessionId }}>
      {children}
    </PoeSessionContext.Provider>
  );
}

export function usePoeSession(): PoeSessionContextValue {
  const ctx = useContext(PoeSessionContext);
  if (!ctx) throw new Error('usePoeSession must be used inside PoeSessionProvider');
  return ctx;
}
