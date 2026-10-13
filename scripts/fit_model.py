"""Fit on 2021–24 history; freeze before validation and the 2025–26 test."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nba_forecast.data import write_json
from nba_forecast.fitting import fit
from nba_forecast.replay import replay


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--maxiter",type=int,default=150)
    args=parser.parse_args()
    # Load only training seasons before fitting; keep hold-out files outside the objective.
    training=[]
    for year in [2022,2023,2024]:
        audit=json.loads((args.history/f"audit_{year}.json").read_text())
        if audit["failures"] or audit["invalid_team_counts"] or audit["accepted_games"]!=1230:
            raise ValueError(f"Unaudited training season {year}")
        training.append(json.loads((args.history/f"games_{year}.json").read_text()))
    params,report=fit(training,seed=args.seed,maxiter=args.maxiter)
    report["frozen_at"]=datetime.now(timezone.utc).isoformat()
    write_json(args.output/"parameters.json",asdict(params))
    write_json(args.output/"fit_report.json",report)
    for year,role in [(2022,"training"),(2023,"training"),(2024,"training"),(2025,"validation"),(2026,"held_out_test")]:
        audit=json.loads((args.history/f"audit_{year}.json").read_text())
        if audit["failures"] or audit["invalid_team_counts"] or audit["accepted_games"]!=1230:
            raise ValueError(f"Unaudited evaluation season {year}")
        raw=(args.history/f"games_{year}.json").read_bytes()
        games=json.loads(raw)
        result=replay(games,params,fitted=True,warmup_games=10)
        result.update(evaluation_role=role,parameters_frozen_at=report["frozen_at"])
        report.setdefault("seasons",{})[str(year)]={"role":role,"metrics":result["metrics"],
                                                   "games":len(games),"data_file_sha256":hashlib.sha256(raw).hexdigest()}
        write_json(args.output/f"replay_{year}.json",result)
        print(year,role,json.dumps(result["metrics"]),flush=True)
    write_json(args.output/"fit_report.json",report)


if __name__=="__main__":main()
