# NBA Elo Forecast

NBA team Elo ratings and pregame win probabilities, adapted from our Wharton competition basketball model.

## Status

Project foundation only. Original basketball code is pending. No fitted NBA model, accuracy claim, Streamlit deployment, or scheduled workflow yet. Initial free-source probes encountered HTTP 403 responses and a timeout; data access remains to be verified.

## Start here

- [Project plan](PROJECT_PLAN.md): scope, milestones, evaluation, and update rules.
- [Data and formulas](DATA_AND_FORMULAS.md): appendix transcription, raw input requirements, and implementation questions.
- [Source probe](scripts/probe_sources.py): repeatable free-data connectivity check.

## Run the source probe

Requires Python 3.10+; no third-party packages or API keys.

```sh
python scripts/probe_sources.py --season 2024-25 --output work/source-probe
```

Each run saves timestamped JSON responses and a report locally. Exit status 1 means at least one source failed; a successful probe is not proof of full historical coverage. Raw data and local probe outputs are ignored by Git.

## Intended architecture

Scheduled Python ingestion and rating updates -> saved ratings and prediction history -> Streamlit Teams, Games, and Methodology views.

Hosting and data must remain free. This repository is private; check included GitHub Actions minutes before enabling automation. Preserve historical pregame forecasts independently of later refits.
