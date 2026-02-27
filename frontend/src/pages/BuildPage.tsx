import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { BuildData } from '@/lib/pob/types';

/**
 * BuildPage — displays the parsed build data from a PoB code.
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

  if (!buildData) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center justify-center p-6">
        <p className="text-gray-400 mb-4">No build data found.</p>
        <Link
          to="/"
          className="text-amber-400 hover:text-amber-300 underline"
        >
          ← Import a build
        </Link>
      </div>
    );
  }

  const { characterName, class: cls, ascendancy, level, bandit, mainSkill, stats } = buildData;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6">
      <div className="max-w-4xl mx-auto space-y-6">
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
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wide">Class</div>
            <div className="text-gray-100 font-medium">{cls || '—'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wide">Ascendancy</div>
            <div className="text-gray-100 font-medium">{ascendancy || '—'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wide">Level</div>
            <div className="text-gray-100 font-medium">{level || '—'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wide">Bandit</div>
            <div className="text-gray-100 font-medium">{bandit || 'None'}</div>
          </div>
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
      </div>
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
