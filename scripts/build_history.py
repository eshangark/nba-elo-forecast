"""Validate downloaded ESPN-derived archives before model fitting."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_forecast.history import build_season


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--cities", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", default=[2022, 2023, 2024, 2025, 2026])
    args = parser.parse_args()
    for year in args.years:
        build_season(year, args.archive_dir, args.cities, args.cache, args.output)


if __name__ == "__main__":
    main()
