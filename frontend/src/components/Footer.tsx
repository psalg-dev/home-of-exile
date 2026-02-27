/**
 * Footer — minimal site-wide footer with attribution links.
 * NOTE: Fandom PoE wiki links are explicitly excluded per project policy.
 */
export default function Footer() {
  return (
    <footer className="mt-auto border-t border-gray-800 bg-gray-900/60">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-gray-500">
        <p>
          &copy; {new Date().getFullYear()} Home of Exile — not affiliated with Grinding Gear Games.
        </p>
        <div className="flex items-center gap-4">
          <a
            href="https://www.pathofexile.com/trade"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-gray-300 transition-colors"
          >
            Trade Site ↗
          </a>
          <a
            href="https://poe.ninja"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-gray-300 transition-colors"
          >
            poe.ninja ↗
          </a>
          <a
            href="https://www.poewiki.net"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-gray-300 transition-colors"
          >
            Wiki ↗
          </a>
        </div>
      </div>
    </footer>
  );
}
