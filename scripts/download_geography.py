"""Download the free GeoNames city-centre dataset used by the pilot."""

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

URL = "https://download.geonames.org/export/dump/cities15000.zip"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/raw/geography/cities15000.zip"))
    args = parser.parse_args()
    if not args.output.exists():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(URL, timeout=30) as response:
            raw = response.read()
        temporary = args.output.with_suffix(".tmp")
        temporary.write_bytes(raw)
        temporary.replace(args.output)
    print(f"GeoNames: {args.output}; sha256={hashlib.sha256(args.output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
