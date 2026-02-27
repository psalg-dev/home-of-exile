/**
 * HomePage — landing page where users paste their PoB export code.
 *
 * Implements D5.1 (hero, input, validation) and D5.2 (loading overlay)
 * from milestone M5.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { decodePobCode } from '@/lib/pob/decode';
import { parsePobXml } from '@/lib/pob/parse';
import type { BuildData } from '@/lib/pob/types';
import { PobDecodeError, PobParseError } from '@/lib/pob/types';
import LoadingOverlay from '@/components/LoadingOverlay';

/**
 * Example PoB code — a level-90 Slayer build used as a demo.
 * Generated from a minimal fixture XML (see gen_example_pob.cjs in repo root).
 */
const EXAMPLE_POB_CODE =
  'eJyVUttOwzAMfecrorxDyx2kdkjANiHBmCiIZ7cxazQ3GUk6bX-Pe9kmJjGJlyiOz7GP' +
  '45PcrSoSS3ReW5PK05NYCjSFVdrMUvnxPjq-kXeDo2QKoXz9uq81NZnBkRBJGwjCJVIq' +
  'b5lXEHg_gQpT-VgjaR-kAF-gUQ-7TEawRsfgEhwUAV33PFxBtSDcZHMwSodUTqxBKSrQ' +
  'JrPFHMPY2XrBMmWjgDVMW3wWIAjPRyqf9RcTlkA1F72I41hGf0GHBt1snZUaSW0pB_AP' +
  'tsq1QfU4zbbwyzg-2GOkHb6hb7-ip1xfHmpB6h_wZz0rg-F9_KdFCdbv4Y-v-hGSqF1q' +
  'e83mmsj3ZdpAeLJc4RNhYY04bYwCOaFKZXA1_zpB3lih3w2zxlgJw-vNFliwJ2zNaJEFp' +
  '-eM9k3JJya_YAAFAaKngJWPxs3R9uNbx9lQeq-dsde-ayAd1l3wW8dm9K5IN9ZumOTdIQ' +
  '6SRpIwVqFnN4kzcc60JGpzDaiTwr6P9oz_A0BwAYQ';

/** Reasonable upper bound — anything longer is suspicious. */
const MAX_POB_LENGTH = 8_192;

/**
 * Validate the raw PoB input before decoding.
 * Returns an error string, or null if input looks valid.
 */
function validateInput(code: string): string | null {
  const trimmed = code.trim();
  if (!trimmed) return 'Please paste a PoB export code.';
  if (trimmed.length < 20) return 'This looks too short to be a valid PoB code.';
  if (trimmed.length > MAX_POB_LENGTH)
    return 'This code is too long. Make sure you copied the right thing.';
  // PoB codes are URL-safe base64: only [A-Za-z0-9\-_]
  if (!/^[A-Za-z0-9\-_]+$/.test(trimmed)) {
    return 'This does not look like a valid PoB code. Make sure you copied the base64 export from Path of Building.';
  }
  return null;
}

