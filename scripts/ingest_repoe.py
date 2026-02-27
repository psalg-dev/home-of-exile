#!/usr/bin/env python3
"""
Download RePoE static data files to data/repoe/.

Downloads base_items.json, gems.json, and mods.json from the brather1ng/RePoE
repository on GitHub and saves them to the data/repoe/ directory.

Usage:
    uv run scripts/ingest_repoe.py

The script prints the download size and SHA-256 hash of each file so you can
verify integrity or detect upstream changes.
"""

import hashlib
import sys
from pathlib import Path

# httpx is a required dependency; install via: pip install httpx
try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_BASE_URL = (
    "https://raw.githubusercontent.com/brather1ng/RePoE/master/RePoE/data/"
)

_FILES = [
    "base_items.json",
    "gems.json",
    "mods.json",
]

# Resolve the output directory relative to this script's location
_SCRIPT_DIR = Path(__file__).parent
_OUTPUT_DIR = _SCRIPT_DIR.parent / "data" / "repoe"


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------


def sha256(data: bytes) -> str:
    """
    Compute the hex-encoded SHA-256 hash of a byte string.

    Args:
        data: Raw bytes to hash.

    Returns:
        Lowercase hex digest string.
    """
    return hashlib.sha256(data).hexdigest()


def download_file(client: httpx.Client, filename: str, output_dir: Path) -> None:
    """
    Download a single RePoE data file and save it to disk.

    Prints the download size and SHA-256 of the file on success.

    Args:
        client: An active httpx.Client instance.
        filename: The filename to download (e.g. 'base_items.json').
        output_dir: Directory where the file should be saved.
    """
    url = _BASE_URL + filename
    output_path = output_dir / filename

    print(f"  Downloading {filename} …", end=" ", flush=True)

    response = client.get(url, follow_redirects=True, timeout=60.0)
    response.raise_for_status()

    content = response.content
    size_kb = len(content) / 1024
    digest = sha256(content)

    output_path.write_bytes(content)

    print(f"done  ({size_kb:.1f} KB, sha256={digest[:16]}…)")


def main() -> None:
    """
    Entry point — download all RePoE data files.

    Creates the output directory if it does not exist.
    Exits with a non-zero status code on any download failure.
    """
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {_OUTPUT_DIR.resolve()}\n")

    success = True
    with httpx.Client(
        headers={"User-Agent": "home-of-exile/ingest_repoe.py"},
        timeout=60.0,
    ) as client:
        for filename in _FILES:
            try:
                download_file(client, filename, _OUTPUT_DIR)
            except Exception as exc:
                print(f"  FAILED: {exc}", file=sys.stderr)
                success = False

    if not success:
        sys.exit(1)

    print("\nAll files downloaded successfully.")


if __name__ == "__main__":
    main()
