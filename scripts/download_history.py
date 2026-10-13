"""Download free SportsDataverse ESPN archives with reproducible source hashes."""

import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import urlopen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("data/raw/history"))
    parser.add_argument("--years",type=int,nargs="+",default=[2022,2023,2024,2025,2026])
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    sources=[]
    for year in args.years:
        for tag,prefix in [("espn_nba_team_boxscores","team_box"),("espn_nba_schedules","nba_schedule"),("espn_nba_pbp","play_by_play")]:
            name=f"{prefix}_{year}.parquet"
            url=f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/{tag}/{name}"
            path=args.output/name
            if not path.exists():
                with urlopen(url,timeout=60) as r:raw=r.read()
                temporary=path.with_suffix(".tmp");temporary.write_bytes(raw);temporary.replace(path)
            sources.append({"name":name,"url":url,"bytes":path.stat().st_size,
                            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                            "retrieved_at":datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()})
            print(name,flush=True)
    (args.output/"downloads.json").write_text(json.dumps(sources,indent=2)+"\n")


if __name__=="__main__":main()
