"""Build the report: python -m permits [--refresh] [--since 2017-01-01]"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .report import analyse, readme_section, update_readme, write_report
from .sources import ACTIVE, CLEARED, download, downloaded_on, read

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default="2017-01-01", help="first issue date to include (the files start in 2017)")
    parser.add_argument("--refresh", action="store_true", help="download again instead of using the cache")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--out", type=Path, default=ROOT / "report")
    args = parser.parse_args(argv)

    frames = {}
    for dataset in (CLEARED, ACTIVE):
        print(f"Loading {dataset.resource} ...")
        frames[dataset.key] = read(download(dataset, args.data, args.refresh), dataset.key)

    # The data runs up to the day before the download; that's the end of the period analysed.
    end = min(downloaded_on(args.data, d) for d in (CLEARED, ACTIVE)) - pd.Timedelta(days=1)
    meta = json.loads((args.data / f"{CLEARED.key}.json").read_text())
    note = f"Data downloaded {pd.Timestamp(meta['downloaded']):%b %-d, %Y}."

    analysis = analyse(frames["cleared"], frames["active"], pd.Timestamp(args.since), end, note)
    path = write_report(analysis, args.out)
    print(f"Wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    readme = ROOT / "README.md"
    if readme.exists() and update_readme(readme, readme_section(analysis)):
        print("Updated the results section in README.md")


if __name__ == "__main__":
    main()
