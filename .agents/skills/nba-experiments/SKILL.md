---
name: nba-experiments
description: Design and run reproducible NBA Elo, probability calibration, and rating quality experiments in this repository. Use for model accuracy research and evaluating candidate forecasts; not routine dashboard styling.
---

# NBA model experiments

Read root AGENTS.md, docs/EVALUATION.md, and the relevant prior protocol before choosing a new study. The first study is experiments/rating-quality-v1/PROTOCOL.md. The live model is Elo plus injuries; a base-only experiment does not measure the full deployed procedure.

For a new experiment, record the hypothesis, baseline, permitted changes, training/inner/outer seasons, scoring population, selection objective, bounds, seeds and missingness policy before scoring. Already explored seasons remain retrospective. Keep SOS and performance unless explicitly studying an authorized diagnostic removal.

Use canonical Engine/replay behavior for the control and verify numerical parity when introducing an accelerated or modified simulator. Protect daily slate cutoffs, completion-time availability, carryover, per-season history resets and player-report timing. Test future-outcome perturbations: they must not change earlier predictions. A completed game's margin/box score can affect later ratings, never its pregame probability.

Separate two questions: does changing the rating update improve the existing probability equation, and does it improve future outcomes/margins when both rating engines receive the same calibration procedure? Fit all scalers, logistic/linear heads and candidate selection using earlier data only; record whether those earlier rows were themselves generated out of fold. Inspect future team-level residuals instead of comparing final ratings to outcomes already absorbed.

Use nba_forecast/evaluation.compare_samples before scoring; retain per-game outputs, raw data/fit/code hashes, per-season and pooled metrics, exact all-game/warmup windows, convergence and selection records. Report paired daily-slate uncertainty and acknowledge repeated exploration. Cache only with validated source/specification identity; fail on drift. Preserve negative findings. A small point improvement with an interval including zero is inconclusive.

Betting evaluation needs historical offered two-sided prices and timestamps. Declare the policy on earlier data, derive market comparisons without using future prices, account for offered odds in returns and report sample size and uncertainty. Missing prices are explicit. Never infer profitability from winner accuracy or construct synthetic historical odds as evidence.

Keep experiment code/results under experiments/ and commands under scripts/. Run meaningful parity, timing and metric tests plus existing checks. Summarize findings and the next evidence needed. Frozen bundles, dashboard forecasts and issued ledgers change only as part of an authorized implementation, not as a side effect of running research.
