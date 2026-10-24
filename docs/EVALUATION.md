# Evaluation

## Current v0.3 integrated models

The default probability is carryover Elo plus a regularized injury correction. A boosted comparison uses the same ratings and additional prior team, schedule and rotation features. Both are implemented internally; only Elo + injuries is exposed as a dashboard forecast. It has the lowest pooled log loss and Brier score. The boosted model picks three additional winners out of 3,690 games, which does not establish better probability estimates. Missing verified report/game coverage falls back to carryover Elo. Unsubmitted teams remain explicit unknowns.

| Procedure | Games | Log loss ↓ | Brier ↓ | Winner accuracy |
| --- | ---: | ---: | ---: | ---: |
| Carryover Elo | 3,690 | 0.603496 | 0.208434 | 66.64% |
| Elo + injuries | 3,690 | 0.598309 | 0.206217 | 67.07% |
| Boosted comparison | 3,690 | 0.600005 | 0.206871 | 67.15% |

These corrected, integrated backtests cover 2023–24 through 2025–26, including opening games. Fit on earlier seasons; select on the last earlier season; refit on all earlier seasons; then evaluate the next season. The first anchor season uses fixed default base coefficients; later training covariates use their own earlier-prefix core fits. All current-slate player updates are withheld until all morning forecasts are captured.

A production parity check corrected five exploratory injury-feature rows where overlapping trade/report assignments could use a player's performance from another game on the same slate. Retrospective heads were refitted. Boosted selections are sensitive to these small changes, so these integrated results supersede the earlier exploratory 67.72% boosted-accuracy figure. They do not establish unique coefficients or future accuracy.

| Season | Carryover LL / accuracy | Injury LL / accuracy | Boosted LL / accuracy |
| --- | ---: | ---: | ---: |
| 2023–24 | 0.608223 / 64.96% | 0.608223 / 64.96% | 0.608223 / 64.96% |
| 2024–25 | 0.606698 / 66.26% | 0.603297 / 66.83% | 0.601994 / 66.83% |
| 2025–26 | 0.595566 / 68.70% | 0.583408 / 69.43% | 0.589797 / 69.67% |

The unchanged base is an available inner candidate. In the first fold, both procedures select it; this is not evidence that an injury or tree term helped that fold. The original 68.56% v0.2 headline refers to one warmup-filtered season and is not directly comparable with this table.

The current release core is fitted on all five completed seasons. The injury head selects mean validation log loss with L2 penalties 0.0001–10; the boosted challenger selects validation winner accuracy, with log loss as a tie-breaker. Scalers fit only training rows. The portable numerical trees reproduce their training estimator within 1e-12. [Frozen bundle](../models/nba-v0.3/bundle.json), [per-fold results](../models/nba-v0.3/evaluation.json), [selection](../models/nba-v0.3/selection.json), and [verification](../models/nba-v0.3/verification.json) record the complete implementation.

All historical outcomes were already examined during development, and multiple model families were explored. These are retrospective chronological comparisons, not fresh confirmation. Live scoring compares only genuinely issued forecasts from the same frozen bundle. Earlier issued versions remain unchanged and never receive fabricated base/boosted probabilities.

## Reference v0.2 comparisons

These diagnostics compare the unchanged v0.2 multifactor equations with simple Elo. The comparator fits only K and home advantage; fatigue, schedule strength, lead retention, and performance adjustments are disabled. Both models use the same rating scale, independent 1500 season initialization, daily forecast cutoff, ten-game warmup, and scored games. Both optimize training log loss within the same K/home-advantage bounds.

## Original frozen release

Both models are fitted on 2021–22 through 2023–24. The original multifactor parameters and archives remain unchanged. The simple comparator was added after inspecting the original results, so this comparison is a retrospective diagnostic, not a new untouched test.

| Evaluation season | Model | Games | Log loss | Brier | Winner accuracy |
| --- | --- | ---: | ---: | ---: | ---: |
| 2024-25 | Multifactor v0.2 | 1,075 | 0.6043 | 0.2088 | 66.42% |
| 2024-25 | Fitted simple Elo | 1,075 | 0.6137 | 0.2129 | 65.95% |
| 2025-26 | Multifactor v0.2 | 1,075 | 0.5925 | 0.2035 | 68.56% |
| 2025-26 | Fitted simple Elo | 1,075 | 0.6018 | 0.2073 | 66.79% |

## Expanding-window checks

Train on the first available season, evaluate the next, then expand the training history by one season at each step. Each fold fits both models using only its training prefix. The three-season full-model fit is reused from the frozen release; other full-model configurations are diagnostic refits and do not replace it. Model structures and bounds were unchanged throughout.

| Evaluation season | Training seasons | Full log loss | Simple log loss | Full Brier | Simple Brier | Full accuracy | Simple accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-23 | 1 | 0.6469 | 0.6522 | 0.2280 | 0.2300 | 61.32% | 62.63% |
| 2023-24 | 2 | 0.6105 | 0.6168 | 0.2114 | 0.2145 | 65.64% | 64.25% |
| 2024-25 | 3 | 0.6043 | 0.6137 | 0.2088 | 0.2129 | 66.42% | 65.95% |
| 2025-26 | 4 | 0.5920 | 0.6013 | 0.2033 | 0.2071 | 68.56% | 66.98% |

