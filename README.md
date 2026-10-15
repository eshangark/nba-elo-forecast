# NBA Elo Forecast

NBA team ratings and pregame win probabilities, with historical backtesting and automatic after-game updates. This project is adapted from work developed for the Wharton Data Science Competition.

[Application](https://eshan-nba-elo-forecast.streamlit.app/) · [Technical paper](paper/main.pdf) · [LaTeX source](paper/main.tex)

## What it does

- Ranks all NBA teams by Elo and estimates matchup win probabilities.
- Displays upcoming forecasts and completed-game outcomes.
- Supports the current season and five historical seasons, with downloadable datasets.
- Collects results every two hours; open pages refresh saved snapshots every minute.

The frontend reads stored outputs rather than scraping or fitting on page load. The live ledger preserves issued forecasts through source corrections; games discovered after completion never receive fabricated pregame predictions.

## Historical performance

Model **0.2.0** was trained on 2021–22 through 2023–24. Constants were frozen before evaluating the following seasons. Scoring begins once both teams have played ten games; earlier games still update ratings.

| Evaluation | Games | Log loss ↓ | Brier score ↓ | Winner accuracy |
| --- | ---: | ---: | ---: | ---: |
| 2024–25 validation | 1,075 | 0.6043 | 0.2088 | 66.42% |
| 2025–26 held-out test | 1,075 | 0.5925 | 0.2035 | 68.56% |
| Simple Elo, same 2025–26 test | 1,075 | 0.6018 | 0.2073 | 66.79% |

These are reconstructed historical forecasts, not measured live performance. Probability scores are the primary measures; accuracy is secondary. Some fitted weights are unstable or reach their bounds. See [evaluation results](docs/EVALUATION.md) for comparisons and limitations, and the [paper](paper/main.pdf) for equations and derivations.

## Run locally

Use Python 3.12 and run commands from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The committed snapshots are sufficient to run the app. No API key or source collection is required. Each season starts teams at 1500; preseason results are excluded.

## Data and code

The repository includes **6,150 games and 12,300 team-game records** across five complete regular seasons, 2021–22 through 2025–26. Basketball records come from ESPN through SportsDataverse archives and primary summaries; GeoNames supplies city coordinates and time zones.

| Directory | Contents |
| --- | --- |
| `nba_forecast/` | Rating engine, ingestion, replay, fitting, and live state |
| `data/seasons/` | Clean records, derived features, historical snapshots, live ledger |
| `models/` | Frozen parameters, fitting reports, and comparator results |
| `scripts/` | Collection, fitting, publishing, and evaluation commands |
| `tests/` | Model, data, timing, live-state, and interface checks |
| `paper/` | Technical paper and LaTeX source |
| `docs/` | Dataset guide, reproducibility instructions, and evaluation results |

- [Data and sources](docs/DATA.md): file definitions, validation, timing, attribution, and reuse notices.
- [Development and operation](docs/DEVELOPMENT.md): research reproduction, tests, updates, hosting, and contribution guidelines.
- [Evaluation](docs/EVALUATION.md): simple Elo comparisons, chronological diagnostics, and uncertainty.

## License

Original project code and documentation use the [MIT License](LICENSE). Provider records, raw-source test fixtures, datasets, and third-party materials retain their separate rights and attribution notices; see [data and sources](docs/DATA.md#sources-and-reuse).
