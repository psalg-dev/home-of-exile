/**
 * BuildPage — displays the parsed build summary, critical issues, and ranked
 * upgrade recommendations from the M4 simulation engine.
 *
 * Implements D5.2 (loading/cancel/timeout), D5.3 (build summary), D5.4
 * (recommendation cards), D5.7 (error states) from milestone M5.
 * Implements D6.3 (feedback buttons, trade-click tracking, session ID) from M6.
 */
import { useEffect, useReducer, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { BuildData, Item } from '@/lib/pob/types';
import type { Recommendation, CriticalIssue, RecommendResponse } from '@/lib/recommendations/types';
import { fetchRecommendations } from '@/lib/recommendations/api';
import { useLeague } from '@/contexts/league-context';
import { getSessionId } from '@/lib/session';
import { submitFeedback, trackTradeClick } from '@/lib/feedback/api';
import { fetchTradeListings } from '@/lib/poe-trade/api';
import type { TradeListingsResponse, TradeListing } from '@/lib/poe-trade/types';
import { usePoeSession } from '@/contexts/poe-session-context';

// ---------------------------------------------------------------------------
// Recommendation state machine
// ---------------------------------------------------------------------------

type ErrorKind = 'parse' | 'server' | 'timeout' | 'network' | 'unknown';

type RecState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: RecommendResponse }
  | { status: 'error'; error: string; kind: ErrorKind };

type RecAction =
  | { type: 'success'; data: RecommendResponse }
  | { type: 'error'; error: string; kind: ErrorKind };

function recReducer(_state: RecState, action: RecAction): RecState {
  switch (action.type) {
    case 'success': return { status: 'success', data: action.data };
    case 'error':   return { status: 'error', error: action.error, kind: action.kind };
  }
}

const ANALYSIS_TIMEOUT_MS = 20_000;

// ---------------------------------------------------------------------------
// BuildPage — outer shell: reads session storage, delegates to BuildPageContent
// When league changes, BuildPageContent remounts via key to reset all state.
// ---------------------------------------------------------------------------

export default function BuildPage() {
  const { league } = useLeague();
  const navigate = useNavigate();

  const buildData = useState<BuildData | null>(() => {
    const raw = sessionStorage.getItem('buildData');
    if (!raw) return null;
    try { return JSON.parse(raw) as BuildData; } catch { return null; }
  })[0];

  const itemsObj = useState<Record<string, Item> | undefined>(() => {
    const raw = sessionStorage.getItem('buildData');
    if (!raw) return undefined;
    try {
      const parsed = JSON.parse(raw) as { items?: Record<string, Item> };
      return parsed.items;
    } catch { return undefined; }
  })[0];

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

  return (
    <BuildPageContent
      key={league}
      buildData={buildData}
      itemsObj={itemsObj}
      league={league}
      onImportAnother={() => void navigate('/')}
    />
  );
}

// ---------------------------------------------------------------------------
// BuildPageContent — mounts fresh for every new league (via key prop).
// All analysis state initializes to 'loading' on mount.
// ---------------------------------------------------------------------------

interface BuildPageContentProps {
  buildData: BuildData;
  itemsObj: Record<string, Item> | undefined;
  league: string;
  onImportAnother: () => void;
}

