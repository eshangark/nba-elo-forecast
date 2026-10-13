# NBA Elo Forecast

Dynamic NBA ratings and pregame win probabilities, adapted from the team's 2025 Wharton competition framework.

## Current release

Model **0.2.0** is fitted to NBA regular-season history. The repository contains five complete seasons, **2021–22 through 2025–26**: 6,150 games and 12,300 team-game records. Every required numerical formula input passes validation. Historical forecasts are reconstructed replays, not predictions issued live.

Training uses 2021–22 through 2023–24. Parameters were frozen before evaluating 2024–25 (validation) and 2025–26 (held-out test). Both teams must have played ten games before a game contributes to the primary evaluation; all opening games still update ratings and retain forecasts.

| Season | Role | Scored games | Log loss | Brier score | Winner accuracy |
| --- | --- | ---: | ---: | ---: | ---: |
| 2021–22 | Training | 1,073 | 0.6298 | 0.2191 | 66.64% |
| 2022–23 | Training | 1,073 | 0.6457 | 0.2273 | 62.26% |
| 2023–24 | Training | 1,074 | 0.6092 | 0.2109 | 66.01% |
| 2024–25 | Validation | 1,075 | 0.6043 | 0.2088 | 66.42% |
| 2025–26 | Held-out test | 1,075 | 0.5925 | 0.2035 | 68.56% |

Log loss and Brier score evaluate probabilities; winner accuracy is a separate secondary measure. Calibration-bin counts are stored with each replay. One held-out season does not establish performance across all future seasons.

## Datasets and sources

Clean data is committed under [`data/seasons/`](data/seasons). Each historical season includes:

- `games.json`: validated games, venues, raw counts, completion-time proxies, and quality flags.
- `team_games.csv`: two clean box-score rows per game.
- `model_features.csv`: pregame inputs and probabilities, plus explicitly named postgame features for rating updates.
- `snapshot.json`: every reconstructed forecast, outcomes, final rankings, and evaluation.
- `collection_manifest.json`: coverage checks, source URLs/hashes, and primary-source replacements.

ESPN is the underlying sports-data source. [SportsDataverse](https://github.com/sportsdataverse/sportsdataverse-data) supplies free ESPN-derived schedule, team-box-score, and play-by-play archives. Incomplete or inconsistent archival records are replaced with validated primary ESPN game summaries. [GeoNames](https://download.geonames.org/export/dump/) supplies city coordinates and time zones. See [SOURCES.md](SOURCES.md) for attribution and limitations.

Raw parquet files and cached ESPN responses remain outside Git. The committed clean tables are the dataset used by this release. Travel estimates represent venue-city distances, not actual itineraries; one game uses an explicitly flagged conservative availability-time bound.

The frozen configuration, optimizer report, and quality summary are under [`models/nba-v0.2/`](models/nba-v0.2). Library `Parameters()` defaults are reference starting values; fitted replays explicitly load this configuration.

## Application

Streamlit has Teams, Games, and Methodology views, with a shared season selector defaulting to the current season. Historical seasons show ratings, reconstructed probabilities, outcomes, evaluation, and downloadable CSVs. The current 2026–27 view is initialized at 1500; live forecasts are not yet published. Native fixed dropdowns and light/dark themes are available.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app reads saved outputs. It does not scrape or fit during page interactions.

## Reproduce the fitted release

Use Python 3.11+ for the pinned fitting dependencies. Free downloads require network access; ingestion caches responses and stops on unresolved failures.

```sh
pip install -r requirements-fit.txt
python scripts/download_geography.py
python scripts/download_history.py --output data/raw/history
python scripts/build_history.py --archive-dir data/raw/history --cities data/raw/geography/cities15000.zip --cache data/raw/espn --output data/processed/history
python scripts/fit_model.py --history data/processed/history --output data/processed/fitted --seed 42 --maxiter 150
python scripts/publish_history.py --history data/processed/history --fitted data/processed/fitted --source-manifest data/raw/history/downloads.json
python -m unittest discover -s tests -v
```

Source archives can change; the committed manifests identify the release's exact downloads. Fitting uses differential evolution with L-BFGS-B polishing on chronological training replays. The accelerated objective is checked against the canonical engine. Bounds, seed, convergence, and full-precision constants are recorded in `fit_report.json`. Lead and performance weights reached their upper bounds; they are bounded estimates, not uniquely established physical constants.

## Documentation and next work

- [Technical manuscript](paper/main.tex): complete equations, feature derivations, fitting, results, and limitations.
- [Data specification](DATA_AND_FORMULAS.md): canonical field and timing contract.
- [Project plan](PROJECT_PLAN.md): live pipeline and deployment milestones.

Live after-game updates, stored upcoming-game forecasts, scheduling, and hosting remain pending. No paid service or scheduled workflow is configured. Preserve genuinely issued forecasts when refitting or correcting data. The repository remains private during development.

The [competition repository](https://github.com/aaravbora22/wharton_game_prediction_model) and team report provide research provenance; the NBA implementation documents its own conventions and revisions.
