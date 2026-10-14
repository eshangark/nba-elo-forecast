# Project plan

## Completed

- Private GitHub repository, documented competition provenance, canonical NBA rating engine, and technical manuscript.
- Free-source ingestion and validation of five full regular seasons (2021–22 through 2025–26), with source hashes and explicit repairs.
- Clean raw-count and derived-feature tables committed by season; 6,150 reconstructed forecasts and final rankings.
- NBA parameter estimation on three training seasons, frozen validation/test evaluation, optimizer report, and fitted model configuration.
- Fitted simple Elo comparison and four expanding-window retrospective checks; probability scores favor the multifactor family, with parameter-instability limitations documented. Original v0.2 retained provisionally for live integration.
- Streamlit Teams/Games/Methodology views, fixed season dropdown defaulting to current season, downloadable datasets, and light/dark themes.

## Next milestones

1. Implement current-season schedule ingestion and idempotent after-game updates using the frozen NBA model. Save upcoming forecasts with their actual issue time, information cutoff, and model version.
2. Preserve issued forecasts independently of corrected data or refits; replay rating state after a correction without overwriting the original forecast.
3. Show update freshness, ingestion failures, and upcoming games in the app. Validate a full after-game update locally before enabling automation.
4. Deploy to free Streamlit hosting and enable a bounded GitHub Actions schedule after checking private-repository included allowances. No paid overage.
5. Review subsequent seasons prospectively; maintain the manuscript and version models when changing formulas, constraints, or training data. The 2025–26 results are now observed and cannot serve as an untouched test for future revisions.

## Operational rules

Process completed games once and require every formula input. Failed ingestion preserves valid prior outputs. Keep credentials and bulky raw caches outside Git. Distinguish regular season from playoffs and other game types. Preserve private visibility until explicitly authorized to publish.

No hosted app or scheduled job is enabled yet. The current-season screen is initialization only; historical forecasts are reconstructed replays.