export default function HomePage() {
  const [pobCode, setPobCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const navigate = useNavigate();

  const charCount = pobCode.length;
  const isOverLimit = charCount > MAX_POB_LENGTH;

  function loadExample() {
    setPobCode(EXAMPLE_POB_CODE);
    setError(null);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const validationError = validateInput(pobCode);
    if (validationError) {
      setError(validationError);
      return;
    }

    try {
      const xml = decodePobCode(pobCode);
      const buildData: BuildData = parsePobXml(xml);

      sessionStorage.setItem('buildData', JSON.stringify({
        ...buildData,
        items: Object.fromEntries(buildData.items),
      }));
      sessionStorage.setItem('pobCode', pobCode.trim());

      setIsAnalyzing(true);
      void navigate('/build');
    } catch (err) {
      if (err instanceof PobDecodeError || err instanceof PobParseError) {
        setError(
          "We couldn't parse this PoB code. Make sure you're using Path of Building Community Fork v2.35 or later.",
        );
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
    }
  }

  function handleCancel() {
    setIsAnalyzing(false);
  }

  return (
    <>
      {isAnalyzing && <LoadingOverlay onCancel={handleCancel} />}

      <div className="min-h-[calc(100vh-3.5rem-4rem)] bg-gray-950 text-gray-100 flex flex-col items-center justify-center px-4 sm:px-6 py-12">
        <div className="w-full max-w-2xl space-y-8">

          {/* Hero */}
          <div className="text-center space-y-3">
            <h1 className="text-4xl sm:text-5xl font-bold text-amber-400 tracking-tight">
              Home of Exile
            </h1>
            <p className="text-gray-300 text-lg sm:text-xl max-w-xl mx-auto leading-relaxed">
              Paste your Path of Building export code and get{' '}
              <span className="text-amber-300 font-medium">5 data-driven upgrade recommendations</span>
              {' '}ranked by cost-efficiency.
            </p>
            <p className="text-gray-500 text-sm">
              Powered by live poe.ninja prices &amp; LuaJIT simulation engine.
            </p>
          </div>

          {/* Input form */}
          <form onSubmit={handleSubmit} className="space-y-3" noValidate>
            <div className="relative">
              <textarea
                className={`w-full h-40 bg-gray-800 border rounded-lg p-4 text-sm font-mono
                           text-gray-100 resize-none focus:outline-none focus:ring-1
                           placeholder-gray-500 transition-colors
                           ${isOverLimit || error
                             ? 'border-red-600 focus:border-red-500 focus:ring-red-500'
                             : 'border-gray-700 focus:border-amber-400 focus:ring-amber-400'
                           }`}
                placeholder="Paste your PoB export code here..."
                value={pobCode}
                onChange={e => { setPobCode(e.target.value); setError(null); }}
                aria-label="Path of Building export code"
                aria-describedby={error ? 'pob-error' : 'pob-char-count'}
                spellCheck={false}
              />
              {/* Character count indicator */}
              <div
                id="pob-char-count"
                aria-live="polite"
                className={`absolute bottom-2 right-3 text-xs select-none pointer-events-none ${
                  isOverLimit ? 'text-red-400 font-medium' : charCount > 0 ? 'text-gray-500' : 'text-gray-700'
                }`}
              >
                {charCount.toLocaleString()} / {MAX_POB_LENGTH.toLocaleString()}
              </div>
            </div>

            {/* Inline error */}
            {error && (
              <div
                id="pob-error"
                role="alert"
                className="bg-red-950 border border-red-700 rounded-lg p-3 text-red-300 text-sm"
              >
                {error}
              </div>
            )}

            {/* Primary action */}
            <button
              type="submit"
              disabled={!pobCode.trim() || isOverLimit}
              className="w-full bg-amber-500 hover:bg-amber-400 disabled:bg-gray-700 disabled:cursor-not-allowed
                         text-gray-950 font-semibold py-3 rounded-lg transition-colors text-base"
            >
              Analyse Build
            </button>

            {/* Example link */}
            <p className="text-center text-sm text-gray-500">
              No build yet?{' '}
              <button
                type="button"
                onClick={loadExample}
                className="text-amber-400 hover:text-amber-300 underline underline-offset-2 transition-colors"
              >
                Try an example build
              </button>
            </p>
          </form>

          {/* How-to instructions */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2 text-sm text-gray-400">
            <p className="font-medium text-gray-300">How to get your PoB code:</p>
            <ol className="list-decimal list-inside space-y-1">
              <li>Open <span className="text-gray-200">Path of Building Community Fork</span></li>
              <li>Load or build your character</li>
              <li>Click <span className="text-gray-200">Export Build</span> → <span className="text-gray-200">Copy to Clipboard</span></li>
              <li>Paste the code above and click <span className="text-amber-400">Analyse Build</span></li>
            </ol>
          </div>

        </div>
      </div>
    </>
  );
}
