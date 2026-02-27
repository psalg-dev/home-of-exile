/**
 * LoadingOverlay — full-screen overlay shown during recommendation analysis.
 *
 * Displays staged progress messages and a cancel button.
 * Shows a timeout warning after 20 seconds.
 */
import { useEffect, useState } from 'react';

const STAGES = [
  { label: 'Parsing your build…', delay: 0 },
  { label: 'Fetching live prices…', delay: 1500 },
  { label: 'Analyzing upgrade candidates…', delay: 3500 },
  { label: 'Running simulations…', delay: 6000 },
] as const;

const TIMEOUT_MS = 20_000;

interface LoadingOverlayProps {
  /** Called when the user clicks the cancel button. */
  onCancel: () => void;
}

export default function LoadingOverlay({ onCancel }: LoadingOverlayProps) {
  const [stageIndex, setStageIndex] = useState(0);
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];

    STAGES.forEach((stage, i) => {
      if (stage.delay > 0) {
        timers.push(setTimeout(() => setStageIndex(i), stage.delay));
      }
    });

    timers.push(
      setTimeout(() => setTimedOut(true), TIMEOUT_MS),
    );

    return () => timers.forEach(t => clearTimeout(t));
  }, []);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Analyzing build"
      className="fixed inset-0 z-50 bg-gray-950/95 backdrop-blur-sm flex flex-col items-center justify-center gap-8 p-6"
    >
      {/* Spinner */}
      <svg
        className="animate-spin h-12 w-12 text-amber-400"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>

      {/* Stage message */}
      <div className="text-center space-y-2">
        <p className="text-lg font-medium text-gray-100">
          {STAGES[stageIndex].label}
        </p>

        {/* Skeleton cards */}
        <div className="mt-6 space-y-3 w-full max-w-md mx-auto" aria-hidden="true">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="bg-gray-800 rounded-lg p-4 space-y-2 animate-pulse">
              <div className="h-4 bg-gray-700 rounded w-2/3" />
              <div className="h-3 bg-gray-700 rounded w-1/2" />
            </div>
          ))}
        </div>
      </div>

      {/* Timeout warning */}
      {timedOut && (
        <p
          role="alert"
          className="text-sm text-yellow-400 text-center max-w-sm"
        >
          Analysis is taking longer than expected. This may happen with very complex builds.
        </p>
      )}

      {/* Cancel button */}
      <button
        type="button"
        onClick={onCancel}
        className="text-sm text-gray-400 hover:text-gray-200 underline transition-colors"
      >
        Cancel
      </button>
    </div>
  );
}
