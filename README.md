# NBA Elo Forecast

NBA team ratings and pregame win probabilities, with historical backtesting and automatic after-game updates. This project is adapted from work developed for the Wharton Data Science Competition.

[Application](https://eshan-nba-elo-forecast.streamlit.app/) · [Technical paper](paper/main.pdf) · [LaTeX source](paper/main.tex)

## What it does

- Ranks all NBA teams by Elo and estimates matchup win probabilities.
- Shows matchup probabilities with current/prior Elo ranks, recent records, plain-language injury availability, and selectable explanations.
- Replays completed games with Correct/Incorrect results and separates historical backtests, original issued forecasts, and current-method replay scores.
- Shows report coverage and falls back to Elo when a verified injury report does not cover the game.
- Supports the current season and five historical seasons, with downloadable datasets.
- Collects results every two hours; open pages refresh saved snapshots every minute.

The frontend reads stored outputs rather than scraping or fitting on page load. The live ledger preserves issued forecasts through source corrections; games discovered after completion never receive fabricated issued predictions. Past-game tables and their scorecards use a separate current-method replay, rebuilt after model changes. Replay probabilities use only pregame information at the saved cutoff, but historical seasons used for fitting are training replays rather than unseen tests. The original live ledger remains downloadable.

## Models and historical performance

Version **0.3.0** carries half of each team's previous-season Elo deviation forward. The published probability adds a regularized injury correction. This is the only dashboard forecast: it has the lowest retrospective log loss and Brier score among the tested procedures. The boosted research comparator picked three more winners out of 3,690 games, but had worse probability scores. Rating updates always use the base Elo probability; injuries do not alter the Elo rankings. Research comparators and their original records remain available for reproducibility.

| Retrospective procedure | Games | Log loss ↓ | Brier ↓ | Winner accuracy |
| --- | ---: | ---: | ---: | ---: |
| Carryover Elo | 3,690 | 0.6035 | 0.2084 | 66.64% |
| Elo + injuries (published) | 3,690 | 0.5983 | 0.2062 | 67.07% |
| Boosted comparison | 3,690 | 0.6000 | 0.2069 | 67.15% |

Each evaluation season uses earlier seasons for fitting and selection. These all-game comparisons include opening games and the deployed missing-report fallback. The production checks corrected five exploratory injury-feature rows that could use another current-slate player's performance; refitted boosted selections therefore supersede earlier exploratory accuracy figures.

These are reconstructed results on previously studied outcomes, not live accuracy claims. The retained v0.2 release scored 68.56% on a different population: one season after both teams' ten-game warmup. See [evaluation](docs/EVALUATION.md) for protocols, per-season scores and limitations.

## Injury data and mathematical basis

The scheduled collector reads [official NBA injury reports](https://official.nba.com/nba-injury-report-2026-27-season/), validates publication time and matchup identity, and maps unambiguous player names to ESPN IDs. Earlier completed player box scores supply expected minutes and a shrunk Game Score per minute. Separate status totals and explicit missingness indicators enter a fitted logistic correction to the base Elo log odds. Reports unavailable for a matchup trigger base Elo; partial reports remain unknown rather than healthy. See [data pipeline](docs/DATA.md#player-and-injury-inputs) and the paper for the full equations, timing and provenance.

The base probability is a covariate-adjusted [Bradley–Terry](https://doi.org/10.1093/biomet/39.3-4.324) paired-comparison model. Ratings update sequentially; the implementation does **not** perform [Whole-History Rating](https://www.remi-coulom.fr/WHR/)'s joint Bayesian optimization of historical rating trajectories. Travel, schedule and performance multipliers are empirical project choices, not formulas derived in those papers.

## Current-method replay versus original forecasts

`data/seasons/*/current-model.json` contains the active model's reconstruction of each season. Historical replays start from the earliest stored season, rebuild ratings chronologically, and carry ratings/player histories forward. The five complete seasons use saved morning report inputs and earlier player appearances in `replay-inputs.json.gz`. Current-season replays use each game's last actual pregame issuance cutoff and captured rest/travel context. Saved raw injury reports are preferred; older records can reuse saved pregame injury covariates with the current scaler and coefficients. If neither exists, the replay uses an explicit Elo fallback. Original issued probabilities are never overwritten.

The past-game **Prediction** column marks the higher-probability team Correct or Incorrect; exactly 50% picks home. Dashboard replay scores evaluate the latest specification, while the chronological backtests below the methodology retain earlier-season fitting and the original issued ledger measures what was actually published. Training replay scores are not an estimate of unseen-game accuracy.

Under **Games → Past games**, choose a date and select a table row or use **Choose past matchup** to inspect the same evidence shown for upcoming games. **Forecast record** switches between the current-method replay and the original issued forecast (or stored historical replay). The final score is separate from the pregame evidence. Team strength, player history and calibration evidence use only information available before that forecast's cutoff; context that cannot be recovered and verified is marked unavailable.

## Symbol dictionary

The paper builds the model in order: season carryover → base forecast → published probability corrections → completed-game features → performance factor → Elo update. Constants below refer to v0.3 and are rounded; the [model bundle](models/nba-v0.3/bundle.json) retains full precision. Game-dependent quantities have no single value. Original v0.2 configurations remain preserved.

<details>
<summary>Notation, English meanings, and numerical values</summary>

### Carryover and published probabilities

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $\rho$ | The season-start Elo retains this fraction of the previous final deviation from 1500. | 0.5 |
| $q_i,q_j$ | The default probabilities include the fitted injury correction and sum to one. | Between 0 and 1 |
| $\mathbf d_i$ | Standardized base log odds, earlier player value/minutes by status, and report-coverage indicators form this vector. | 19 features |
| $b,\mathbf w$ | The intercept and feature weights adjust base log odds. | Intercept 0.00231409; 19 weights in the model bundle |
| $\eta$ | This penalty shrinks the logistic correction. | 0.0001 in the current release |
| $\bar m,v_p$ | Expected minutes and shrunk value use earlier played observations. | Half-life 10; value prior 80 minutes at 0.3 |
| $q_{B,i},\mathbf f_i$ | The challenger probability uses prior team, schedule, rotation and injury inputs. | 50 features |
| $T,\omega$ | Trees contribute to the challenger score; the blend controls its weight relative to Elo. | 100 trees; initial score 0.21349012; blend 1 |

### Fitted constants and fixed scales

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $K$ | The base update coefficient controls how much a game can change Elo. | 13.748881 |
| $H$ | Home advantage adds this many Elo points to the home-side rating difference. | 40.03439907 |
| $c$ | The fixed rating scale converts Elo differences into probability differences. | 497.3558141 (fixed) |
| $\gamma$ | The fatigue coefficient weights the logarithm of the rest/travel index ratio. | 0.179559595 |
| $\nu$ | The travel coefficient weights venue-city distance inside the fatigue indices. | 9.534356884e-05 |
| $\beta$ | The schedule coefficient weights the prior strength-of-schedule adjustment. | 0.7081901219 |
| $\phi$ | The lead coefficient weights the logarithmic lead-retention adjustment. | 2 |
| $\lambda$ | The performance coefficient weights relative box-score performance. | 0.25 |
| $10$ | The probability exponent uses a fixed base of ten. | 10 (fixed) |
| $3$ | The fatigue indices divide absolute time-zone change by this fixed hourly scale. | 3 hours (fixed) |
| $R$ | The Haversine calculation uses this fixed Earth-radius approximation. | 6371 km |

### Learned feature weights

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $\alpha_1$ | The normalized weight multiplies scaled net efficiency. | 0.0006686328527 |
| $\alpha_2$ | The normalized weight multiplies scaled effective field-goal percentage. | 0.0008033843254 |
| $\alpha_3$ | The normalized weight multiplies scaled true shooting percentage. | 0.008884867219 |
| $\alpha_4$ | The normalized weight multiplies scaled offensive-rebound rate. | 0.0007283531314 |
| $\alpha_5$ | The normalized weight multiplies scaled defensive-rebound rate. | 0.1613285001 |
| $\alpha_6$ | The normalized weight multiplies scaled assist-to-turnover ratio. | 0.8047679813 |
| $\alpha_7$ | The normalized weight multiplies scaled turnover fraction. | 0.01518263624 |
| $\alpha_8$ | The normalized weight multiplies scaled steal rate. | 0.007635644786 |

### Matchup and rating-update quantities

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $i,j,O$ | In the probability equation, i is the home team and j the away team; O denotes an opponent in feature derivations. | Team identifiers |
| $g,t$ | The index g labels a game; t labels a team in win-rate notation and a time instant in the offset function. | Context dependent |
| $r_i,r_j$ | These are the team ratings available before the game. | Carryover; first anchor 1500 |
| $r_{\mathrm{new}}$ | This is a team rating after its game update, before league recentering. | Varies by game |
| $p_i,p_j$ | These are the complementary pregame probabilities of a home and away win. | Between 0 and 1; sum 1 |
| $z_i$ | The probability exponent combines the rating difference, home advantage, and fatigue adjustment. | Varies by matchup |
| $h$ | The venue indicator enables home advantage at a home venue and removes it at a neutral venue. | 1 home; 0 neutral |
| $RD_i,RD_j$ | Rest is the number of intervening Eastern-calendar dates since the previous game. | Varies; opener 3 days |
| $TD_i,TD_j$ | Travel is the estimated distance between consecutive venue cities. | Varies; opener 0 km |
| $TZ_i,TZ_j$ | Time-zone change compares dated venue offsets at the current tip-off. | Varies; opener 0 hours |
| $F_i,G_i$ | The two empirical indices combine each side's rest, travel, and time-zone context. | Varies; positive |
| $y_i\;(y)$ | The observed outcome is one for a win and zero for a loss. | 1 win; 0 loss |
| $s_i\;(s)$ | The result sign equals twice the win indicator minus one. | +1 win; -1 loss |
| $S_i\;(S)$ | Schedule strength combines the opponent's prior win rate and its prior opponents' win rates. | Varies; empty history 0.5 |
| $W_t$ | The smoothed prior win rate equals (prior wins + 1) divided by (prior games + 2). | Varies; no games 0.5 |
| $w_t,n_t$ | These are the wins and games observed for a team before the forecast cutoff. | Nonnegative integer counts |
| $\overline W_{\mathrm{opp\ history}}$ | This is the mean prior win rate of the opponent's previous opponents, counting repeats. | Varies; empty mean 0.5 |
| $LL_i,LL_j$ | Largest lead is the maximum points advantage achieved by each team during the completed game. | Nonnegative point counts |
| $L_i\;(L)$ | Lead retention divides absolute final margin by the larger of both teams' largest leads. | Greater than 0; at most 1 |
| $\mathrm{Score}$ | The box-score total is the weighted sum of the scaled box-score features. | Varies by team-game |
| $\mathrm{Perf}$ | The aggregate game performance factor (AGPF) applies a clipped sigmoid to the weighted Score. | From 0.000001 to 0.999999 |
| $\mathrm{PriorPerf}$ | The baseline is the expanding mean of the team's prior game-performance values. | Varies; opener uses current Perf |
| $P$ | The performance adjustment factor (PAF) compares current game performance with its prior baseline and clips the ratio. | From 0.25 to 4; opener 1 |
| $n$ | The prior-performance average divides the sum of a team's earlier game-performance scores by this count. | Number of prior team games |
| $M_S$ | The schedule multiplier equals one plus the result sign times beta times schedule strength. | Varies by game |
| $M_L$ | The lead multiplier equals one plus phi times the base-two logarithm of one plus lead retention. | Varies by game |
| $M_P$ | The performance multiplier equals one plus the result sign times lambda times (P minus one). | Varies by game |
| $\Delta r$ | The rating change equals the base outcome error multiplied by the three adjustment factors. | Varies by game |

### Box-score features and counts

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $X_1$ | The feature measures point differential per 100 estimated team possessions. | Varies by team-game |
| $X_2$ | The feature credits three-point makes with half an additional made shot. | Varies by team-game |
| $X_3$ | The feature measures points per twice the estimated shooting opportunities. | Varies by team-game |
| $X_4$ | The feature divides offensive rebounds by offensive rebounds plus opponent defensive rebounds. | Varies by team-game |
| $X_5$ | The feature divides defensive rebounds by defensive rebounds plus opponent offensive rebounds. | Varies by team-game |
| $X_6$ | The feature divides assists by player turnovers, using a denominator of one for zero turnovers. | Varies by team-game |
| $X_7$ | The feature divides player turnovers by field-goal attempts plus 0.44 free-throw attempts plus player turnovers. | Varies by team-game |
| $X_8$ | The feature divides steals by estimated opponent possessions. | Varies by team-game |
| $x_k$ | The scaled features follow (X1/10, X2, X3, X4, X5, X6/3, -X7, X8). | Fixed transformation |
| $\mathrm{Poss},\mathrm{Poss}_O$ | Estimated possessions equal field-goal attempts plus 0.44 free-throw attempts minus offensive rebounds plus player turnovers. | Varies; coefficient 0.44 |
| $PTS,PTS_O$ | These counts record points scored by the team and its opponent. | Points in the completed game |
| $FGM,FGA$ | These counts record field goals made and attempted. | Nonnegative integer counts |
| $3PM$ | This count records made three-point field goals. | Nonnegative integer count |
| $FTA$ | This count records free throws attempted. | Nonnegative integer count |
| $OREB,DREB$ | These counts record offensive and defensive rebounds; an O subscript denotes opponent counts. | Nonnegative integer counts |
| $AST,TOV,STL$ | These counts record assists, summed player turnovers, and steals. | Nonnegative integer counts |

### Fitting, evaluation, and travel notation

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $\theta$ | The fitted parameter vector contains seven scalar coefficients and seven independent feature-weight logits. | 14 free coordinates |
| $\mathcal L(\theta)$ | Training loss is the mean binary log loss across eligible training games. | 0.6159695469 at fitted solution |
| $N$ | The number of eligible games normalizes a stated fitting or evaluation score. | 5370 release fit; 3690 new evaluation |
| $u_1$ | This softmax logit parameterizes feature weight alpha1 relative to alpha8. | -2.435347556 |
| $u_2$ | This softmax logit parameterizes feature weight alpha2 relative to alpha8. | -2.251749454 |
| $u_3$ | This softmax logit parameterizes feature weight alpha3 relative to alpha8. | 0.1515221307 |
| $u_4$ | This softmax logit parameterizes feature weight alpha4 relative to alpha8. | -2.349796664 |
| $u_5$ | This softmax logit parameterizes feature weight alpha5 relative to alpha8. | 3.050615273 |
| $u_6$ | This softmax logit parameterizes feature weight alpha6 relative to alpha8. | 4.657726628 |
| $u_7$ | This softmax logit parameterizes feature weight alpha7 relative to alpha8. | 0.6873250356 |
| $u_8$ | The final softmax logit is fixed to identify the normalized feature weights. | 0 (fixed) |
| $\varphi_1,\varphi_2,\ell_1,\ell_2$ | These are the latitudes and longitudes of consecutive venue cities, expressed in radians. | Varies by venue |
| $a_v$ | The Haversine intermediate combines the angular latitude and longitude differences. | Between 0 and 1 |
| $v,o(v,t)$ | The venue v and its UTC-offset function define a location's dated time-zone offset. | Venue dependent; hours |
| $\ln,\log_2,\exp$ | These functions are the natural logarithm, base-two logarithm, and natural exponential. | Function definitions |
| $\operatorname{clip}$ | Clipping limits an input to its stated lower and upper bounds. | Bounds stated above |

</details>

## Run locally

Use Python 3.12 and run commands from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The committed snapshots are sufficient to run the app. No API key or source collection is required. The current model carries ratings across seasons; preseason results are excluded. Archived v0.2 outputs retain their original resets.

## Data and code

The repository includes **6,150 games and 12,300 team-game records** across five complete regular seasons, 2021–22 through 2025–26. Basketball records come from ESPN through SportsDataverse archives and primary summaries; official NBA reports supply timestamped injury designations, and GeoNames supplies city coordinates and time zones.

| Directory | Contents |
| --- | --- |
| `nba_forecast/` | Rating engine, ingestion, replay, fitting, and live state |
| `data/seasons/` | Clean records, derived features, historical snapshots, live ledger |
| `models/` | Frozen parameters, fitting reports, and comparator results |
| `scripts/` | Collection, fitting, publishing, and evaluation commands |
| `tests/` | Model, data, timing, live-state, and interface checks |
| `paper/` | Technical paper and LaTeX source |
| `docs/` | Dataset guide, reproducibility instructions, and evaluation results |

- [Data and sources](docs/DATA.md): file definitions, validation, timing, attribution, and reuse notices.
- [Development and operation](docs/DEVELOPMENT.md): research reproduction, tests, updates, hosting, and contribution guidelines.
- [Evaluation](docs/EVALUATION.md): simple Elo comparisons, chronological diagnostics, and uncertainty.

## License

Original project code and documentation use the [MIT License](LICENSE). Provider records, raw-source test fixtures, datasets, and third-party materials retain their separate rights and attribution notices; see [data and sources](docs/DATA.md#sources-and-reuse).

## Understanding forecasts and fair comparisons

The matchup details show an exact sequential reconstruction: ratings only → home court → rest/travel → injury inputs and fitted recalibration. These percentage-point changes depend on that order and are not causal player-impact estimates. Recent form excludes games unfinished at the forecast cutoff. Prior-season ranks and returning observed minutes provide context; neither is a confirmed current roster or a confidence grade.

The performance view separates historical chronological backtests, original issued predictions for the selected season, and current-method replays. Five-point favorite probability bins show sample counts, mean predictions, actual win rates and sampling intervals for chronological or issued forecasts only, excluding training replays.

Run `python scripts/audit_comparisons.py` before comparing changes. The audit rejects unequal game sets, duplicates, altered outcomes, cutoffs, eligibility, source-snapshot IDs or invalid probabilities. A single declared warmup filter applies to every model, and the shared sample ID and game list are saved in `models/nba-v0.3/matched-evaluation.json`. The three current historical procedures retain their original scores on the same 3,690 games; no model is allowed to omit difficult or missing-report games from its comparison.

## Forecast reliability indicators

The **Matchup** tab provides a searchable upcoming-game lookup and reuses the exact forecast explanation and reliability panels from **Games**. The **Accuracy** tab provides searchable evidence-source, season and team selectors, season scores, team expected/actual wins and calibration by probability band. These additions leave Teams, Games and Methodology intact. Choose an upcoming game in **Accuracy evidence cutoff** to reproduce its pregame evidence window; issued evidence then also matches that forecast's model fingerprint. Use **All available seasons** to match the full Games historical benchmark.

Accuracy keeps chronological backtests, original issued forecasts and current-method replays separate. Training replays are labeled historical fit and excluded from calibration reliability tables. Each overall game is counted once, while team summaries include one appearance for each side. Expected wins are summed probabilities; calibration gap is actual minus mean forecast in percentage points, not an accuracy percentage. The read-only explorer checks IDs, teams, results, scores and pregame cutoffs against the stored season records, and rejects stale replays using the same bundle/source hashes as Games. A scheduled tip-off retained by an immutable issued forecast can differ from the completed-game source; exports preserve both times and require the cutoff to precede both. Integrity failures withhold Accuracy scores rather than silently dropping conflicting games.

Upcoming matchups summarize captured input status, league-wide team strength and current-season evidence. Past-game details provide the same panels at the selected forecast's pregame cutoff. Expand **Inspect forecast reliability** for report coverage, unmatched-player/missing-history counts, unresolved availability, captured timestamps, prior completed-game counts and calibration by favorite-probability band. Historical chronological evidence is separated from same-bundle original issued forecasts; training replays are excluded. Counts and sampling intervals accompany observed rates. Snapshot freshness appears only in upcoming forecast details.

These are observable input checks, not a numerical confidence grade. The early-season flag uses the existing ten-game evaluation warmup; freshness uses the two-hour collection interval. The captured injury/recalibration adjustment is shown against base Elo; player-availability scenario ranges are not available. The page does not change probabilities or collect new inputs.

The evidence view also separates league-wide strength from matchup favoritism, shows the favored team’s base-to-published probability change, and provides team-specific calibration bands with counts, expected/actual rates and observed-rate sampling intervals. A displayed pooled historical error uses 80 league-reference team appearances and does not revise the forecast. Earlier chronological evidence and same-bundle original issued evidence remain separate. Reported-player minutes/value proxies are displayed only when their saved history state matches the forecast; unknown values stay blank. Freshness remains in details rather than the main evidence summary.
