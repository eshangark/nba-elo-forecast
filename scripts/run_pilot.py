"""Collect a bounded historical interval and run the unfitted model pilot."""

import argparse
import hashlib
import json
import sys
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_forecast.data import Client, Cities, parse_summary, write_json
from nba_forecast.replay import replay
from nba_forecast.seasons import publish_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2024-10-22")
    parser.add_argument("--end", default="2024-11-10")
    parser.add_argument("--evaluate-from", default="2024-11-04")
    parser.add_argument("--cities", required=True, type=Path)
    parser.add_argument("--cache", type=Path, default=Path("data/raw/espn"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/pilot"))
    parser.add_argument("--refresh", action="store_true", help="Refetch source payloads rather than use cache")
    parser.add_argument("--publish-archive", type=Path, help="Export verified processed history to a season directory")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start or (end-start).days > 60:
        parser.error("Select a pilot interval of at most 61 days")
    if not start <= date.fromisoformat(args.evaluate_from) <= end:
        parser.error("evaluate-from must be inside the collection interval")
    cities = Cities(args.cities)
    client = Client(args.cache)
    events, games, failures, exclusions = {}, [], [], []
    day = start
    while day <= end:
        payload = client.get("scoreboard", "dates=" + day.strftime("%Y%m%d"), refresh=args.refresh)
        if "events" not in payload:
            raise ValueError(f"Missing events field on {day}")
        for event in payload["events"]:
            if int(event.get("season", {}).get("type", 0)) != 2:
                exclusions.append({"id": event["id"], "reason": "not regular season"})
                continue
            events[event["id"]] = event
        day += timedelta(days=1)
    print(f"Discovered {len(events)} regular-season events", flush=True)
    for index, (event_id, event) in enumerate(events.items(), 1):
        try:
            payload = client.get("summary", "event=" + event_id, refresh=args.refresh)
            games.append(parse_summary(payload, cities))
        except Exception as exc:
            failures.append({"game_id": event_id, "error": f"{type(exc).__name__}: {exc}"})
        if index % 20 == 0:
            print(f"Checked {index}/{len(events)} games; {len(failures)} failures", flush=True)
    coverage = {"start": args.start, "end": args.end, "discovered": len(events), "parsed": len(games),
                "failures": failures, "exclusions": exclusions, "sources": client.manifest,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "geonames_sha256": hashlib.sha256(args.cities.read_bytes()).hexdigest()}
    write_json(args.output / "coverage.json", coverage)
    write_json(args.output / "games.json", games)
    if failures:
        print(json.dumps(failures, indent=2))
        raise SystemExit("Incomplete collection: coverage report saved; replay not published")
    result = replay(games, evaluate_from=args.evaluate_from)
    write_json(args.output / "replay.json", result)
    if args.publish_archive:
        print("Published season", publish_archive(args.publish_archive, result, games, coverage))
    print(json.dumps({"coverage": {k: coverage[k] for k in ["discovered", "parsed"]},
                      "metrics": result["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
