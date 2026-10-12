# NBA Elo Forecast

## Scope

Adapt the existing Wharton basketball model to NBA data. Preserve its core dynamic Elo and Bradley–Terry approach; refit constants on NBA history. All data collection, hosting, and routine automation must remain free. The repository is private. Original competition code has been reviewed as reference material. The NBA implementation will preserve the conceptual framework while specifying its own consistent equations and data conventions.

## Product

- Teams: teams sorted by Elo, latest change, and team history.
- Games: upcoming win probabilities; completed games show the saved pregame prediction and actual outcome.
- Methodology: model equations, derived features, data processing, optimization, and evaluation; eventually a downloadable technical paper.

Streamlit will display saved outputs. A separate Python process will ingest results, derive features, update ratings, and publish predictions. It must run independently of app visits. Never fit the model or scrape the source on every page interaction.

## First milestones

1. Finalize a coherent NBA specification using the original basketball code and appendix as references. Document deliberate equation changes.
2. Validate free-source coverage and connectivity on historical and recent games. A response containing fields is not proof of multi-season completeness.
3. Build canonical game and team-game tables, retaining raw-source timestamps. Derive all feasible model features from basic inputs.
4. Replay games chronologically, saving predictions before applying game-result updates. Both teams' updates use the same pregame rating state.
5. Optimize constants on training history; choose changes on validation history; evaluate probabilities on untouched later games.
6. Build Streamlit views on verified model outputs, then enable scheduled ingestion.
7. Maintain `paper/main.tex` alongside implementation; associate evaluated results with a fixed model and dataset version.

## Evaluation

Proposed split: 2021–22 through 2023–24 training, 2024–25 validation, 2025–26 final test, subject to verified source coverage. Use earlier history for warm-up if available. No random train/test split. Training-period preprocessing only. Ratings can update as test results arrive; constants cannot be fitted to the test outcomes. Evaluate each game once.

Optimize log loss; report Brier score, calibration, sample sizes, and secondary winner accuracy. No accuracy claims before evaluation. Evaluation focuses on the proposed model family.

## Prediction records

Store game ID, prediction timestamp, data cutoff, model version, both pregame ratings, home/away probability, and later the result. Retain forecast versions and lock the latest valid pregame forecast when a game starts. Postponed games need explicit rescheduling rules. Label historical replays as backtests, distinct from forecasts genuinely issued before tip-off.

## Operational rules

- Process each completed game once; require all update inputs before processing it.
- Keep prior valid outputs when a fetch fails; show freshness in the app.
- Handle corrected box scores by replaying rating state from the affected point without overwriting original forecast records.
- Exclude preseason and explicitly distinguish regular-season, playoff, and other game types.
- Large raw datasets stay outside Git history; small model state and forecast outputs can be versioned.
- With a private repository, GitHub Actions uses the account's included allowance. Check that allowance before enabling a schedule; no paid overage.
- No scheduled workflow or deployment is enabled yet.

## Current status

Private repository created; free-data specification and connectivity probe prepared. No model trained, NBA dataset validated, website deployed, or paid service configured. Original competition reference reviewed; initial LaTeX manuscript compiles successfully. Data coverage and the canonical implementation are the next milestones.
