# NBA Elo Forecast development

## Start here

This repository is the source for the Streamlit dashboard and GitHub scheduled collector. Read README.md for the active model, docs/EVALUATION.md for evidence and limitations, and docs/DATA.md for source/cutoff rules. Research work uses [.agents/skills/nba-experiments/SKILL.md](.agents/skills/nba-experiments/SKILL.md); read it for experiments, calibration or rating changes.

## Project invariants

- Retain SOS and performance in model candidates. Removal is a separately labeled diagnostic, not an agreed production change.
- Predictions use information available at the recorded pregame cutoff. Forecast the entire slate before updating any team/player from that slate. Preserve missing-report fallback and explicit unknown coverage.
- Original issued forecasts are immutable. Current-method reconstructions, training replays and chronological backtests are separate evidence. Never manufacture historical issued forecasts or overwrite them after refitting.
- Compare exactly matched IDs, teams, outcomes, cutoffs, eligibility and source fingerprints through nba_forecast/evaluation.py. Fail on missing candidates rather than intersecting samples silently.
- Winner accuracy, probability quality, rating quality and profitability are different objectives. Report log loss, Brier, calibration and counts alongside winner accuracy. Elo has no observable true target; evaluate future outcomes/margins under common training-only mappings.
- Historical seasons have already been studied. Earlier-prefix evaluation is retrospective, not fresh confirmation. Record experiments and unsuccessful candidates, seeds, fitting bounds and convergence. Do not select on outer seasons and call the same scores unbiased.
- Research does not automatically promote a model. Use experiments/ for candidates and artifacts; change frozen bundles, historical dashboard replays or default forecasts only within the requested implementation scope and after evidence supports it.
- Use free data/hosting within included allowances; no paid overages. Preserve repository visibility. Do not commit secrets or local environment paths.
- Maintain paper/main.tex alongside material production changes to equations, feature definitions, data, fitting or evaluation. Research-only experiments should document their own protocol/results; distinguish proposals from implemented and verified findings.

## Useful commands and locations

Use Python 3.12, with requirements-fit.txt for numerical work or requirements-live.txt for collection. Run from repository root:

```sh
python -m pip install -r requirements-fit.txt
python -m unittest discover -s tests -v
python scripts/audit_comparisons.py
python scripts/run_rating_experiment.py
python -m streamlit run app.py
```

Core engine: nba_forecast/model.py; conservative replay: replay.py; probability heads: forecasting.py; fitting: fitting.py; dashboard: app.py; immutable/reconstruction storage: data/seasons/; frozen models: models/; collector and validation: .github/workflows/. The experiment runner writes only experiments/rating-quality-v1/results/ by default. It never fits or publishes on page load.

Inspect the checkout and remote before changing Git state; preserve concurrent collector updates. Use a branch/PR for research changes so the deployed dashboard is not changed by an exploratory result. Run relevant numerical/timing tests plus the existing suite and matched-sample audit before delivery; avoid rerunning expensive fits when source/code hashes and cached earlier-prefix reports suffice.