function BuildPageContent({ buildData, itemsObj, league, onImportAnother }: BuildPageContentProps) {
  const [timedOut, setTimedOut] = useState(false);

  // Session ID — generated once per browser session, used for feedback
  const sessionId = getSessionId();

  const [recState, dispatchRec] = useReducer(
    recReducer,
    undefined,
    (): RecState => (sessionStorage.getItem('pobCode') ? { status: 'loading' } : { status: 'idle' }),
  );

  useEffect(() => {
    const pobCode = sessionStorage.getItem('pobCode') ?? '';
    if (!pobCode) return;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => setTimedOut(true), ANALYSIS_TIMEOUT_MS);

    fetchRecommendations(buildData, pobCode, itemsObj, league, sessionId)
      .then(data => {
        if (!controller.signal.aborted) {
          clearTimeout(timeoutId);
          dispatchRec({ type: 'success', data });
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        clearTimeout(timeoutId);
        const msg = err instanceof Error ? err.message : 'Unknown error';
        const isTimeout = msg.toLowerCase().includes('timeout') || msg.includes('signal');
        const isNetwork = msg.toLowerCase().includes('fetch') || msg.toLowerCase().includes('network');
        const kind = isTimeout ? 'timeout' : isNetwork ? 'network' : 'server';
        dispatchRec({ type: 'error', error: msg, kind });
      });

    return () => {
      controller.abort();
      clearTimeout(timeoutId);
    };
    }, [buildData, itemsObj, league, sessionId]); // stable props — remounted per league via key

  const isLoadingRec = recState.status === 'loading';
  const recError = recState.status === 'error' ? recState : null;
  const recResponse = recState.status === 'success' ? recState.data : null;

  const { characterName, class: cls, ascendancy, level, bandit, mainSkill, stats } = buildData;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 pb-10">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-6">

        {/* Header row */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <h1 className="text-2xl sm:text-3xl font-bold text-amber-400">
            {characterName || `${cls} Build`}
          </h1>
          <button
            type="button"
            onClick={onImportAnother}
            className="text-sm text-gray-400 hover:text-gray-200 transition-colors"
          >
            â† Import another build
          </button>
        </div>

        {/* D5.3 Build Summary Card */}
        <BuildSummaryCard
          cls={cls}
          ascendancy={ascendancy}
          level={level}
          bandit={bandit}
          mainSkill={mainSkill}
          stats={stats}
        />

        {/* Critical issues */}
        {recResponse && recResponse.critical_issues.length > 0 && (
          <CriticalIssuesPanel issues={recResponse.critical_issues} />
        )}

        {/* Recommendations section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className="text-xl font-semibold text-gray-100">Upgrade Recommendations</h2>
            <div className="flex items-center gap-3">
              {recResponse && (
                <span className="text-xs text-gray-500">
                  {recResponse.simulation_count} simulations Â· {recResponse.elapsed_seconds.toFixed(1)}s Â·{' '}
                  <span className="text-gray-400">{league}</span>
                </span>
              )}
            </div>
          </div>

          {/* Loading â€” skeleton cards */}
          {isLoadingRec && (
            <div
              role="status"
              aria-label="Loading recommendations"
              className="space-y-3"
            >
              {timedOut && (
                <div role="alert" className="bg-yellow-950 border border-yellow-700 rounded-lg p-3 text-yellow-300 text-sm">
                  Analysis is taking longer than expected. This may happen with very complex builds.
                </div>
              )}
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="bg-gray-800 rounded-lg p-4 space-y-3 animate-pulse" aria-hidden="true">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 bg-gray-700 rounded-full" />
                    <div className="h-4 bg-gray-700 rounded w-1/3" />
                    <div className="ml-auto h-4 bg-gray-700 rounded w-16" />
                  </div>
                  <div className="h-3 bg-gray-700 rounded w-2/3" />
                  <div className="flex gap-2">
                    <div className="h-5 bg-gray-700 rounded-full w-16" />
                    <div className="h-5 bg-gray-700 rounded-full w-20" />
                  </div>
                </div>
              ))}
              <p className="text-center text-sm text-gray-500 animate-pulse">
                Simulating upgrade candidatesâ€¦
              </p>
            </div>
          )}

          {/* Error states */}
          {!isLoadingRec && recError && (
            <ErrorPanel kind={recError.kind} onRetry={() => {
              // Re-trigger by re-navigating (simplest approach)
              const code = sessionStorage.getItem('pobCode');
              if (code) window.location.reload();
            }} />
          )}

          {/* Empty state */}
          {!isLoadingRec && !recError && recResponse && recResponse.recommendations.length === 0 && (
            <div className="bg-gray-800 rounded-lg p-6 text-center text-gray-500">
              No upgrade recommendations found for this build.
            </div>
          )}

          {/* D5.4 Recommendation cards */}
          {!isLoadingRec && recResponse && recResponse.recommendations.length > 0 && (
            <div className="space-y-3" data-testid="recommendations-list">
              {recResponse.recommendations.map(rec => (
                <RecommendationCard
                  key={rec.rank}
                  rec={rec}
                  sessionId={sessionId}
                  league={league}
                  characterLevel={buildData.level}
                />
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// D5.3 Build Summary Card
// ---------------------------------------------------------------------------

interface BuildSummaryCardProps {
  cls: string;
  ascendancy: string;
  level: number;
  bandit: string;
  mainSkill: string;
  stats: BuildData['stats'];
}

function BuildSummaryCard({ cls, ascendancy, level, bandit, mainSkill, stats }: BuildSummaryCardProps) {
  const resCap = 75;
  type ResKey = 'fireRes' | 'coldRes' | 'lightningRes' | 'chaosRes';
  const resFields: { label: string; key: ResKey; color: string; capColor: string }[] = [
    { label: 'Fire',      key: 'fireRes',       color: 'text-orange-400', capColor: 'text-green-400' },
    { label: 'Cold',      key: 'coldRes',       color: 'text-cyan-400',   capColor: 'text-green-400' },
    { label: 'Lightning', key: 'lightningRes',  color: 'text-yellow-400', capColor: 'text-green-400' },
    { label: 'Chaos',     key: 'chaosRes',      color: 'text-purple-400', capColor: 'text-green-400' },
  ];

  return (
    <div className="bg-gray-800 rounded-lg p-5 space-y-4" data-testid="build-summary">
      {/* Character row */}
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <InfoItem label="Class"      value={cls || 'â€”'} />
        <InfoItem label="Ascendancy" value={ascendancy || 'â€”'} />
        <InfoItem label="Level"      value={level ? String(level) : 'â€”'} />
        <InfoItem label="Bandit"     value={bandit || 'None'} />
        {mainSkill && <InfoItem label="Main Skill" value={mainSkill} highlight />}
      </div>

      {/* Key stats */}
      <div className="grid grid-cols-3 gap-3">
        <StatBar label="Life"           value={stats.life}         color="bg-red-500"  textColor="text-red-400" />
        <StatBar label="Energy Shield"  value={stats.energyShield} color="bg-blue-500" textColor="text-blue-400" />
        <StatBar label="DPS"            value={stats.dps}          color="bg-amber-500" textColor="text-amber-400" isDps />
      </div>

      {/* Resistances */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {resFields.map(r => {
          const val = stats[r.key];
          const capped = val >= resCap;
          return (
            <div key={r.key} className={`rounded px-3 py-2 text-center ${capped ? 'bg-green-950/40 border border-green-800/50' : 'bg-red-950/40 border border-red-800/50'}`}>
              <div className="text-xs text-gray-500 uppercase tracking-wide">{r.label} Res</div>
              <div className={`font-bold text-lg ${capped ? 'text-green-400' : 'text-red-400'}`}>
                {val}%
              </div>
              {!capped && <div className="text-xs text-red-500">Uncapped</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface InfoItemProps { label: string; value: string; highlight?: boolean }
function InfoItem({ label, value, highlight = false }: InfoItemProps) {
  return (
    <div>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`font-medium ${highlight ? 'text-amber-400' : 'text-gray-100'}`}>{value}</div>
    </div>
  );
}

interface StatBarProps {
  label: string;
  value: number;
  color: string;
  textColor: string;
  isDps?: boolean;
}
function StatBar({ label, value, textColor, isDps = false }: StatBarProps) {
  const formatted = isDps && value >= 1_000_000
    ? `${(value / 1_000_000).toFixed(2)}M`
    : isDps && value >= 1_000
      ? `${(value / 1_000).toFixed(1)}k`
      : value.toLocaleString();

  return (
    <div className="bg-gray-700/50 rounded px-3 py-2">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`font-bold text-xl ${textColor}`}>{formatted}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Critical Issues Panel
// ---------------------------------------------------------------------------

interface CriticalIssuesPanelProps { issues: CriticalIssue[] }
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
            {issue.severity === 'critical' ? 'âš ï¸' : 'âš¡'}
          </span>
          <div>
            <span className="font-semibold capitalize">{issue.category.replace(/_/g, ' ')}: </span>
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

// ---------------------------------------------------------------------------
// D5.7 Error Panel
// ---------------------------------------------------------------------------

const ERROR_MESSAGES: Record<ErrorKind, string> = {
  parse:   "We couldn't parse this PoB code. Make sure you're using Path of Building Community Fork v2.35 or later.",
  server:  'Something went wrong generating recommendations. Please try again.',
  timeout: 'Analysis is taking longer than expected. This may happen with very complex builds.',
  network: 'Unable to reach the server. Check your connection and try again.',
  unknown: 'Something went wrong generating recommendations. Please try again.',
};

interface ErrorPanelProps { kind: ErrorKind; onRetry: () => void }
function ErrorPanel({ kind, onRetry }: ErrorPanelProps) {
  return (
    <div
      role="alert"
      className="bg-red-950 border border-red-700 rounded-lg p-4 space-y-3"
    >
      <p className="text-red-300 text-sm">{ERROR_MESSAGES[kind]}</p>
      <button
        type="button"
        onClick={onRetry}
        className="text-xs bg-red-800 hover:bg-red-700 text-red-100 px-3 py-1.5 rounded transition-colors"
      >
        Try Again
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// D5.4 Recommendation Card (collapsible, feedback buttons)
// ---------------------------------------------------------------------------

const CATEGORY_STYLES: Record<string, { bg: string; badgeBg: string; text: string; label: string }> = {
  critical_fix:    { bg: 'bg-red-900/30 border-red-700',    badgeBg: 'bg-red-700',    text: 'text-red-300',    label: 'Critical Fix' },
  power_upgrade:   { bg: 'bg-amber-900/30 border-amber-700', badgeBg: 'bg-amber-700', text: 'text-amber-300',  label: 'Power Upgrade' },
  defense_upgrade: { bg: 'bg-blue-900/30 border-blue-700',  badgeBg: 'bg-blue-700',   text: 'text-blue-300',   label: 'Defense Upgrade' },
  efficiency:      { bg: 'bg-green-900/30 border-green-700', badgeBg: 'bg-green-700', text: 'text-green-300',  label: 'Efficiency' },
  qol:             { bg: 'bg-purple-900/30 border-purple-700', badgeBg: 'bg-purple-700', text: 'text-purple-300', label: 'Quality of Life' },
};

interface RecommendationCardProps {
  rec: Recommendation;
  sessionId: string;
  league: string;
  characterLevel: number;
}

function RecommendationCard({ rec, sessionId, league, characterLevel }: RecommendationCardProps) {
  const [expanded, setExpanded] = useState(false);
  /** null = not voted yet, 'up' | 'down' = voted */
  const [voted, setVoted] = useState<'up' | 'down' | null>(null);
  /** null = not reported, 'reported' = wrong_explanation submitted */
  const [reported, setReported] = useState<'reported' | null>(null);
  const style = CATEGORY_STYLES[rec.category] ?? CATEGORY_STYLES.qol;

  const dpsDelta = rec.deltas['dps'] ?? rec.deltas['total_dps'] ?? null;
  const lifeDelta = rec.deltas['life'] ?? null;
  const esDelta   = rec.deltas['es'] ?? rec.deltas['energy_shield'] ?? null;
  const ehpDelta  = rec.deltas['ehp'] ?? rec.deltas['effective_hp'] ?? null;
  const fireResDelta  = rec.deltas['fire_res'] ?? null;
  const coldResDelta  = rec.deltas['cold_res'] ?? null;
  const lightResDelta = rec.deltas['lightning_res'] ?? null;

  /** Submit a thumbs-up or thumbs-down vote. */
  async function handleVote(vote: 'up' | 'down') {
    if (voted !== null) return; // already voted
    setVoted(vote); // optimistically update UI
    await submitFeedback({
      session_id: sessionId,
      recommendation_rank: rec.rank,
      vote,
      context: {
        archetype_damage: '',
        archetype_defense: '',
        archetype_playstyle: '',
        character_level: characterLevel,
        league,
        recommendation_category: rec.category,
        slot: rec.slot,
        suggested_item: rec.suggestedItem,
        dps_delta: dpsDelta,
        ehp_delta: ehpDelta,
        price_divine: rec.priceDivine,
        explanation_source: rec.explanationSource,
      },
    });
  }

  /** Report that the explanation is wrong or misleading. */
  async function handleReportExplanation() {
    if (reported !== null) return; // already reported
    setReported('reported'); // optimistically update UI
    await submitFeedback({
      session_id: sessionId,
      recommendation_rank: rec.rank,
      vote: 'wrong_explanation',
      context: {
        archetype_damage: '',
        archetype_defense: '',
        archetype_playstyle: '',
        character_level: characterLevel,
        league,
        recommendation_category: rec.category,
        slot: rec.slot,
        suggested_item: rec.suggestedItem,
        dps_delta: dpsDelta,
        ehp_delta: ehpDelta,
        price_divine: rec.priceDivine,
        explanation_source: rec.explanationSource,
      },
    });
  }

  /** Fire trade-click tracking before opening the trade URL. */
  async function handleTradeClick(e: React.MouseEvent<HTMLAnchorElement>) {
    e.preventDefault();
    const url = rec.tradeUrl;
    void trackTradeClick({
      session_id: sessionId,
      recommendation_rank: rec.rank,
      suggested_item: rec.suggestedItem,
      league,
    });
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  return (
    <div
      data-testid={`recommendation-${rec.rank}`}
      className={`rounded-lg border ${style.bg} overflow-hidden`}
    >
      {/* Clickable header â€” always visible */}
      <button
        type="button"
        className="w-full text-left px-4 py-3 flex items-start justify-between gap-3 hover:bg-white/5 transition-colors"
        onClick={() => setExpanded(e => !e)}
        aria-expanded={expanded}
        aria-controls={`rec-body-${rec.rank}`}
      >
        <div className="flex items-center gap-3 flex-wrap min-w-0">
          {/* Rank + category badge */}
          <span className={`shrink-0 w-8 h-8 rounded-full ${style.badgeBg} flex items-center justify-center text-white text-xs font-bold`}>
            #{rec.rank}
          </span>
          <span className={`text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border ${style.text} ${style.bg}`}>
            {style.label}
          </span>
          <span className="text-xs text-gray-500 uppercase shrink-0">{rec.slot}</span>
          {/* Deltas inline on header */}
          <div className="flex flex-wrap gap-1.5 items-center">
            {dpsDelta !== null && dpsDelta !== 0 && <DeltaBadge label="DPS" value={dpsDelta} formatFn={formatDps} />}
            {lifeDelta !== null && lifeDelta !== 0 && <DeltaBadge label="Life" value={lifeDelta} formatFn={Math.round} />}
            {esDelta   !== null && esDelta   !== 0 && <DeltaBadge label="ES"   value={esDelta}   formatFn={Math.round} />}
            {ehpDelta  !== null && ehpDelta  !== 0 && <DeltaBadge label="EHP"  value={ehpDelta}  formatFn={Math.round} />}
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {rec.priceDivine !== null && (
            <span className="text-sm font-semibold text-amber-400 whitespace-nowrap">
              ~{rec.priceDivine.toFixed(1)} div
            </span>
          )}
          {rec.priceDivine === null && (
            <span className="text-xs text-gray-500 whitespace-nowrap">Price unknown</span>
          )}
          <span className={`text-gray-500 transition-transform ${expanded ? 'rotate-180' : ''}`} aria-hidden="true">â–¾</span>
        </div>
      </button>

      {/* Item swap line */}
      <div className="px-4 pb-2 flex items-center gap-2 text-sm flex-wrap">
        <span className="text-gray-400">{rec.currentItem}</span>
        <span className="text-gray-600">â†’</span>
        <span className="text-gray-100 font-medium">{rec.suggestedItem}</span>
      </div>

      {/* Expandable body */}
      {expanded && (
        <div id={`rec-body-${rec.rank}`} className="px-4 pb-4 space-y-3 border-t border-white/10 pt-3">
          {/* Resistance deltas */}
          {(fireResDelta !== null || coldResDelta !== null || lightResDelta !== null) && (
            <div className="flex flex-wrap gap-2">
              {fireResDelta  !== null && fireResDelta  !== 0 && <DeltaBadge label="Î”Fire Res"  value={fireResDelta}  formatFn={v => `${Math.round(v)}%`} />}
              {coldResDelta  !== null && coldResDelta  !== 0 && <DeltaBadge label="Î”Cold Res"  value={coldResDelta}  formatFn={v => `${Math.round(v)}%`} />}
              {lightResDelta !== null && lightResDelta !== 0 && <DeltaBadge label="Î”Lght Res"  value={lightResDelta} formatFn={v => `${Math.round(v)}%`} />}
            </div>
          )}

          {/* Efficiency */}
          {rec.efficiencyScore !== null && (
            <div className="text-xs text-gray-400">
              Efficiency: <span className="text-gray-200 font-medium">{formatDps(rec.efficiencyScore)} DPS per divine</span>
            </div>
          )}

          {/* Explanation */}
          <p className="text-sm text-gray-300">{rec.explanation}</p>

          {/* D7.5 — Report incorrect explanation (LLM-sourced only) */}
          {rec.explanationSource === 'llm' && (
            <div className="text-xs text-gray-600">
              {reported === 'reported' ? (
                <span className="text-gray-500">Thank you for the report.</span>
              ) : (
                <button
                  type="button"
                  onClick={() => void handleReportExplanation()}
                  data-testid={`report-explanation-${rec.rank}`}
                  className="text-gray-500 hover:text-red-400 underline cursor-pointer transition-colors"
                >
                  Report incorrect explanation
                </button>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex flex-wrap gap-2">
            {rec.tradeUrl && (
              <a
                href={rec.tradeUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-testid={`trade-link-${rec.rank}`}
                onClick={handleTradeClick}
                className="text-xs bg-amber-600 hover:bg-amber-500 text-gray-950 font-semibold
                           px-3 py-1.5 rounded transition-colors"
              >
                Search on Trade ↗
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
                View on Wiki â†—
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
                Price History â†—
              </a>
            )}
          </div>

          {/* Live trade listings panel */}
          <TradeListingsPanel rec={rec} league={league} />

          {/* D6.3 Feedback buttons */}
          <div className="flex items-center gap-2 pt-1" data-testid={`feedback-${rec.rank}`}>
            <span className="text-xs text-gray-500">Was this helpful?</span>
            <button
              type="button"
              disabled={voted !== null}
              onClick={() => void handleVote('up')}
              aria-label="Thumbs up — helpful"
              aria-pressed={voted === 'up'}
              data-testid={`vote-up-${rec.rank}`}
              className={`text-sm px-2 py-0.5 rounded transition-colors ${
                voted === 'up'
                  ? 'bg-green-700 text-white cursor-default'
                  : voted !== null
                    ? 'bg-gray-800 text-gray-600 cursor-not-allowed opacity-50'
                    : 'bg-gray-700 hover:bg-green-700/60 text-gray-300 cursor-pointer'
              }`}
            >
              👍
            </button>
            <button
              type="button"
              disabled={voted !== null}
              onClick={() => void handleVote('down')}
              aria-label="Thumbs down — not helpful"
              aria-pressed={voted === 'down'}
              data-testid={`vote-down-${rec.rank}`}
              className={`text-sm px-2 py-0.5 rounded transition-colors ${
                voted === 'down'
                  ? 'bg-red-700 text-white cursor-default'
                  : voted !== null
                    ? 'bg-gray-800 text-gray-600 cursor-not-allowed opacity-50'
                    : 'bg-gray-700 hover:bg-red-700/60 text-gray-300 cursor-pointer'
              }`}
            >
              👎
            </button>
            {voted !== null && (
              <span className="text-xs text-gray-500 ml-1">Thanks for your feedback!</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trade listings panel — lazy-loaded inline price checker
// ---------------------------------------------------------------------------

type TradeState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: TradeListingsResponse }
  | { status: 'error'; message: string };

interface TradeListingsPanelProps {
  rec: Recommendation;
  league: string;
}

function TradeListingsPanel({ rec, league }: TradeListingsPanelProps) {
  const { poeSessionId } = usePoeSession();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<TradeState>({ status: 'idle' });
  const [copied, setCopied] = useState<string | null>(null);

  async function load() {
    if (state.status === 'loading') return;
    setState({ status: 'loading' });
    try {
      const result = await fetchTradeListings({
        item_name: rec.isUnique ? rec.suggestedItem : '',
        base_type: rec.isGem ? rec.suggestedItem : rec.baseType,
        is_unique: rec.isUnique,
        is_gem: rec.isGem,
        league,
        count: 5,
        buyout_only: true,
        poesessid: poeSessionId || undefined,
      });
      if (result.error) {
        setState({ status: 'error', message: result.error });
      } else {
        setState({ status: 'success', data: result });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setState({ status: 'error', message: msg });
    }
  }

  function handleToggle() {
    if (!open && (state.status === 'idle' || state.status === 'error')) {
      void load();
    }
    setOpen(prev => !prev);
  }

  async function copyWhisper(whisper: string, id: string) {
    try {
      await navigator.clipboard.writeText(whisper);
      setCopied(id);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // Clipboard API not available in this context — silently ignore.
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={handleToggle}
        data-testid={`live-prices-${rec.rank}`}
        className={`text-xs px-3 py-1.5 rounded transition-colors font-semibold ${
          open
            ? 'bg-sky-700 hover:bg-sky-600 text-white'
            : 'bg-gray-700 hover:bg-sky-700/60 text-gray-200'
        }`}
      >
        {open ? 'Hide Prices' : 'Live Prices ✦'}
      </button>

      {open && (
        <div className="mt-2 rounded-lg bg-gray-900 border border-gray-700/60 p-3 space-y-2">
          {state.status === 'loading' && (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span
                className="inline-block w-3 h-3 rounded-full border-2 border-sky-400 border-t-transparent animate-spin"
                aria-hidden="true"
              />
              Fetching live listings…
            </div>
          )}

          {state.status === 'error' && (
            <div className="space-y-1">
              <p className="text-xs text-red-400">{state.message}</p>
              <button
                type="button"
                onClick={() => { setState({ status: 'idle' }); void load(); }}
                className="text-xs text-sky-400 hover:underline"
              >
                Retry
              </button>
            </div>
          )}

          {state.status === 'success' && (
            <>
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>
                  {state.data.total_listings.toLocaleString()} listing
                  {state.data.total_listings !== 1 ? 's' : ''} found
                  {' · buyout only'}
                </span>
                {state.data.cached && (
                  <span className="italic text-gray-600">cached</span>
                )}
              </div>

              {state.data.listings.length === 0 ? (
                <p className="text-xs text-gray-500">No buyout listings right now.</p>
              ) : (
                <ListingsList
                  listings={state.data.listings}
                  copied={copied}
                  onCopy={copyWhisper}
                />
              )}

              <a
                href={state.data.trade_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block text-xs text-sky-400 hover:text-sky-300 hover:underline"
              >
                View all on trade site ↗
              </a>
            </>
          )}

          {/* Nudge to add POESESSID when not set */}
          {!poeSessionId && state.status !== 'loading' && (
            <p className="text-xs text-gray-600 border-t border-gray-800 pt-2">
              Tip: Add your{' '}
              <code className="text-amber-500/80">POESESSID</code> via the{' '}
              <span className="text-gray-400">⚙️</span> button in the header for
              more reliable price fetching.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

interface ListingsListProps {
  listings: TradeListing[];
  copied: string | null;
  onCopy: (whisper: string, id: string) => Promise<void>;
}

function ListingsList({ listings, copied, onCopy }: ListingsListProps) {
  return (
    <ul className="space-y-1.5" aria-label="Trade listings">
      {listings.map(listing => (
        <li
          key={listing.id}
          className="flex items-center justify-between gap-2 bg-gray-800/60 rounded px-3 py-1.5"
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-sm font-bold text-amber-300 shrink-0">
              {listing.price.amount}
              <span className="ml-1 text-xs font-normal text-amber-400/80">
                {listing.price.currency_display || listing.price.currency}
              </span>
            </span>
            <span className="text-xs text-gray-500 truncate">
              {listing.character_name || listing.account_name}
            </span>
            {listing.ilvl > 0 && (
              <span className="text-xs text-gray-600 shrink-0">iL{listing.ilvl}</span>
            )}
            {listing.corrupted && (
              <span className="text-xs text-red-400 shrink-0">Corrupted</span>
            )}
          </div>

          {listing.whisper && (
            <button
              type="button"
              onClick={() => void onCopy(listing.whisper, listing.id)}
              aria-label="Copy whisper message for this listing"
              title={listing.whisper}
              className={`text-xs px-2 py-0.5 rounded shrink-0 transition-colors ${
                copied === listing.id
                  ? 'bg-green-700 text-green-100 cursor-default'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-300 cursor-pointer'
              }`}
            >
              {copied === listing.id ? '✓ Copied' : 'Whisper'}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

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


