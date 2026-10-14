"""Deterministic rating engine; fitted configurations are loaded explicitly."""

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo

MODEL_VERSION = "0.2.0"
ALPHA_BASE = (0.25, 0.20, 0.15, 0.10, 0.10, 0.10, 0.05, 0.05)
EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Parameters:
    k: float = 32.0
    # Fix b=10 while preserving the original report's rating/fatigue log-odds scales.
    c: float = 993.39 * math.log(10) / math.log(99.39)
    home_advantage: float = 72.52
    fatigue_weight: float = 0.02 * math.log(99.39) / math.log(10)
    travel_weight: float = 0.000001
    lead_weight: float = 0.7
    performance_weight: float = 0.02
    schedule_weight: float = 1.0
    alpha_weights: tuple = ALPHA_BASE

    def __post_init__(self):
        values = [v for k,v in asdict(self).items() if k != "alpha_weights"] + list(self.alpha_weights)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Parameters must be finite")
        if self.k <= 0 or self.c <= 0 or min(self.home_advantage, self.fatigue_weight,
                                          self.travel_weight, self.lead_weight) < 0:
            raise ValueError("Invalid parameter domain")
        if not 0 <= self.performance_weight <= 0.25:
            raise ValueError("Performance weight must be in [0, 0.25]")
        if not 0 <= self.schedule_weight <= 1:
            raise ValueError("Schedule weight must be in [0, 1]")
        if len(self.alpha_weights) != 8 or min(self.alpha_weights) < 0 or abs(sum(self.alpha_weights)-1) > 1e-9:
            raise ValueError("Eight nonnegative performance weights must sum to one")


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return result


def slate_date(game):
    return timestamp(game["start"]).astimezone(EASTERN).date()


def logistic(value):
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    e = math.exp(value)
    return e / (1 + e)


def distance(a, b):
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dlat = lat2 - lat1
    dlon = math.radians(b["longitude"] - a["longitude"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1, max(0, h))))


def box_features(team, opponent):
    poss = team["fga"] + 0.44 * team["fta"] - team["oreb"] + team["tov"]
    opp_poss = opponent["fga"] + 0.44 * opponent["fta"] - opponent["oreb"] + opponent["tov"]
    denominators = [poss, opp_poss, team["fga"], team["fga"] + 0.44 * team["fta"],
                    team["oreb"] + opponent["dreb"], team["dreb"] + opponent["oreb"]]
    if min(denominators) <= 0:
        raise ValueError("Undefined box-score feature denominator")
    return [
        100 * (team["points"] - opponent["points"]) / poss,
        (team["fgm"] + 0.5 * team["threem"]) / team["fga"],
        team["points"] / (2 * (team["fga"] + 0.44 * team["fta"])),
        team["oreb"] / (team["oreb"] + opponent["dreb"]),
        team["dreb"] / (team["dreb"] + opponent["oreb"]),
        team["ast"] / max(team["tov"], 1),
        team["tov"] / (team["fga"] + 0.44 * team["fta"] + team["tov"]),
        team["stl"] / opp_poss,
    ]


def performance(team, opponent, weights=ALPHA_BASE):
    x = box_features(team, opponent)
    # Fixed, documented units; no sample-wide statistics or future-data scaling.
    scaled = [x[0] / 10, x[1], x[2], x[3], x[4], x[5] / 3, -x[6], x[7]]
    return max(1e-6, min(1 - 1e-6, logistic(sum(a * b for a, b in zip(weights, scaled)))))


@dataclass
class TeamState:
    rating: float = 1500.0
    wins: int = 0
    games: int = 0
    opponents: list = field(default_factory=list)
    performances: list = field(default_factory=list)
    last_start: str | None = None
    last_location: dict | None = None

    @property
    def win_rate(self):
        return (self.wins + 1) / (self.games + 2)


