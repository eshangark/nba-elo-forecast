# NBA Elo Forecast

An NBA forecasting project using dynamic team ratings and pregame win probabilities, informed by a multifactor Elo and Bradley–Terry framework developed for the 2025 Wharton competition.

## Project status

Research and development. The model specification and initial technical manuscript are available. NBA data access and coverage are being evaluated; fitted NBA parameters, predictive results, and a deployed application are not yet available.

## Planned application

- **Teams:** ratings, rating changes, and historical trajectories.
- **Games:** upcoming win probabilities and archived pregame forecasts alongside outcomes.
- **Methodology:** equations, feature definitions, parameter estimation, and evaluation.

## Documentation

- [Technical manuscript](paper/main.tex) — self-contained LaTeX working draft.
- [Project plan](PROJECT_PLAN.md) — milestones and operational requirements.
- [Data specification](DATA_AND_FORMULAS.md) — inputs, inherited equations, and open implementation decisions.

The manuscript is maintained alongside substantive model and evaluation changes. Proposed methods and verified results are explicitly distinguished.

## Data-source check

Requires Python 3.10+; no third-party dependencies or API keys.

```sh
python scripts/probe_sources.py --season 2024-25 --output work/source-probe
```

Responses and a report are saved in a timestamped local directory. Exit status 1 indicates at least one failed source check. Connectivity does not establish historical completeness. Raw data and temporary outputs are excluded from Git.

## Architecture

Scheduled Python ingestion and rating updates produce saved model state and forecast history. A Streamlit application will display these outputs independently of the update process.

## Research provenance

The [original competition repository](https://github.com/aaravbora22/wharton_game_prediction_model) and team report inform this project. The NBA implementation will document its own conventions, fitted parameters, and validation. See the manuscript for attribution.

## Development constraints

Use free data and hosting within included allowances. Preserve historical forecasts independently of subsequent model refits. Keep credentials out of version control.
