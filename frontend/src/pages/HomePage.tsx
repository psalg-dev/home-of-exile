import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { decodePobCode } from '@/lib/pob/decode';
import { parsePobXml } from '@/lib/pob/parse';
import type { BuildData } from '@/lib/pob/types';
import { PobDecodeError, PobParseError } from '@/lib/pob/types';

/**
 * HomePage — landing page where users paste their Path of Building export code.
 */
export default function HomePage() {
  const [pobCode, setPobCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    try {
      const xml = decodePobCode(pobCode);
      const buildData: BuildData = parsePobXml(xml);
      console.log('[HomeOfExile] BuildData:', buildData);
      // Store in sessionStorage to pass to BuildPage
      sessionStorage.setItem('buildData', JSON.stringify({
        ...buildData,
        // Map can't be JSON serialised directly
        items: Object.fromEntries(buildData.items),
      }));
      // Persist raw PoB code so BuildPage can send it to the simulation engine
      sessionStorage.setItem('pobCode', pobCode.trim());
      void navigate('/build');
    } catch (err) {
      if (err instanceof PobDecodeError || err instanceof PobParseError) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-2xl space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-4xl font-bold text-amber-400">Home of Exile</h1>
          <p className="text-gray-400 text-lg">
            Paste your Path of Building export code to analyse your build
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <textarea
            className="w-full h-40 bg-gray-800 border border-gray-700 rounded-lg p-4 text-sm font-mono
                       text-gray-100 resize-none focus:outline-none focus:border-amber-400 focus:ring-1
                       focus:ring-amber-400 placeholder-gray-500"
            placeholder="Paste your PoB export code here..."
            value={pobCode}
            onChange={(e) => setPobCode(e.target.value)}
            aria-label="Path of Building export code"
          />

          {error && (
            <div
              role="alert"
              className="bg-red-950 border border-red-700 rounded-lg p-3 text-red-300 text-sm"
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={!pobCode.trim()}
            className="w-full bg-amber-500 hover:bg-amber-400 disabled:bg-gray-700 disabled:cursor-not-allowed
                       text-gray-950 font-semibold py-3 rounded-lg transition-colors"
          >
            Analyse Build
          </button>
        </form>
      </div>
    </div>
  );
}
