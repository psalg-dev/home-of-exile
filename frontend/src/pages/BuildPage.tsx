import { useEffect, useReducer, useState } from 'react';
import { Link } from 'react-router-dom';
import type { BuildData, Item } from '@/lib/pob/types';
import type { Recommendation, CriticalIssue, RecommendResponse } from '@/lib/recommendations/types';
import { fetchRecommendations } from '@/lib/recommendations/api';

// ---------------------------------------------------------------------------
// Recommendation state machine — avoids calling setState synchronously
// inside useEffect (react-hooks/set-state-in-effect).
// ---------------------------------------------------------------------------

type RecState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: RecommendResponse }
  | { status: 'error'; error: string };

type RecAction =
  | { type: 'success'; data: RecommendResponse }
  | { type: 'error'; error: string };

function recReducer(_state: RecState, action: RecAction): RecState {
  switch (action.type) {
    case 'success': return { status: 'success', data: action.data };
    case 'error': return { status: 'error', error: action.error };
  }
}

/**
 * BuildPage — displays the parsed build, critical issues, and ranked upgrade
 * recommendations from the M4 simulation engine.
 */
export default function BuildPage() {
  const [buildData] = useState<BuildData | null>(() => {
    const raw = sessionStorage.getItem('buildData');
    if (!raw) return null;
    try {
      return JSON.parse(raw) as BuildData;
    } catch {
      return null;
    }
  });

  const [itemsObj] = useState<Record<string, Item> | undefined>(() => {
    const raw = sessionStorage.getItem('buildData');
    if (!raw) return undefined;
    try {
      const parsed = JSON.parse(raw) as { items?: Record<string, Item> };
      return parsed.items;
    } catch {
      return undefined;
    }
  });

  /**
   * Initialise to 'loading' immediately if a pobCode is available —
   * this avoids calling setState synchronously inside the effect
   * (which would violate react-hooks/set-state-in-effect).
   */
  const [recState, dispatchRec] = useReducer(
    recReducer,
    undefined,
    (): RecState => (sessionStorage.getItem('pobCode') ? { status: 'loading' } : { status: 'idle' }),
  );

  useEffect(() => {
    if (!buildData) return;

    const pobCode = sessionStorage.getItem('pobCode') ?? '';
    if (!pobCode) return;

    fetchRecommendations(buildData, pobCode, itemsObj)
      .then(data => dispatchRec({ type: 'success', data }))
      .catch((err: unknown) => {
        const error = err instanceof Error ? err.message : 'Unknown error';
        dispatchRec({ type: 'error', error });
      });
  }, [buildData, itemsObj]);

  // Derived values for JSX
  const isLoadingRec = recState.status === 'loading';
  const recError = recState.status === 'error' ? recState.error : null;
  const recResponse = recState.status === 'success' ? recState.data : null;

  if (!buildData) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center justify-center p-6">
        <p className="text-gray-400 mb-4">No build data found.</p>
        <Link to="/" className="text-amber-400 hover:text-amber-300 underline">
          ← Import a build
        </Link>
      </div>
    );
  }

  const { characterName, class: cls, ascendancy, level, bandit, mainSkill, stats } = buildData;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold text-amber-400">
            {characterName || `${cls} Build`}
          </h1>
          <Link to="/" className="text-gray-400 hover:text-gray-200 text-sm">
            ← Import another build
          </Link>
        </div>

        {/* Character info */}
        <div className="bg-gray-800 rounded-lg p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
          <InfoItem label="Class" value={cls || '—'} />
          <InfoItem label="Ascendancy" value={ascendancy || '—'} />
          <InfoItem label="Level" value={level ? String(level) : '—'} />
          <InfoItem label="Bandit" value={bandit || 'None'} />
        </div>

        {/* Main skill */}
        {mainSkill && (
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Main Skill</div>
            <div className="text-amber-400 font-semibold text-lg">{mainSkill}</div>
          </div>
        )}

        {/* Stats */}
        <div className="bg-gray-800 rounded-lg p-4">
          <h2 className="text-sm text-gray-500 uppercase tracking-wide mb-3">Stats</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatItem label="Life" value={stats.life} color="text-red-400" />
            <StatItem label="Energy Shield" value={stats.energyShield} color="text-blue-400" />
            <StatItem label="DPS" value={stats.dps} color="text-amber-400" />
            <StatItem label="Fire Res" value={stats.fireRes} suffix="%" color="text-orange-400" />
            <StatItem label="Cold Res" value={stats.coldRes} suffix="%" color="text-cyan-400" />
            <StatItem label="Lightning Res" value={stats.lightningRes} suffix="%" color="text-yellow-400" />
            <StatItem label="Chaos Res" value={stats.chaosRes} suffix="%" color="text-purple-400" />
          </div>
        </div>

        {/* Critical issues */}
        {recResponse && recResponse.critical_issues.length > 0 && (
          <CriticalIssuesPanel issues={recResponse.critical_issues} />
        )}

        {/* Recommendations section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-gray-100">Upgrade Recommendations</h2>
            {recResponse && (
              <span className="text-xs text-gray-500">
                {recResponse.simulation_count} simulations · {recResponse.elapsed_seconds.toFixed(1)}s
              </span>
            )}
          </div>

          {isLoadingRec && (
            <div
              role="status"
              aria-label="Loading recommendations"
              className="bg-gray-800 rounded-lg p-6 flex items-center justify-center gap-3 text-gray-400"
            >
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Simulating upgrade candidates…
            </div>
          )}

          {!isLoadingRec && recError && (
            <div
              role="alert"
              className="bg-red-950 border border-red-700 rounded-lg p-4 text-red-300 text-sm"
            >
              <span className="font-semibold">Recommendations unavailable: </span>{recError}
            </div>
          )}

          {!isLoadingRec && !recError && recResponse && recResponse.recommendations.length === 0 && (
            <div className="bg-gray-800 rounded-lg p-6 text-center text-gray-500">
              No upgrade recommendations found for this build.
            </div>
          )}

          {!isLoadingRec && recResponse && recResponse.recommendations.length > 0 && (
            <div className="space-y-3" data-testid="recommendations-list">
              {recResponse.recommendations.map(rec => (
                <RecommendationCard key={rec.rank} rec={rec} />
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface InfoItemProps {
  label: string;
  value: string;
}

function InfoItem({ label, value }: InfoItemProps) {
  return (
    <div>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-gray-100 font-medium">{value}</div>
    </div>
  );
}

interface StatItemProps {
  label: string;
  value: number;
  color?: string;
  suffix?: string;
}

function StatItem({ label, value, color = 'text-gray-100', suffix = '' }: StatItemProps) {
  return (
    <div>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`font-semibold text-lg ${color}`}>
        {value.toLocaleString()}{suffix}
      </div>
    </div>
  );
}

interface CriticalIssuesPanelProps {
  issues: CriticalIssue[];
}

function CriticalIssuesPanel({ issues }: CriticalIssuesPanelProps) {
  return (
    <div className="space-y-2" aria-label="Critical issues" data-testid="critical-issues">
      {issues.map((issue, idx) => (
        <div
          key={idx}
          role="alert"
          data-testid={`critical-issue-${issue.category}`}
          className={`rounded-lg px-4 py-3 border text-sm flex items-start gap-3 ${
            issue.severity === 'critical'
              ? 'bg-red-950 border-red-700 text-red-200'
              : 'bg-yellow-950 border-yellow-700 text-yellow-200'
          }`}
        >
          <span className="text-base leading-none mt-0.5">
            {issue.severity === 'critical' ? '⚠️' : '⚡'}
          </span>
          <div>
            <span className="font-semibold capitalize">
              {issue.category.replace(/_/g, ' ')}:{' '}
            </span>
            {issue.description}
            {issue.currentValue !== issue.targetValue && (
              <span className="ml-2 text-xs opacity-70">
                ({issue.currentValue} / {issue.targetValue})
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

const CATEGORY_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  critical_fix:    { bg: 'bg-red-900/40 border-red-700',    text: 'text-red-300',    label: 'Critical Fix' },
  power_upgrade:   { bg: 'bg-amber-900/40 border-amber-700', text: 'text-amber-300', label: 'Power Upgrade' },
  defense_upgrade: { bg: 'bg-blue-900/40 border-blue-700',  text: 'text-blue-300',  label: 'Defense Upgrade' },
  efficiency:      { bg: 'bg-green-900/40 border-green-700', text: 'text-green-300', label: 'Efficiency' },
  qol:             { bg: 'bg-gray-700/40 border-gray-600',  text: 'text-gray-300',  label: 'QoL' },
};

interface RecommendationCardProps {
  rec: Recommendation;
}

function RecommendationCard({ rec }: RecommendationCardProps) {
  const style = CATEGORY_STYLES[rec.category] ?? CATEGORY_STYLES.qol;

  const dpsDelta = rec.deltas['dps'] ?? rec.deltas['total_dps'] ?? null;
  const ehpDelta = rec.deltas['ehp'] ?? rec.deltas['effective_hp'] ?? null;

  return (
    <div
      data-testid={`recommendation-${rec.rank}`}
      className={`rounded-lg border p-4 space-y-3 ${style.bg}`}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-2xl font-bold text-gray-500">#{rec.rank}</span>
          <span className={`text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border ${style.text} ${style.bg}`}>
            {style.label}
          </span>
          <span className="text-xs text-gray-500 uppercase">{rec.slot}</span>
        </div>
        {rec.priceDivine !== null && (
          <span className="text-sm font-semibold text-amber-400 whitespace-nowrap">
            ~{rec.priceDivine.toFixed(1)} div
          </span>
        )}
      </div>

      {/* Item change */}
      <div className="flex items-center gap-2 text-sm flex-wrap">
        <span className="text-gray-400">{rec.currentItem}</span>
        <span className="text-gray-600">→</span>
        <span className="text-gray-100 font-medium">{rec.suggestedItem}</span>
      </div>

      {/* Delta badges */}
      <div className="flex flex-wrap gap-2">
        {dpsDelta !== null && dpsDelta !== 0 && (
          <DeltaBadge label="DPS" value={dpsDelta} formatFn={formatDps} />
        )}
        {ehpDelta !== null && ehpDelta !== 0 && (
          <DeltaBadge label="EHP" value={ehpDelta} formatFn={Math.round} />
        )}
        {rec.efficiencyScore !== null && (
          <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">
            eff {rec.efficiencyScore.toFixed(2)}
          </span>
        )}
      </div>

      {/* Explanation */}
      <p className="text-sm text-gray-300">{rec.explanation}</p>

      {/* Action links */}
      <div className="flex flex-wrap gap-2">
        {rec.tradeUrl && (
          <a
            href={rec.tradeUrl}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`trade-link-${rec.rank}`}
            className="text-xs bg-amber-600 hover:bg-amber-500 text-gray-950 font-semibold
                       px-3 py-1.5 rounded transition-colors"
          >
            Trade →
          </a>
        )}
        {rec.ninjaUrl && (
          <a
            href={rec.ninjaUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-200
                       px-3 py-1.5 rounded transition-colors"
          >
            poe.ninja
          </a>
        )}
        {rec.wikiUrl && (
          <a
            href={rec.wikiUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-200
                       px-3 py-1.5 rounded transition-colors"
          >
            Wiki
          </a>
        )}
      </div>
    </div>
  );
}

interface DeltaBadgeProps {
  label: string;
  value: number;
  formatFn?: (v: number) => number | string;
}

function DeltaBadge({ label, value, formatFn = v => v }: DeltaBadgeProps) {
  const isPositive = value > 0;
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded font-medium ${
        isPositive ? 'bg-green-900/60 text-green-300' : 'bg-red-900/60 text-red-300'
      }`}
    >
      {label} {isPositive ? '+' : ''}{formatFn(value)}
    </span>
  );
}

function formatDps(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(Math.round(value));
}
