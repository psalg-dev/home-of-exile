/**
 * Session ID management.
 *
 * A UUID v4 is generated once per browser session and persisted in
 * sessionStorage.  The same ID is sent with all feedback and trade-click
 * events so the backend can deduplicate votes per recommendation per session.
 */

const SESSION_KEY = 'hoe_session_id';

/**
 * Generate a UUID v4 string using the browser's crypto API.
 *
 * @returns A random UUID v4 string.
 */
function generateUuid(): string {
  return crypto.randomUUID();
}

/**
 * Return the current session ID, creating and persisting one if needed.
 *
 * The value is stored in `sessionStorage` so it survives page navigation
 * within the same tab but resets when the tab is closed.
 *
 * @returns Session ID string (UUID v4).
 */
export function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = generateUuid();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}
