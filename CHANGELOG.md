# Changelog

## Repository preparation — 2026-10-14

- Added the compiled technical paper alongside its LaTeX source.

- Shortened the project overview and separated operating, contributing, dataset, and roadmap documentation.
- Removed superseded source probes and the unfitted pilot entry point.
- Made historical-ingestion dependencies explicit and added a full-test CI workflow for code changes.
- Retained frozen model parameters, historical results, source attribution, and issued forecasts.
- Licensed original project code and documentation under MIT, with provider data and third-party materials excluded.

## Model 0.2.0 — 2026-10-13

- Fitted the NBA adaptation on three training seasons and evaluated frozen parameters on validation and held-out seasons.
- Published five complete regular-season datasets, quality audits, and chronological replay outputs.
- Added a fitted simple Elo comparator and expanding-window diagnostics.
- Implemented immutable live forecast revisions, correction replay, collection failure reporting, and scheduled updates.
- Deployed the Streamlit dashboard with season selection, dataset downloads, themes, and periodic snapshot refresh.

Repository/documentation changes do not imply a change to the mathematical model version. Historical comparisons are retrospective; prospective live evaluation is ongoing.
