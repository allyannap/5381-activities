import sys
from pathlib import Path

import requests


VERA_NATIONAL_URL = "https://raw.githubusercontent.com/vera-institute/ice-detention-trends/main/national.csv"


def download_national_csv(target_path: Path) -> None:
    """
    Download Vera's national.csv file to the given path.

    This is a one-time helper used for Homework 1 so that the Shiny app
    can read national trends from a local CSV instead of depending on
    network access at runtime.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading national.csv from {VERA_NATIONAL_URL} ...")
    resp = requests.get(VERA_NATIONAL_URL, timeout=60)
    resp.raise_for_status()

    target_path.write_bytes(resp.content)
    print(f"Wrote {target_path} ({len(resp.content)} bytes)")


def main() -> None:
    root = Path(__file__).resolve().parent
    out_path = root / "data" / "national.csv"
    download_national_csv(out_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - simple helper script
        print(f"Error downloading national.csv: {exc}", file=sys.stderr)
        sys.exit(1)

