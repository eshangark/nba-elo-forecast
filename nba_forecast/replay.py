"""Conservative daily-cutoff historical replay and probability metrics."""

import hashlib
import json
import math
from dataclasses import asdict
from datetime import datetime, time
from itertools import groupby
from statistics import mean

from .model import EASTERN, Engine, MODEL_VERSION, slate_date, timestamp


def metrics(rows):
    if not rows:
        return {"games": 0, "log_loss": None, "brier_score": None, "winner_accuracy": None, "calibration": []}
    losses = []
    for r in rows:
        p = max(1e-12, min(1 - 1e-12, r["home_probability"]))
        y = r["home_win"]
        losses.append(-(y * math.log(p) + (1-y) * math.log1p(-p)))
    bins = []
    for i in range(10):
        bucket = [r for r in rows if min(9, int(r["home_probability"] * 10)) == i]
        if bucket:
            bins.append({"lower": i / 10, "upper": (i+1) / 10, "games": len(bucket),
                         "mean_probability": mean(r["home_probability"] for r in bucket),
                         "observed_home_win_rate": mean(r["home_win"] for r in bucket)})
    return {"games": len(rows), "log_loss": mean(losses),
            "brier_score": mean((r["home_probability"] - r["home_win"])**2 for r in rows),
            "winner_accuracy": mean(int(r["home_probability"] >= 0.5) == r["home_win"] for r in rows),
            "tie_policy": "pick home when probability equals 0.5", "calibration": bins}


def replay(games, params=None, evaluate_from=None):
    if not games:
        raise ValueError("No games to replay")
    if len({g["game_id"] for g in games}) != len(games):
        raise ValueError("Duplicate game IDs")
    if len({g["season"] for g in games}) != 1:
        raise ValueError("Pilot supports one season; season carryover is not implemented")
    games = sorted(games, key=lambda g: (timestamp(g["start"]), g["game_id"]))
    engine = Engine(params)
    names = {g[s]["id"]: g[s]["name"] for g in games for s in ["home", "away"]}
    # Roster identities contain no game results; use the same starting universe throughout.
    for team_id in names:
        engine.team(team_id)
    predictions = []
    last_completion = None
    for day, batch_iterator in groupby(games, slate_date):
        batch = list(batch_iterator)
        cutoff = datetime.combine(day, time(10), tzinfo=EASTERN)
        if last_completion and last_completion >= cutoff:
            raise ValueError("Previous slate was not complete at forecast cutoff")
        if any(timestamp(g["start"]) <= cutoff for g in batch):
            raise ValueError("Early game precedes daily cutoff; choose an explicit alternate policy")
        if any(not g.get("last_play_at") for g in batch):
            raise ValueError("Missing final-play timestamp: availability cannot be checked")
        team_ids = [g[s]["id"] for g in batch for s in ["home", "away"]]
        if len(team_ids) != len(set(team_ids)):
            raise ValueError("Multiple games for one team on the same slate")
        forecasts = [engine.predict(g) for g in batch]
        for g, row in zip(batch, forecasts):
            row.update(forecast_cutoff=cutoff.isoformat(), kind="historical_replay",
                       home_win=int(g["home"]["points"] > g["away"]["points"]),
                       home_score=g["home"]["points"], away_score=g["away"]["points"])
            engine.update(g, row)
            predictions.append(row)
        engine.recenter()
        for g, row in zip(batch, forecasts):
            for side in ["home", "away"]:
                row[side + "_rating_after"] = engine.team(g[side]["id"]).rating
                row[side + "_rating_change"] = row[side + "_rating_after"] - row[side + "_rating"]
        last_completion = max(timestamp(g["last_play_at"]) for g in batch)
    evaluated = [p for p in predictions if not evaluate_from or slate_date(p).isoformat() >= evaluate_from]
    return {"model_version": MODEL_VERSION, "status": "unfitted_pipeline_pilot",
            "parameters": asdict(engine.params), "cutoff_policy": "10:00 America/New_York; prior slates only",
            "start": games[0]["start"], "end": games[-1]["start"], "evaluation_from": evaluate_from,
            "dataset_sha256": hashlib.sha256(json.dumps(games, sort_keys=True).encode()).hexdigest(),
            "limitations": ["Parameters not fitted on NBA data", "Short historical sample, not final test performance",
                            "Cold-start ratings", "City-centre travel estimates", "Historical source corrections may be present"],
            "metrics": metrics(evaluated), "predictions": predictions,
            "rankings": sorted([{"team_id": k, "team": names[k], "elo": v.rating, "games": v.games,
                                  "wins": v.wins} for k,v in engine.teams.items()], key=lambda r: -r["elo"])}
