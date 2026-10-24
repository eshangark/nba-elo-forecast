# Rating quality: independent base and lead update rates

The independent-lead procedure has slightly better retrospective probability scores and future-margin errors. Winner accuracy gains remain uncertain, and the common probability head loses two correct picks relative to its matched control. These results support further testing; they do not establish a deployable improvement over the injury-adjusted dashboard.

Both engines retain SOS and performance. No production bundle, issued forecast or dashboard reconstruction was changed. This experiment compares earlier-prefix fitted procedures; it does not merely replace the lead formula while keeping all other coefficients fixed.

## Matched future games

3,690 games across 2023–24, 2024–25 and 2025–26, including openers; fit each engine and both heads only on earlier seasons. Injuries are off for both. The archived earlier-prefix coefficient fits are reused, not chosen again on the evaluation seasons. See [protocol](PROTOCOL.md), [inputs](inputs.json), [machine-readable summary](results/summary.json), and [parity verification](verification.json).

| Procedure | Correct / games | Accuracy | Log loss ↓ | Brier ↓ | Margin MAE ↓ | Margin RMSE ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original update, original probability | 2454 / 3690 | 66.50% | 0.603761 | 0.208521 | 11.1910 | 14.3399 |
| Independent lead, original probability | 2460 / 3690 | 66.67% | 0.602717 | 0.208054 | 11.1743 | 14.3186 |
| Original update, common probability head | 2449 / 3690 | 66.37% | 0.607088 | 0.210023 | 11.1910 | 14.3399 |
| Independent lead, common probability head | 2447 / 3690 | 66.31% | 0.606169 | 0.209601 | 11.1743 | 14.3186 |

The common heads use pregame rating gap, venue and intercept, with identical fitting procedures. Margin predictions always use the common linear head, so their scores repeat across each engine's two probability rows. The probability head deliberately omits fatigue/context from both engines: its worse scores do not establish that richer calibration cannot help. A later experiment should calibrate complete pregame log odds using earlier out-of-fold rows.

## Per-season direction

| Season | Original raw log loss | Independent raw log loss | Original raw accuracy | Independent raw accuracy |
| --- | ---: | ---: | ---: | ---: |
| 2023–24 | 0.608617 | 0.608455 | 64.96% | 65.12% |
| 2024–25 | 0.606604 | 0.605619 | 65.77% | 66.02% |
| 2025–26 | 0.596063 | 0.594077 | 68.78% | 68.86% |

## Paired exploratory intervals

2,000 whole-day paired bootstrap draws, seed 42; candidate minus original. Negative error/loss differences favor independent lead.

| Metric | Difference | Exploratory 95% interval |
| --- | ---: | ---: |
| Raw log loss | -0.001044 | [-0.001603, -0.000468] |
| Raw winner accuracy | +0.163 percentage points | [-0.216, +0.545] percentage points |
| Common-head log loss | -0.000919 | [-0.001439, -0.000382] |
| Common-head winner accuracy | -0.054 percentage points | [-0.374, +0.247] percentage points |
| Margin MAE | -0.01672 points | [-0.02612, -0.00710] points |

The margin improvement is tiny in practical terms. Intervals omit fitting uncertainty and cross-day dependence and are unadjusted for repeated historical exploration. Both families and outcomes were inspected previously, so these intervals are not confirmation of a newly discovered edge.

Across 720 nonoverlapping ten-game team blocks, expected-win RMSE is 1.5050 versus 1.5045 using raw probabilities; 1.5036 versus 1.5044 using common heads. There is no consistent team-block improvement. These blocks aggregate sequential pregame forecasts, with updates between games; they are not forecasts frozen ten games ahead. Favorite calibration bins/counts and the separate warmup-filtered comparison are in summary.json.

## Next decision

Keep the deployed Elo + injuries model while testing out-of-fold calibration of the complete probability and repeating the rating comparison with identical, separately refitted injury procedures. A future frozen issued-forecast test is needed. Historical offered odds and timestamps are also needed before making any claim about returns; this study did not evaluate a betting policy.

## Validation

The five new numerical/timing tests pass, as does the full 80-test suite. The existing matched-sample audit verifies 3,690 games across the production procedures. Both raw research variants reproduce their prior independently implemented simulator across all 3,690 games within 1e-11. Source and fit hashes are checked by the runner; The full result with exact game lists and the per-game CSV regenerate locally; the compact summary is committed. No new coefficient optimization was performed.
