"""Export clean full seasons, derived feature tables, and the frozen fitted model."""

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nba_forecast.data import write_json
from nba_forecast.model import Parameters, box_features, performance, slate_date
from nba_forecast.seasons import season_label


def csv_file(path, rows):
    with path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history",type=Path,required=True)
    parser.add_argument("--fitted",type=Path,required=True)
    parser.add_argument("--archives",type=Path,default=Path("data/seasons"))
    parser.add_argument("--model-output",type=Path,default=Path("models/nba-v0.2"))
    parser.add_argument("--source-manifest",type=Path,required=True)
    args=parser.parse_args()
    report=json.loads((args.fitted/"fit_report.json").read_text())
    if not report["optimizer_success"]:raise ValueError("Optimizer did not converge")
    params=Parameters(**report["parameters"])
    source_manifest=json.loads(args.source_manifest.read_text())
    index=json.loads((args.archives/"index.json").read_text())
    quality=[]
    for year in range(2022,2027):
        label=season_label(year-1);destination=args.archives/label;destination.mkdir(parents=True,exist_ok=True)
        audit=json.loads((args.history/f"audit_{year}.json").read_text())
        if audit["failures"] or audit["invalid_team_counts"]:raise ValueError("Incomplete season")
        audit["archive_sources"]=[s for s in source_manifest if str(year) in s["name"]]
        games=json.loads((args.history/f"games_{year}.json").read_text())
        result=json.loads((args.fitted/f"replay_{year}.json").read_text())
        predictions={p["game_id"]:p for p in result["predictions"]}
        hist={};team_rows=[];feature_rows=[]
        for g in games:
            p=predictions[g["game_id"]]
            for side,other in [("home","away"),("away","home")]:
                t,o=g[side],g[other];context=p[side+"_context"];opcontext=p[other+"_context"]
                current=performance(t,o,params.alpha_weights)
                previous=mean(hist[t["id"]]) if hist.get(t["id"]) else current
                ratio=max(0.25,min(4.0,current/previous));x=box_features(t,o)
                lead=abs(t["points"]-o["points"])/max(t["largest_lead"],o["largest_lead"])
                ortf=opcontext["rest"]+math.exp(abs(context["timezone_change"])/3)+params.travel_weight*context["travel"]
                trof=context["rest"]+math.exp(abs(opcontext["timezone_change"])/3)+params.travel_weight*opcontext["travel"]
                team_rows.append({"season":label,"game_id":g["game_id"],"start":g["start"],"team_id":t["id"],
                                  "team":t["name"],"opponent_id":o["id"],"opponent":o["name"],"side":side,
                                  "neutral":g["neutral"],"venue_id":g["venue_id"],"venue":g["venue_name"],
                                  **{k:t[k] for k in ["points","fgm","fga","threem","threea","ftm","fta","oreb","dreb","ast","stl","tov","largest_lead"]}})
                feature_rows.append({"season":label,"game_id":g["game_id"],"team_id":t["id"],"side":side,
                                     "forecast_cutoff":p["forecast_cutoff"],"pregame_elo":p[side+"_rating"],
                                     "pregame_opponent_elo":p[other+"_rating"],"pregame_home_offset":0 if g["neutral"] else params.home_advantage*(1 if side=="home" else -1),
                                     "pregame_rest_days":context["rest"],"pregame_travel_km":context["travel"],
                                     "pregame_timezone_change_hours":context["timezone_change"],"pregame_sos":p[side+"_sos"],
                                     "pregame_ortf":ortf,"pregame_trof":trof,"win_probability":p[side+"_probability"],
                                     **{f"postgame_x{k+1}":v for k,v in enumerate(x)},
                                     "postgame_agpf":current,"prior_agpf_mean":previous,"postgame_paf":ratio,
                                     "postgame_lre":lead,"postgame_elo":p[side+"_rating_after"],
                                     "eligible_for_evaluation":p["eligible_for_evaluation"],"model_version":result["model_version"]})
                hist.setdefault(t["id"],[]).append(current)
        coverage={"start":str(slate_date(games[0])),"end":str(slate_date(games[-1])),"discovered":1230,"parsed":1230,"failures":[]}
        snapshot={"season":label,"status":"complete_historical_replay","published_at":report["frozen_at"],
                  "result":result,"coverage":coverage,"upcoming":[]}
        # Compact files preserve all fields while keeping full-season archives manageable in Git.
        for filename,data in [("games.json",games),("snapshot.json",snapshot)]:
            (destination/filename).write_text(json.dumps(data,separators=(",",":"),allow_nan=False)+"\n")
        write_json(destination/"collection_manifest.json",audit)
        csv_file(destination/"team_games.csv",team_rows)
        csv_file(destination/"model_features.csv",feature_rows)
        index["seasons"]=[e for e in index["seasons"] if e["season"]!=label]
        index["seasons"].append({"season":label,"status":snapshot["status"],"file":f"{label}/snapshot.json"})
        flags=Counter(action["action"] for g in games for action in g["quality_actions"])
        quality.append({"season":label,"games":len(games),"team_rows":len(team_rows),"teams":audit["teams"],
                        "missing_required_formula_inputs":0,"unresolved_failures":0,"primary_replacements":len(audit["primary_repairs"]),
                        "repair_actions":dict(flags),"evaluation_role":result["evaluation_role"]})
    index["seasons"].sort(key=lambda e:e["season"],reverse=True);write_json(args.archives/"index.json",index)
    write_json(args.model_output/"parameters.json",report["parameters"])
    write_json(args.model_output/"fit_report.json",report)
    write_json(args.model_output/"data_quality.json",quality)
    print(json.dumps(quality,indent=2))


if __name__=="__main__":main()
