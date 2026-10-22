# NBA Elo Forecast

NBA team ratings and pregame win probabilities, with historical backtesting and automatic after-game updates. This project is adapted from work developed for the Wharton Data Science Competition.

[Application](https://eshan-nba-elo-forecast.streamlit.app/) · [Technical paper](paper/main.pdf) · [LaTeX source](paper/main.tex)

## What it does

- Ranks all NBA teams by Elo and estimates matchup win probabilities.
- Displays upcoming forecasts and completed-game outcomes.
- Supports the current season and five historical seasons, with downloadable datasets.
- Collects results every two hours; open pages refresh saved snapshots every minute.

The frontend reads stored outputs rather than scraping or fitting on page load. The live ledger preserves issued forecasts through source corrections; games discovered after completion never receive fabricated pregame predictions.

## Historical performance

Model **0.2.0** was trained on 2021–22 through 2023–24. Constants were frozen before evaluating the following seasons. Scoring begins once both teams have played ten games; earlier games still update ratings.

| Evaluation | Games | Log loss ↓ | Brier score ↓ | Winner accuracy |
| --- | ---: | ---: | ---: | ---: |
| 2024–25 validation | 1,075 | 0.6043 | 0.2088 | 66.42% |
| 2025–26 held-out test | 1,075 | 0.5925 | 0.2035 | 68.56% |
| Simple Elo, same 2025–26 test | 1,075 | 0.6018 | 0.2073 | 66.79% |

These are reconstructed historical forecasts, not measured live performance. Probability scores are the primary measures; accuracy is secondary. Some fitted weights are unstable or reach their bounds. See [evaluation results](docs/EVALUATION.md) for comparisons and limitations, and the [paper](paper/main.pdf) for equations and derivations.

## Symbol dictionary

The dictionary uses the notation from the paper and dashboard. Constants are rounded for display; the frozen [parameter file](models/nba-v0.2/parameters.json) retains full precision. Game-dependent quantities have no single numerical value. Subscripts identify the team or game, and the rating-update equation applies to each team using its own probability. Season carryover is not implemented in model 0.2.0.

<details>
<summary>Notation, English meanings, and numerical values</summary>

### Fitted constants and fixed scales

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $K$ | The base update coefficient controls how much a game can change Elo. | 12.21734709 |
| $H$ | Home advantage adds this many Elo points to the home-side rating difference. | 41.55284709 |
| $c$ | The fixed rating scale converts Elo differences into probability differences. | 497.3558141 (fixed) |
| $\gamma$ | The fatigue coefficient weights the logarithm of the rest/travel index ratio. | 0.1647242036 |
| $\nu$ | The travel coefficient weights venue-city distance inside the fatigue indices. | 0.0001097348541 |
| $\beta$ | The schedule coefficient weights the prior strength-of-schedule adjustment. | 0.9785483342 |
| $\phi$ | The lead coefficient weights the logarithmic lead-retention adjustment. | 2 |
| $\lambda$ | The performance coefficient weights relative box-score performance. | 0.25 |
| $10$ | The probability exponent uses a fixed base of ten. | 10 (fixed) |
| $3$ | The fatigue indices divide absolute time-zone change by this fixed hourly scale. | 3 hours (fixed) |
| $R$ | The Haversine calculation uses this fixed Earth-radius approximation. | 6371 km |

### Learned feature weights

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $\alpha_1$ | The normalized weight multiplies scaled net efficiency. | 0.1619541794 |
| $\alpha_2$ | The normalized weight multiplies scaled effective field-goal percentage. | 0.004364883064 |
| $\alpha_3$ | The normalized weight multiplies scaled true shooting percentage. | 0.006380439345 |
| $\alpha_4$ | The normalized weight multiplies scaled offensive-rebound rate. | 0.002773641359 |
| $\alpha_5$ | The normalized weight multiplies scaled defensive-rebound rate. | 0.6869916183 |
| $\alpha_6$ | The normalized weight multiplies scaled assist-to-turnover ratio. | 0.07304149277 |
| $\alpha_7$ | The normalized weight multiplies scaled turnover fraction. | 0.007925905426 |
| $\alpha_8$ | The normalized weight multiplies scaled steal rate. | 0.05656784034 |

### Matchup and rating-update quantities

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $i,j,O$ | In the probability equation, i is the home team and j the away team; O denotes an opponent in feature derivations. | Team identifiers |
| $g,t$ | The index g labels a game; t labels a team in win-rate notation and a time instant in the offset function. | Context dependent |
| $r_i,r_j$ | These are the team ratings available before the game. | Varies; season opener 1500 |
| $r_i^{+}\;(r^{+})$ | This is a team rating after its game update, before league recentering. | Varies by game |
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
| $\mathcal O(j),\overline W_{\mathcal O(j)}$ | The opponent-history collection includes repeats; its mean uses those opponents' smoothed prior win rates. | Varies; empty mean 0.5 |
| $LL_i,LL_j$ | Largest lead is the maximum points advantage achieved by each team during the completed game. | Nonnegative point counts |
| $L_i\;(L)$ | Lead retention divides absolute final margin by the larger of both teams' largest leads. | Greater than 0; at most 1 |
| $U$ | The aggregate is the weighted sum of the scaled box-score features. | Varies by team-game |
| $A$ | The aggregate game performance factor (AGPF) applies a clipped sigmoid to U. | From 0.000001 to 0.999999 |
| $\overline A_{<g}$ | The baseline is the expanding mean of the team's prior AGPF values. | Varies; opener uses current A |
| $Q_i\;(Q)$ | The performance adjustment factor (PAF) compares current AGPF with its prior baseline and clips the ratio. | From 0.25 to 4; opener 1 |

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
| $\widetilde X_k$ | The scaled vector is (X1/10, X2, X3, X4, X5, X6/3, -X7, X8). | Fixed transformation |
| $\widehat P,\widehat P_O$ | Estimated possessions equal field-goal attempts plus 0.44 free-throw attempts minus offensive rebounds plus player turnovers. | Varies; coefficient 0.44 |
| $PTS,PTS_O$ | These counts record points scored by the team and its opponent. | Points in the completed game |
| $FGM,FGA$ | These counts record field goals made and attempted. | Nonnegative integer counts |
| $3PM$ | This count records made three-point field goals. | Nonnegative integer count |
| $FTA$ | This count records free throws attempted. | Nonnegative integer count |
| $OREB,DREB$ | These counts record offensive and defensive rebounds; an O subscript denotes opponent counts. | Nonnegative integer counts |
| $AST,TOV,STL$ | These counts record assists, summed player turnovers, and steals. | Nonnegative integer counts |

### Fitting, evaluation, and travel notation

| Symbol | Meaning | Numerical value or range |
| --- | --- | --- |
| $\tau_g,\mathcal F_{\tau_g}$ | The cutoff time and its information set specify what is available when a forecast is made. | Varies by game |
| $\theta$ | The fitted parameter vector contains seven scalar coefficients and seven independent feature-weight logits. | 14 free coordinates |
| $\mathcal L(\theta)$ | Training loss is the mean binary log loss across eligible training games. | 0.6282097079 at fitted solution |
| $N$ | The number of eligible games normalizes a stated fitting or evaluation score. | 3220 training; 1075 test |
| $u_1$ | This softmax logit parameterizes feature weight alpha1 relative to alpha8. | 1.05187282 |
| $u_2$ | This softmax logit parameterizes feature weight alpha2 relative to alpha8. | -2.561849232 |
| $u_3$ | This softmax logit parameterizes feature weight alpha3 relative to alpha8. | -2.182203674 |
| $u_4$ | This softmax logit parameterizes feature weight alpha4 relative to alpha8. | -3.015279605 |
| $u_5$ | This softmax logit parameterizes feature weight alpha5 relative to alpha8. | 2.49688146 |
| $u_6$ | This softmax logit parameterizes feature weight alpha6 relative to alpha8. | 0.2555870419 |
| $u_7$ | This softmax logit parameterizes feature weight alpha7 relative to alpha8. | -1.965304069 |
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

The committed snapshots are sufficient to run the app. No API key or source collection is required. Each season starts teams at 1500; preseason results are excluded.

## Data and code

The repository includes **6,150 games and 12,300 team-game records** across five complete regular seasons, 2021–22 through 2025–26. Basketball records come from ESPN through SportsDataverse archives and primary summaries; GeoNames supplies city coordinates and time zones.

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
