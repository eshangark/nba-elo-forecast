# Rating quality experiment v1

This protocol is recorded before running the new rating/margin/head comparison. The two rating families and historical outcomes were already explored in the earlier formula study; this is retrospective exploratory evidence, not an untouched confirmation set.

## Hypothesis and controlled comparison

Independent base and lead update coefficients may improve estimates of team strength. Compare the original K(1+phi*log2(1+L)) rate against k0+k1*L. Both retain SOS, performance, home advantage, fatigue/travel, the fixed Elo scale and 0.5 season carryover. Injuries are disabled in both to isolate rating changes. No model is selected or promoted by this script.

Use the prior study's converged, earlier-prefix full coefficient fits, with their source reports preserved in fits/ and SHA256 hashes in inputs.json. Original bounds include K in [1,80], phi in [0,2]; independent bounds are k0 in [0.5,80], k1 in [0,160]. The other fitted parameters also differ because each engine was refitted on the same prior games and objective. Thus this compares fitted procedures, not a one-coefficient perturbation. Neither family nor seed is selected on the new outer scores. The prior structural fit was a follow-up prompted by inspected results.

## Chronology and samples

Outer seasons: 2023–24, 2024–25, 2025–26; train only on preceding complete seasons starting 2021–22. Replay the entire prefix under each fold's coefficients, with a fresh team-history state each season and rating carryover. Earlier of 10am Eastern/one hour before first tip is the daily cutoff; all predictions precede that slate's updates; reject unavailable previous-slate results. Evaluate identical game IDs, teams, outcomes, cutoffs and source hashes. Primary population includes all 3,690 games; report the identical ten-prior-game population separately. Use hashes to reject changed game data or fits rather than silently recomputing a different experiment.

## Separate rating information from probability scale

Report the original probability equation for each engine. Independently give both engines exactly the same fitted heads using only their pregame rating difference/100, venue and intercept:

- Logistic probability head: binary log loss, L2 penalty 1 on nonintercept coefficients; no tuning on outer games.
- Linear expected-margin head: ordinary least squares against signed home scoring margin.

Heads fit on earlier-season replay rows; those replay ratings were generated using parameters fitted on that training prefix. They are training replays, not out-of-fold calibration inputs. Future evaluation remains later-only, but later research should compare out-of-fold calibration histories. Venue is identical across heads; the original context terms are deliberately excluded from both common heads to isolate rating information plus venue.

## Outcomes and uncertainty

Report log loss, Brier, winner accuracy, five-point favorite calibration bins with counts, margin MAE/RMSE, and each team's expected minus observed wins across nonoverlapping ten-game blocks. Team blocks sum sequential pregame predictions that continue updating; they are not frozen forecasts made ten games ahead, and home/away blocks overlap in game evidence.

Pool all outer predictions and report every season. Compute 2,000 paired whole-day bootstrap draws with seed 42 for independent minus original raw and common-head probability scores and margin MAE. Negative loss/error differences favor independent lead. Intervals are exploratory, not adjusted for the many prior experiments, and do not capture cross-day dependence or fitting uncertainty. Do not choose the best family, calibration, seed or metric based on these results and call it confirmed.

## Betting evaluation and next experiments

Winner accuracy alone does not establish betting value. Before evaluating a betting policy, obtain timestamped two-sided prices available at each forecast cutoff; compare probabilities to proportional no-vig market probabilities, evaluate returns using the offered price (including its margin), account for price availability and report bet count, uncertainty and closing-line comparison. Declare the selection/edge policy on earlier data. Never substitute closing odds as a cutoff-time feature. Missing odds must be explicit and identical across candidates. This study has no such prices and makes no profitability claim.

Next isolated experiments: out-of-fold probability calibration; recency-weighted performance histories; season carryover selected on inner seasons; margin-based opponent-adjusted rating benchmark; then identical injury corrections refitted separately for each rating engine. Preserve SOS/performance in candidates unless the user requests an explicit diagnostic removal. Freeze a future issued-forecast evaluation before considering deployment.

## Reproduce

From the repository root with requirements-fit.txt installed:

```sh
python scripts/run_rating_experiment.py
python -m unittest discover -s tests -v
```

The default outputs are experiments/rating-quality-v1/results/{summary.json,results.json,predictions.csv}. No dashboard, production bundle, live ledger or historical replay is written. Results use the canonical Engine for bookkeeping; the independent lead engine changes only the effective update rate during completed-game updates.
