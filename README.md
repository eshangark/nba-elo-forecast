# NBA Elo Forecast

NBA team ratings and pregame win probabilities, with reproducible historical evaluation and an after-game update pipeline. The model adapts the Billy Beanes' 2025 Wharton competition framework to NBA regular-season basketball.

[Application](https://eshan-nba-elo-forecast.streamlit.app/) · [Technical manuscript](paper/main.tex) · [Data sources](SOURCES.md) · [Model comparison](MODEL_COMPARISON.md)

The hosted application currently requires private access. Preparing this repository for publication does not change its visibility or the application's sharing settings.

## Features

- **Teams:** ratings ordered by Elo.
- **Games:** upcoming win probabilities and completed-game outcomes.
- **Seasons:** current-season view plus five historical archives, with downloadable datasets.
- **Methodology:** equations, fitted constants, and probability evaluation.
- **Updates:** GitHub Actions collects completed games every two hours; open pages reread saved outputs every minute.

The frontend reads committed snapshots; page interactions do not scrape data or fit models. The live pipeline preserves issued forecasts when source data is corrected. Backfilled games without an issued prediction are excluded from live forecast scores.

## Historical results

Model **0.2.0** was fitted on 2021–22 through 2023–24. Its constants were frozen before evaluating 2024–25 and 2025–26. Primary scoring requires both teams to have played ten games; earlier games still update ratings.

| Evaluation | Games | Log loss ↓ | Brier score ↓ | Winner accuracy |
| --- | ---: | ---: | ---: | ---: |
| 2024–25 validation | 1,075 | 0.6043 | 0.2088 | 66.42% |
| 2025–26 held-out test | 1,075 | 0.5925 | 0.2035 | 68.56% |
| Simple Elo, same 2025–26 test | 1,075 | 0.6018 | 0.2073 | 66.79% |

These are **reconstructed historical forecasts**, not predictions issued live. Log loss and Brier score measure probability quality; accuracy is secondary. Later expanding-window comparisons are retrospective diagnostics. Individual weights vary across fits, two coefficients reach their bounds, and future performance remains unestablished. See [MODEL_COMPARISON.md](MODEL_COMPARISON.md) for the complete protocol and limitations.

## Run locally

Use **Python 3.12**, the tested development and deployment runtime. Run commands from the repository root.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The committed snapshots are sufficient to run the application without collecting source data. At the start of each regular season, ratings reset to 1500; preseason games are excluded.

## Data and repository layout

Five complete regular seasons, **2021–22 through 2025–26**, contain **6,150 games and 12,300 team-game records**. Required numerical model inputs pass the release's validation checks. ESPN supplies the underlying basketball records through SportsDataverse archives and primary ESPN summaries; GeoNames supplies city coordinates and time zones.

| Path | Contents |
| --- | --- |
| `app.py` | Streamlit dashboard |
| `nba_forecast/` | Rating engine, ingestion, replay, fitting, and live state |
| `data/seasons/` | Clean game records, feature tables, replay snapshots, live ledger |
| `models/nba-v0.2/` | Frozen constants, optimizer report, data-quality summary |
| `models/comparison-v0.2/` | Comparator fits and paired predictions |
| `scripts/` | Data collection, fitting, publishing, and comparison entry points |
| `tests/` | Formula, chronology, data, live-state, and interface checks |
| `paper/main.tex` | Self-contained technical manuscript |

See [data/README.md](data/README.md) for file meanings, timing, and reuse notices. Raw downloads, local caches, credentials, and generated build files are excluded from Git. Travel is a venue-city distance proxy; source repairs and completion-time assumptions are disclosed in the manifests and manuscript.

## Reproduce the research

```sh
python -m pip install -r requirements-fit.txt
python -m unittest discover -s tests -v
```

To rebuild the historical data and refit the original training protocol:

```sh
python scripts/download_geography.py
python scripts/download_history.py --output data/raw/history
python scripts/build_history.py --archive-dir data/raw/history --cities data/raw/geography/cities15000.zip --cache data/raw/espn --output data/processed/history
python scripts/fit_model.py --history data/processed/history --output data/processed/fitted --seed 42 --maxiter 150
```

These commands write local research outputs without replacing the frozen release. Source archives can change; committed manifests record release URLs and hashes. Floating-point and optimizer differences can affect refitted constants. To reproduce the recorded evaluation, use the committed game records and frozen parameters; the test suite checks their canonical replays.

See [CONTRIBUTING.md](CONTRIBUTING.md) before publishing replacement archives or changing model versions. The historical 2025–26 test has already been observed and cannot serve as an untouched test for a new model.

## Operation and documentation

- [Deployment](DEPLOYMENT.md): hosting, update schedule, costs, and maintenance.
- [Live pipeline](LIVE_PIPELINE.md): collection, corrections, issued forecasts, and scoring.
- [Data and formulas](DATA_AND_FORMULAS.md): field definitions and timing contract.
- [Roadmap](ROADMAP.md): prospective evaluation and future research.
- [Changelog](CHANGELOG.md): released implementation and repository changes.
- [Sources and attribution](SOURCES.md): provider records, geography, and competition provenance.

The live collector can also be run manually on macOS or Linux:

```sh
python scripts/download_geography.py
python scripts/update_live.py --cities data/raw/geography/cities15000.zip
```

Collection uses free endpoints with no availability guarantee. Hosting and scheduled jobs use included allowances. No paid API or automatic paid overage is configured.

## Licensing

Original project code and documentation are available under the [MIT License](LICENSE). This license excludes provider records, raw-source test fixtures, datasets, and third-party materials, which retain their separate rights and attribution notices. See [SOURCES.md](SOURCES.md) and [data/README.md](data/README.md).
