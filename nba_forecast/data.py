"""Free-source ingestion with raw caching and explicit schema validation."""

import hashlib
import json
import math
import time
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


class Client:
    """One request at a time; retry transient failures, never access denials."""

    def __init__(self, cache, pause=0.3):
        self.cache = Path(cache)
        self.pause = pause
        self.manifest = []

    def get(self, endpoint, query, refresh=False):
        url = f"{BASE}/{endpoint}?{query}"
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / f"{key}.json"
        if path.exists() and not refresh:
            envelope = json.loads(path.read_text())
        else:
            for attempt in range(3):
                time.sleep(self.pause)
                try:
                    with urlopen(url, timeout=20) as response:
                        raw = response.read()
                    envelope = {
                        "url": url,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "data": json.loads(raw),
                    }
                    write_json(path, envelope)
                    break
                except HTTPError as exc:
                    if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                        raise
                    time.sleep(2 ** (attempt + 1))
                except (URLError, TimeoutError):
                    if attempt == 2:
                        raise
                    time.sleep(2 ** (attempt + 1))
        self.manifest.append({k: envelope[k] for k in ("url", "retrieved_at", "sha256")})
        return envelope["data"]


def normalized_name(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text).casefold()
                   if not unicodedata.combining(c)).strip()


class Cities:
    """GeoNames city-centre travel proxy, not exact arena coordinates."""

    def __init__(self, archive):
        self.rows = []
        with zipfile.ZipFile(archive) as z:
            for line in z.read("cities15000.txt").decode("utf-8").splitlines():
                f = line.split("\t")
                self.rows.append({
                    "id": f[0], "name": f[1], "aliases": {normalized_name(x) for x in [f[1], f[2], *f[3].split(",")]},
                    "latitude": float(f[4]), "longitude": float(f[5]),
                    "country": f[8], "state": f[10], "population": int(f[14]), "timezone": f[17],
                })

    def resolve(self, address):
        city = normalized_name(address["city"])
        state = address.get("state", "")
        # ESPN uses state abbreviations for US venues and country for overseas venues.
        country = address.get("country", "")
        country = {"USA": "US", "United States": "US", "Canada": "CA", "Mexico": "MX"}.get(country, country)
        candidates = [r for r in self.rows if city in r["aliases"]]
        if state and len(state) == 2 and state not in {"ON", "BC", "QC"}:
            candidates = [r for r in candidates if r["country"] == "US" and r["state"] == state]
        elif country:
            candidates = [r for r in candidates if r["country"] == country]
        elif state in {"ON", "BC", "QC"}:
            candidates = [r for r in candidates if r["country"] == "CA"]
        if not candidates:
            raise ValueError(f"Unresolved venue city: {address}")
        candidates.sort(key=lambda r: r["population"], reverse=True)
        # Require an unambiguous name/state/country match; no silent geographic guess.
        if len(candidates) != 1:
            raise ValueError(f"Ambiguous venue city: {address}: {[r['id'] for r in candidates]}")
        r = candidates[0]
        return {k: r[k] for k in ("id", "name", "latitude", "longitude", "timezone")}


def integer(value, field):
    number = float(value)
    if not math.isfinite(number) or number < 0 or number != int(number):
        raise ValueError(f"Invalid {field}: {value}")
    return int(number)


def player_totals(payload, team_id):
    """Recover a contradictory team aggregate from complete player records."""
    player_box = next(b for b in payload["boxscore"]["players"] if b["team"]["id"] == team_id)
    table = player_box["statistics"][0]
    total = {k: 0 for k in ["points", "fgm", "fga", "threem", "threea", "ftm", "fta",
                           "oreb", "dreb", "ast", "stl", "tov"]}
    count = 0
    for athlete in table["athletes"]:
        values = athlete.get("stats", [])
        if not values:
            if not athlete.get("didNotPlay", False):
                raise ValueError("Missing stats for an active player")
            continue
        if len(values) != len(table["labels"]):
            raise ValueError("Incomplete player stat row")
        row = dict(zip(table["labels"], values))
        for label, field in [("PTS", "points"), ("OREB", "oreb"), ("DREB", "dreb"),
                             ("AST", "ast"), ("STL", "stl"), ("TO", "tov")]:
            total[field] += integer(row[label], label)
        for label, prefix in [("FG", "fg"), ("3PT", "three"), ("FT", "ft")]:
            made, attempted = row[label].split("-")
            total[prefix + "m"] += integer(made, label)
            total[prefix + "a"] += integer(attempted, label)
        count += 1
    if count < 5:
        raise ValueError("Too few player records to recover team totals")
    return total


