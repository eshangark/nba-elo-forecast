"""Shared validation for every completed game before a rating update."""

from .data import integer
from .model import box_features, timestamp


def validate_game(game):
    if game["home"]["id"] == game["away"]["id"]:
        raise ValueError("A team cannot play itself")
    margin = abs(game["home"]["points"] - game["away"]["points"])
    if margin == 0:
        raise ValueError("Tied final score")
    for side, opponent in [("home", "away"), ("away", "home")]:
        t = game[side]
        for field in ["points", "fgm", "fga", "threem", "threea", "ftm", "fta", "oreb", "dreb", "ast", "stl", "tov", "largest_lead"]:
            integer(t[field], field)
        if not (t["fgm"] <= t["fga"] and t["threem"] <= t["threea"] <= t["fga"]
                and t["threem"] <= t["fgm"] and t["ftm"] <= t["fta"]):
            raise ValueError("Impossible shooting totals")
        if t["points"] != 2*t["fgm"] + t["threem"] + t["ftm"]:
            raise ValueError("Scoring identity failure")
        if t["ast"] > t["fgm"] or t["stl"] > game[opponent]["tov"]:
            raise ValueError("Assists or steals contradict counterpart totals")
        box_features(t, game[opponent])
    winner = game["home"] if game["home"]["points"] > game["away"]["points"] else game["away"]
    if winner["largest_lead"] < margin:
        raise ValueError("Winning team's largest lead below final margin")
    end = timestamp(game["last_play_at"])
    start = timestamp(game["start"])
    if end <= start or (end-start).total_seconds() > 8*3600:
        raise ValueError("Invalid game completion timestamp")


