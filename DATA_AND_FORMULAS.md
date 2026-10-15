# Data and formula specification

The canonical model is `nba_forecast/model.py`, version 0.2.0; `paper/main.tex` gives the mathematical specification and appendix derivations. Feature definitions, units, fitting, and evaluation are documented in the manuscript.

## Coverage and validation

Five complete regular seasons, 2021–22 through 2025–26, contain 1,230 games each, 30 teams, and 82 games per team. Completed standard regular-season games are included; preseason, playoffs, All-Star games, and the NBA Cup final are excluded. Cup games that count toward the regular season remain included.

Schedules, box scores, and play-by-play come from SportsDataverse's ESPN archives. Validation enforces unique game keys, opponent pairing, header-score agreement, finite nonnegative integer counts, shot-attempt constraints, point identities, plausible assists/steals, positive feature denominators, and peak lead at least final margin. Missing is never silently converted to zero. Unresolved records block publication.

873 games required validated primary ESPN replacements, mostly because archived play-by-play was incomplete. Repairs to largest leads and team aggregates are recorded separately. Largest lead recovery requires a score path ending at the header score. Player aggregate recovery requires complete rows and matching point/shooting totals. TOV consistently means summed **player turnovers**, excluding provider non-player team turnovers. See `models/nba-v0.2/data_quality.json` and each season's manifest.

## Fields and timing

| Stored input | Source | Use |
| --- | --- | --- |
| Stable game/team IDs, tip-off, season, status, final scores | ESPN schedule/header | Chronology, outcomes, margin, schedule strength |
| Venue city, neutral status | ESPN venue metadata | Home advantage and travel context |
| PTS, FGM, FGA, 3PM, 3PA, FTM, FTA, OREB, DREB, AST, player TOV, STL | ESPN team/player box scores | Postgame performance features |
| Largest lead for both teams | ESPN box score or validated score path | Lead retention |
| Latitude, longitude, IANA timezone | GeoNames cities15000 | City-distance/timezone proxy |
| Completion-time proxy | Terminal EndGame wallclock or dated final recap | Prior-slate availability check |

Seventeen games use final-recap publication times. One game has play dates shifted by a day and uses an explicitly flagged conservative tip-off-plus-eight-hours availability bound. This bound is not an observed completion timestamp. Historical provider corrections may also be present; replays do not prove what a live feed showed at the time.

Pregame fields use prior games only. Historical forecasts share a daily cutoff at the earlier of 10:00 Eastern and one hour before the day's first tip-off. All prior slates must be complete by that cutoff. After the slate, results and box-score features update ratings. Live after-game forecasting is implemented separately in `nba_forecast/live.py`; the observed forecast ledger is distinct from reconstructed rating-state estimates. See `LIVE_PIPELINE.md` for the operational policy.

Rest equals intervening Eastern calendar dates; back-to-back is zero. Openers use three rest days, zero travel/timezone change, and a flag. Travel uses Haversine kilometres between consecutive venue cities. Both cities' timezone offsets are compared at the current tip-off, avoiding DST-only artificial travel.

## Canonical equations

For home team i, away team j, and h=1 (0 at neutral venues):

    F = RD_j + exp(abs(TZ_i)/3) + nu * TD_i
    G = RD_i + exp(abs(TZ_j)/3) + nu * TD_j
    logit(p_i) = ln(10) * ((r_i-r_j+H*h)/c - gamma*ln(F/G))
    p_j = 1-p_i

For each team, s=2*y-1:

    delta = K*(y-p)*(1+s*beta*S)*(1+phi*log2(1+L))*(1+s*lambda*(Q-1))

S uses opponent and opponent-of-opponent prior records with Laplace-smoothed win rates and repeated-opponent weighting. L is absolute final margin divided by the largest lead of either team. The eight X features are derived from the committed raw counts using the manuscript's appendix; rebound rates use opposite opponent categories and steal rate uses opponent estimated possessions.

    scaled_X = (X1/10, X2, X3, X4, X5, X6/3, -X7, X8)
    AGPF = clip(sigmoid(sum(alpha_k*scaled_Xk)), 1e-6, 1-1e-6)
    Q = clip(AGPF/prior_mean_AGPF, .25, 4)

Openers receive Q=1. Current box scores never enter their own pregame prediction. Each season starts independently at 1500 and league mean ratings are recentered after each slate.

`model_features.csv` labels pregame and postgame fields explicitly. The prior AGPF mean is an opening-game initialization value for the first game, not historical observations. Full-precision frozen constants live in `models/nba-v0.2/parameters.json`; fixed numerical conventions and optimizer bounds are documented in the paper/report.

## Fitting and evaluation

2021–22 through 2023–24 train the 14-dimensional bounded model; 2024–25 validates and 2025–26 tests the frozen result. Differential evolution (seed 42) plus L-BFGS-B polishing minimizes chronological training log loss. Every candidate recomputes rating and performance history. Exponent base 10 and c=497.3558141396255 anchor the rating scale; eight positive alpha weights are fitted through seven softmax logits.

All 6,150 forecasts are saved; primary scoring requires both teams to have played ten prior games. Probability metrics are log loss, Brier score, and calibration-bin summaries. Winner accuracy picks home at probability exactly 0.5. Training scores are not out-of-sample evidence. The held-out test has 1,075 scored games, log loss 0.5925, Brier 0.2035, and winner accuracy 68.56%.

## Baseline and stability checks

`MODEL_COMPARISON.md` records the fitted simple Elo comparison and expanding-window diagnostics. Both models use identical chronology, initialization, and scoring eligibility. Original frozen v0.2 outperforms the three-season-fitted comparator on both later seasons; four expanding-window evaluations also favor the multifactor model on probability scores. Individual travel/feature weights are unstable and several coefficients reach bounds. These retrospective checks neither eliminate overfitting nor supply a new untouched test. The original configuration remains unchanged.
