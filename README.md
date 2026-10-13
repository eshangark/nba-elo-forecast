# NBA Elo Forecast

An NBA forecasting project using dynamic team ratings and pregame win probabilities, informed by a multifactor Elo and Bradley–Terry framework developed for the 2025 Wharton competition.

## Project status

Research and development. A working Python pipeline and Streamlit season browser are available. The initial 2024–25 archive contains 151 verified games from October 22 through November 10, 2024. Parameters are unfitted starting values; the archive is a pipeline pilot and contains reconstructed historical predictions. Full-season collection, parameter estimation, live forecasting, and deployment are pending.

## Application

- **Teams:** ratings, rating changes, and historical trajectories.
- **Games:** upcoming win probabilities and archived pregame forecasts alongside outcomes.
- **Methodology:** equations, feature definitions, parameter estimation, and evaluation.

A season selector applies to all three views and defaults to the current season. The 2026–27 view currently shows initial ratings; it does not contain calibrated forecasts. The 2024–25 pilot is labeled as a partial archive.

## Run locally

Requires Python 3.10+.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app reads the versioned files under `data/seasons/`. It does not scrape or fit the model during page interactions.

## Reproduce the historical pilot

```sh
python scripts/download_geography.py
python scripts/run_pilot.py --cities data/raw/geography/cities15000.zip --publish-archive data/seasons
```

The collector caches raw responses, validates scores and statistics, records repairs, and refuses to publish an incomplete collection. The first run makes network requests; subsequent runs reuse the cache unless `--refresh` is specified. Historical provider data can change; the committed collection manifest records response hashes and the geography snapshot hash.

```sh
python -m unittest discover -s tests -v
```

Tests cover forecast timing, duplicate updates, signed features, actual source anomalies, and season switching. UI checks require Streamlit; they are skipped when only the core environment is available.

## Documentation

- [Technical manuscript](paper/main.tex) — self-contained LaTeX working draft.
- [Project plan](PROJECT_PLAN.md) — milestones and operational requirements.
- [Data specification](DATA_AND_FORMULAS.md) — inputs, inherited equations, and open implementation decisions.

The manuscript is maintained alongside substantive model and evaluation changes. Proposed methods and verified results are explicitly distinguished.

## Alternative data-source check

Requires Python 3.10+; no third-party dependencies or API keys.

```sh
python scripts/probe_sources.py --season 2024-25 --output work/source-probe
```

Responses and a report are saved in a timestamped local directory. Exit status 1 indicates at least one failed source check. Connectivity does not establish historical completeness. Raw data and temporary outputs are excluded from Git.

## Architecture

Python ingestion and rating updates produce saved model state and forecast history. Streamlit displays these outputs independently of the update process. Scheduling will be enabled after broader source coverage and model calibration.

Processed game histories, predictions, and collection manifests are versioned by season in GitHub. Large raw responses remain in the ignored collection cache. Pilot seasons reset to 1500 independently; season selection does not imply a fitted carryover model.

## Research provenance

The [original competition repository](https://github.com/aaravbora22/wharton_game_prediction_model) and team report inform this project. The NBA implementation will document its own conventions, fitted parameters, and validation. See the manuscript for attribution.

NBA source records come from ESPN's publicly accessible feeds. Venue-city coordinates and time zones are derived from [GeoNames](https://download.geonames.org/export/dump/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Travel estimates use city centres rather than exact arenas or team itineraries.

## Development constraints

Use free data and hosting within included allowances. Preserve historical forecasts independently of subsequent model refits. Keep credentials out of version control.
