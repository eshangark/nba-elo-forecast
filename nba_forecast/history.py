"""Normalize season-level ESPN archives and audit every model input."""

import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .data import Cities, Client, integer, parse_summary, write_json
from .model import timestamp
from .validation import validate_game

STAT_MAP = {"points": "team_score", "fgm": "field_goals_made", "fga": "field_goals_attempted",
            "threem": "three_point_field_goals_made", "threea": "three_point_field_goals_attempted",
            "ftm": "free_throws_made", "fta": "free_throws_attempted", "oreb": "offensive_rebounds",
            "dreb": "defensive_rebounds", "ast": "assists", "stl": "steals", "tov": "turnovers"}
COUNTRIES = {"Paris": "FR", "Mexico City": "MX", "London": "GB", "Berlin": "DE"}


def regular_schedule(schedule):
    # ESPN labels All-Star games and Cup finals as season_type=2 in some archives.
    eligible = schedule[(schedule.season_type == 2) & (schedule.status_type_completed == True)
                        & (schedule.type_abbreviation == "STD")].copy()
    if eligible.id.duplicated().any():
        raise ValueError("Duplicate eligible schedule IDs")
    return eligible



def build_season(year, archive_dir, cities_path, cache_dir, output_dir):
    archive_dir, output_dir = Path(archive_dir), Path(output_dir)
    schedule = pd.read_parquet(archive_dir / f"nba_schedule_{year}.parquet")
    boxes = pd.read_parquet(archive_dir / f"team_box_{year}.parquet")
    columns = ["game_id", "sequence_number", "home_score", "away_score", "wallclock"]
    plays = pd.read_parquet(archive_dir / f"play_by_play_{year}.parquet", columns=columns)
    eligible = regular_schedule(schedule)
    cities, client = Cities(cities_path), Client(cache_dir)
    boxes = {str(int(g)): table for g, table in boxes.groupby("game_id")}
    paths = {str(int(g)): table.sort_values("sequence_number") for g, table in plays.groupby("game_id")}
    games, failures, repairs = [], [], []
    for row in eligible.sort_values("date").to_dict("records"):
        game_id = str(int(row["id"]))
        try:
            table = boxes[game_id]
            if len(table) != 2 or table.team_id.nunique() != 2:
                raise ValueError("Expected two unique team box scores")
            path = paths[game_id]
            final = path.iloc[-1]
            if (int(final.home_score), int(final.away_score)) != (int(row["home_score"]), int(row["away_score"])):
                raise ValueError("Play-by-play final score disagrees with schedule")
            address = {"city": row["venue_address_city"]}
            if pd.notna(row.get("venue_address_state")):
                address["state"] = row["venue_address_state"]
            if address["city"] in COUNTRIES:
                address["country"] = COUNTRIES[address["city"]]
            game = {"game_id": game_id, "start": row["date"], "season": year, "season_type": 2,
                    "neutral": bool(row["neutral_site"]), "venue_id": str(int(row["venue_id"])),
                    "venue_name": row["venue_full_name"], "location": cities.resolve(address),
                    "source": f"SportsDataverse ESPN archive, season {year}", "quality_actions": [],
                    "last_play_at": final.wallclock}
            for side in ["home", "away"]:
                record = table[table.team_home_away == side].iloc[0]
                if int(record.team_id) != int(row[side + "_id"]):
                    raise ValueError("Schedule and box-score opponents disagree")
                t = {"id": str(int(record.team_id)), "name": record.team_display_name}
                t.update({field: integer(record[source], field) for field, source in STAT_MAP.items()})
                if t["points"] != int(row[side + "_score"]):
                    raise ValueError("Schedule and box-score scores disagree")
                if pd.isna(record.largest_lead):
                    differences = path.home_score - path.away_score
                    t["largest_lead"] = max(0, int((differences if side == "home" else -differences).max()))
                    game["quality_actions"].append({"team_id": t["id"], "action": "largest_lead_from_archive_plays"})
                else:
                    t["largest_lead"] = integer(record.largest_lead, "largest_lead")
                game[side] = t
            validate_game(game)
        except Exception as exc:
            original_error = f"{type(exc).__name__}: {exc}"
            try:
                payload = client.get("summary", "event=" + game_id)
                game = parse_summary(payload, cities)
                validate_game(game)
                repairs.append({"game_id": game_id, "archive_error": original_error,
                                "resolution": "validated_primary_ESPN_summary", "actions": game["quality_actions"]})
            except Exception as replacement_error:
                failures.append({"game_id": game_id, "archive_error": original_error,
                                 "primary_error": f"{type(replacement_error).__name__}: {replacement_error}"})
                continue
        games.append(game)
    games.sort(key=lambda g: (timestamp(g["start"]), g["game_id"]))
    counts = Counter(t["id"] for g in games for t in [g["home"], g["away"]])
    invalid_counts = {k:v for k,v in counts.items() if v != 82}
    audit = {"season": year, "eligible_schedule_games": len(eligible), "accepted_games": len(games),
             "teams": len(counts), "team_game_counts": dict(sorted(counts.items())),
             "invalid_team_counts": invalid_counts, "failures": failures, "primary_repairs": repairs,
             "excluded": schedule[~schedule.id.isin(eligible.id)][["id","season_type","type_abbreviation"]].to_dict("records"),
             "collected_at": datetime.now(timezone.utc).isoformat(), "primary_sources": client.manifest,
             "archive_sources": [{"filename": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
                                 for f in [archive_dir/f"nba_schedule_{year}.parquet", archive_dir/f"team_box_{year}.parquet",
                                           archive_dir/f"play_by_play_{year}.parquet"]],
             "geonames_sha256": hashlib.sha256(Path(cities_path).read_bytes()).hexdigest()}
    write_json(output_dir/f"audit_{year}.json", audit)
    write_json(output_dir/f"games_{year}.json", games)
    print(f"{year}: {len(games)}/{len(eligible)} games; {len(repairs)} primary repairs; {len(failures)} failures", flush=True)
    if failures or invalid_counts or len(counts) != 30 or len(games) != 1230:
        raise ValueError(f"Season {year} failed completeness audit; see audit_{year}.json")
    return games, audit
