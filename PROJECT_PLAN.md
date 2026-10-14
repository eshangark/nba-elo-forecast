# Project plan

## Completed

- Private GitHub repository, documented competition provenance, canonical NBA rating engine, and technical manuscript.
- Free-source ingestion and validation of five full regular seasons (2021–22 through 2025–26), with source hashes and explicit repairs.
- Clean raw-count and derived-feature tables committed by season; 6,150 reconstructed forecasts and final rankings.
- NBA parameter estimation on three training seasons, frozen validation/test evaluation, optimizer report, and fitted model configuration.
- Fitted simple Elo comparison and four expanding-window retrospective checks; probability scores favor the multifactor family, with parameter-instability limitations documented. Original v0.2 retained provisionally for live integration.
- Streamlit Teams/Games/Methodology views, fixed season dropdown defaulting to current season, downloadable datasets, and light/dark themes.

- Manual after-game collector, single-writer locking, atomic live snapshots, immutable forecast revisions, correction replay, and freshness/failure display.
- First three observed upcoming regular-season forecasts published for 2026–27; no completed regular-season games yet in the initial snapshot.
- Two-hour GitHub Actions schedule, pinned vendor actions, bounded runtimes, core checks, and safe data-only publishing.
- Private Streamlit deployment, hosted interface verification, and one-minute refresh of saved snapshots.

## Ongoing evaluation

The initial implementation and deployment are complete. Automatic collection continues within included allowances and existing zero-dollar paid-usage controls.

1. Monitor real completed-game updates and genuinely issued forecasts. Record ingestion failures and source latency; compare live probability calibration with historical results.
2. Review subsequent seasons prospectively; maintain the manuscript and version models when changing formulas, constraints, or training data. The 2025–26 results are observed and cannot serve as an untouched test for future revisions.

## Operational rules

Process completed games once and require every formula input. Failed ingestion preserves valid prior outputs. Keep credentials and bulky raw caches outside Git. Distinguish regular season from playoffs and other game types. Preserve private visibility until explicitly authorized to publish.

The scheduled updater is enabled. The hosted frontend is deployed with private access. The current-season screen shows an observed snapshot and upcoming issued forecasts. Historical archives are reconstructed replays; backfilled current-season games never acquire fabricated live predictions.
