"""Probe free NBA sources without credentials or paid dependencies.

This is a connectivity/schema check, not an ingestion pipeline or coverage proof.
Run: python scripts/probe_sources.py --output work/source-probe
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


def endpoints(season, game_id):
    query = urlencode(dict(Counter=0, DateFrom="", DateTo="", Direction="ASC",
                           LeagueID="00", PlayerOrTeam="T", Season=season,
                           SeasonType="Regular Season", Sorter="DATE"))
    return {
        "game_log": "https://stats.nba.com/stats/leaguegamelog?" + query,
        "schedule": "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json",
        "box_score": f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json",
    }


def summarize(name, data):
    if name == "game_log":
        table = next(t for t in data["resultSets"] if t["name"] == "LeagueGameLog")
        required = {"GAME_ID", "TEAM_ID", "GAME_DATE", "PTS", "FGM", "FGA",
                    "FG3M", "FTA", "OREB", "DREB", "AST", "TOV", "STL"}
        missing = sorted(required - set(table["headers"]))
        rows = table["rowSet"]
        if missing or not rows:
            raise ValueError(f"Missing fields: {missing}; rows: {len(rows)}")
        return {"rows": len(rows), "headers": table["headers"]}
    if name == "schedule":
        dates = data["leagueSchedule"]["gameDates"]
        count = sum(len(d["games"]) for d in dates)
        if not count:
            raise ValueError("Empty schedule")
        return {"games": count}
    game = data["game"]
    return {"game_id": game["gameId"], "status": game["gameStatus"],
            "home_stat_fields": sorted(game["homeTeam"]["statistics"]),
            "away_stat_fields": sorted(game["awayTeam"]["statistics"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--game-id", default="0022400001")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--output", type=Path, default=Path("work/source-probe"))
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output / stamp
    destination.mkdir(parents=True)
    results = []
    for name, url in endpoints(args.season, args.game_id).items():
        result = {"source": name, "url": url,
                  "retrieved_at": datetime.now(timezone.utc).isoformat()}
        try:
            with urlopen(url, timeout=args.timeout) as response:
                raw = response.read()
                result["http_status"] = response.status
            data = json.loads(raw)
            (destination / f"{name}.json").write_bytes(raw)
            result["summary"] = summarize(name, data)
            result["ok"] = True
        except Exception as exc:
            result.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        results.append(result)
        print(json.dumps(result))
    (destination / "report.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0 if all(row["ok"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