def parse_summary(payload, cities):
    header = payload["header"]
    competition = header["competitions"][0]
    if not competition["status"]["type"]["completed"]:
        raise ValueError("Game is not completed")
    if int(header["season"]["type"]) != 2:
        raise ValueError("Only regular-season games supported in this pilot")
    venue = payload["gameInfo"]["venue"]
    location = cities.resolve(venue["address"])
    competitors = {c["homeAway"]: c for c in competition["competitors"]}
    if set(competitors) != {"home", "away"}:
        raise ValueError("Expected one home and one away team")
    boxes = {b["team"]["id"]: b for b in payload["boxscore"]["teams"]}
    game = {
        "game_id": str(header["id"]), "start": competition["date"],
        "season": int(header["season"]["year"]), "season_type": 2,
        "neutral": bool(competition.get("neutralSite", False)),
        "venue_id": str(venue["id"]), "venue_name": venue["fullName"],
        "location": location,
        "source": f"{BASE}/summary?event={header['id']}",
        "quality_actions": [],
    }
    plays = payload.get("plays", [])
    score_path = [(integer(p["homeScore"], "homeScore"), integer(p["awayScore"], "awayScore"))
                  for p in sorted(plays, key=lambda p: int(p.get("sequenceNumber", 0)))
                  if "homeScore" in p and "awayScore" in p]
    expected_final = tuple(integer(competitors[s]["score"], "score") for s in ["home", "away"])
    valid_score_path = bool(score_path and score_path[-1] == expected_final)
    for side, competitor in competitors.items():
        team_id = competitor["team"]["id"]
        stats = {s["name"]: s["displayValue"] for s in boxes[team_id]["statistics"]}
        team = {"id": str(team_id), "name": competitor["team"]["displayName"],
                "points": integer(competitor["score"], "points")}
        for field, source in [("fg", "fieldGoalsMade-fieldGoalsAttempted"),
                              ("three", "threePointFieldGoalsMade-threePointFieldGoalsAttempted"),
                              ("ft", "freeThrowsMade-freeThrowsAttempted")]:
            made, attempted = stats[source].split("-")
            team[field + "m"] = integer(made, source)
            team[field + "a"] = integer(attempted, source)
            if team[field + "m"] > team[field + "a"]:
                raise ValueError(f"Made shots exceed attempts: {team_id}")
        for field, source in [("oreb", "offensiveRebounds"), ("dreb", "defensiveRebounds"),
                              ("ast", "assists"), ("stl", "steals"),
                              ("tov", "totalTurnovers")]:
            team[field] = integer(stats[source], source)
        if team["points"] != 2 * team["fgm"] + team["threem"] + team["ftm"]:
            recovered = player_totals(payload, team_id)
            if recovered["points"] != team["points"] or recovered["points"] != 2 * recovered["fgm"] + recovered["threem"] + recovered["ftm"]:
                raise ValueError(f"Both team and player totals contradict final score: {team_id}")
            if not valid_score_path:
                raise ValueError("Cannot verify recovery against final play-by-play score")
            # Non-player turnovers have no athlete participants in this feed.
            team_turnovers = sum(1 for p in plays if p.get("team", {}).get("id") == team_id
                                 and "turnover" in p.get("text", "").lower()
                                 and not p.get("participants"))
            recovered["tov"] += team_turnovers
            team.update(recovered)
            game["quality_actions"].append({"team_id": team_id, "action": "recovered_player_totals",
                                             "team_turnovers_from_plays": team_turnovers})
        if "largestLead" in stats:
            team["largest_lead"] = integer(stats["largestLead"], "largestLead")
        elif valid_score_path:
            index = 0 if side == "home" else 1
            team["largest_lead"] = max(0, max(s[index] - s[1-index] for s in score_path))
            game["quality_actions"].append({"team_id": team_id, "action": "largest_lead_from_plays"})
        else:
            raise ValueError("Largest lead missing and no validated final score path")
        if team["threem"] > team["fgm"] or team["threea"] > team["fga"]:
            raise ValueError("Three-point totals exceed field-goal totals")
        game[side] = team
    if game["home"]["id"] == game["away"]["id"] or game["home"]["points"] == game["away"]["points"]:
        raise ValueError("Invalid opponents or tied final score")
    winner = game["home"] if game["home"]["points"] > game["away"]["points"] else game["away"]
    if winner["largest_lead"] < abs(game["home"]["points"] - game["away"]["points"]):
        raise ValueError("Largest lead cannot be smaller than the winning margin")
    # Final event time is an availability proxy, not the historical data publication time.
    wallclocks = [p["wallclock"] for p in payload.get("plays", []) if p.get("wallclock")]
    game["last_play_at"] = max(wallclocks) if wallclocks else None
    return game