class Engine:
    def __init__(self, params=None):
        self.params = params or Parameters()
        self.teams = {}
        self.processed = set()

    def team(self, identifier):
        return self.teams.setdefault(identifier, TeamState())

    def context(self, team_id, game):
        state = self.team(team_id)
        if state.last_start is None:
            return {"rest": 3, "travel": 0.0, "timezone_change": 0.0, "opening_prior": True}
        current = timestamp(game["start"])
        previous = timestamp(state.last_start)
        if previous >= current:
            raise ValueError("Rating history is not strictly before this game")
        # Evaluate both locations at the same instant: DST transitions alone are not travel.
        old_offset = current.astimezone(ZoneInfo(state.last_location["timezone"])).utcoffset()
        new_offset = current.astimezone(ZoneInfo(game["location"]["timezone"])).utcoffset()
        return {"rest": max(0, (current.astimezone(EASTERN).date() - previous.astimezone(EASTERN).date()).days - 1),
                "travel": distance(state.last_location, game["location"]),
                "timezone_change": (new_offset - old_offset).total_seconds() / 3600,
                "opening_prior": False}

    def sos(self, opponent_id):
        opponent = self.team(opponent_id)
        other_rates = [self.team(t).win_rate for t in opponent.opponents]
        return (2 * opponent.win_rate + (mean(other_rates) if other_rates else 0.5)) / 3

    def predict(self, game):
        home = self.team(game["home"]["id"])
        away = self.team(game["away"]["id"])
        hc = self.context(game["home"]["id"], game)
        ac = self.context(game["away"]["id"], game)
        p = self.params
        ortf = ac["rest"] + math.exp(abs(hc["timezone_change"]) / 3) + p.travel_weight * hc["travel"]
        trof = hc["rest"] + math.exp(abs(ac["timezone_change"]) / 3) + p.travel_weight * ac["travel"]
        logodds = math.log(10) * ((home.rating - away.rating + (0 if game["neutral"] else p.home_advantage)) / p.c
                                    - p.fatigue_weight * math.log(ortf / trof))
        probability = logistic(logodds)
        return {"game_id": game["game_id"], "start": game["start"],
                "home": game["home"]["name"], "away": game["away"]["name"],
                "home_rating": home.rating, "away_rating": away.rating,
                "home_probability": probability, "away_probability": 1 - probability,
                "home_context": hc, "away_context": ac,
                "home_sos": self.sos(game["away"]["id"]), "away_sos": self.sos(game["home"]["id"]),
                "model_version": MODEL_VERSION}

    def update(self, game, prediction):
        if game["game_id"] in self.processed:
            raise ValueError("Game already processed")
        if prediction["game_id"] != game["game_id"]:
            raise ValueError("Forecast/game mismatch")
        margin = abs(game["home"]["points"] - game["away"]["points"])
        if margin == 0:
            raise ValueError("Final NBA game cannot be tied")
        # Peak absolute lead yields a bounded feature for both winners and losers.
        peak = max(game["home"]["largest_lead"], game["away"]["largest_lead"])
        if peak < margin:
            raise ValueError("Largest lead inconsistent with final score")
        lead_ratio = margin / peak
        pending = []
        for side, other in [("home", "away"), ("away", "home")]:
            state = self.team(game[side]["id"])
            win = int(game[side]["points"] > game[other]["points"])
            sign = 2 * win - 1
            current = performance(game[side], game[other], self.params.alpha_weights)
            baseline = mean(state.performances) if state.performances else current
            ratio = max(0.25, min(4.0, current / baseline))
            p = self.params
            delta = p.k * (win - prediction[side + "_probability"]) * (1 + sign * p.schedule_weight * prediction[side + "_sos"])
            delta *= (1 + p.lead_weight * math.log2(1 + lead_ratio)) * (1 + sign * p.performance_weight * (ratio - 1))
            pending.append((state, side, other, win, current, delta))
        # Commit both teams only after both calculations succeed.
        for state, side, other, win, current, delta in pending:
            state.rating += delta
            state.games += 1
            state.wins += win
            state.opponents.append(game[other]["id"])
            state.performances.append(current)
            state.last_start = game["start"]
            state.last_location = game["location"]
        self.processed.add(game["game_id"])

    def recenter(self):
        if self.teams:
            shift = mean(t.rating for t in self.teams.values()) - 1500
            for t in self.teams.values():
                t.rating -= shift