The multifactor model has lower log loss and Brier score in all four folds. Winner accuracy improves in three folds and declines in 2022–23, demonstrating why probability quality and winner accuracy are separate objectives. All added fits converged. These historical outcomes were already available during development; chronological objective separation does not turn the diagnostics into prospective evidence.

## Paired uncertainty estimates

10,000 paired bootstrap samples resample whole Eastern-calendar daily slates, retaining all eligible games within each sampled slate. Intervals preserve within-day dependence but do not model dependence across days or uncertainty in fitting parameters. They are exploratory 95% intervals, without multiple-comparison adjustment. Differences are multifactor minus simple Elo; negative loss differences favor the multifactor model.

| Protocol / season | Log-loss difference | Exploratory 95% interval |
| --- | ---: | --- |
| Frozen / 2024-25 | -0.00935 | [-0.01435, -0.00438] |
| Frozen / 2025-26 | -0.00928 | [-0.01417, -0.00395] |
| Expanding / 2022-23 | -0.00529 | [-0.01177, 0.00121] |
| Expanding / 2023-24 | -0.00628 | [-0.01217, -0.00019] |
| Expanding / 2024-25 | -0.00935 | [-0.01435, -0.00438] |
| Expanding / 2025-26 | -0.00933 | [-0.01439, -0.00390] |

## Parameter stability

| Training seasons | K | Home advantage | Fatigue weight | Travel weight | Schedule weight | Defensive-rebound feature weight |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 12.143 | 33.368 | 0.1829 | 9.26e-07 | 1.0000 | 0.5890 |
| 2 | 11.134 | 47.570 | 0.1693 | 1.32e-07 | 1.0000 | 0.4795 |
| 3 | 12.217 | 41.553 | 0.1647 | 0.00011 | 0.9785 | 0.6870 |
| 4 | 13.085 | 40.906 | 0.1768 | 3.3e-05 | 0.7526 | 0.9610 |

Lead and performance weights reach their upper bounds in all four fits. K and fatigue weights are comparatively stable, while individual feature and travel weights vary substantially. For example, defensive-rebound weight ranges from 0.4795 to 0.9610. The additional equations provide a modest, repeated predictive improvement, but these checks do not establish uniquely stable feature effects or eliminate overfitting. An ablation study would be required to attribute improvement to particular features.

## Model decision

Retain the original frozen v0.2 configuration as the provisional model for live integration. The comparator earns its role as a benchmark; the multifactor family improves probability scores across the evaluated folds. Do not replace the release with the four-season refit merely because its now-observed test score is slightly better. Monitor future genuinely issued forecasts and revisit bounds/regularization in a separately versioned study.

## Reproduction

```sh
pip install -r requirements-fit.txt
python scripts/compare_models.py
```

Results, per-fold fitting reports, and paired predictions are under `models/comparison-v0.2/`. `predictions.csv` distinguishes `expanding_window` from `original_frozen_release`. All 1,230 forecasts per evaluation season are retained, with an eligibility flag; only eligible forecasts enter scores.

## Current specification dashboard replay

The dashboard now evaluates `current-model.json`, a separate replay of the active specification using pregame inputs. All five complete seasons helped fit the current release and are labeled **training replay**. The current season is a **post-fit reconstruction**, using each game's recorded pregame cutoff and saved inputs; it is not the original live record. These metrics answer how the current method reconstructs stored history, not how it generalizes to unseen seasons. The earlier-prefix chronological results above and original issued forecasts are retained separately. In the past-game table, Correct/Incorrect compares the probability's favored team with the final winner, choosing home at exactly 50%.

## Enforced matched samples

`nba_forecast/evaluation.py` compares model outputs only after verifying exact game-ID sets, uniqueness, outcomes, pregame cutoffs, teams/start times, eligibility, availability policy and any source-snapshot fingerprint. Missing variants or invalid probabilities fail the evaluation instead of dropping rows. The shared all-game or ten-prior-game window is applied once after identity checks, then all models receive the same ordered sample and SHA256 identifier. Metrics and paired differences are recorded together.

`python scripts/audit_comparisons.py` audits the three original next-season archives, verifies their reported scores to 1e-12 and records per-season raw-game/normalized-input source hashes. It regenerates `matched-evaluation.json`, including exact game lists and a pooled 3,690-game comparison. CI runs this audit. Future head fitting also checks duplicate IDs and records one validation sample shared by base, injury and boosted candidates. This guards sample fairness; it does not remove model-selection bias, dependence between games or historical source-vintage limitations.

Favorite calibration summaries use max(home probability, away probability), count whether that favorite won, and group forecasts in five-percentage-point bins. Bins are left-inclusive and right-exclusive, except the final bin includes 100%; a 50% tie chooses home. Counts and Wilson 95% binomial intervals accompany observed rates; those intervals do not account for dependence or fitting uncertainty. Historical chronological and original-issued evidence is shown separately, and training replays are excluded from these calibration summaries.
