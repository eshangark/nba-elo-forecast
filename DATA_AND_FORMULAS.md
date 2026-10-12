# Data and formula specification

Source: The Billy Beanes, 2025 competition paper, appendix A (pages 7–11). These are transcriptions and implementation questions, not claims that every equation is already suitable for production. Reconcile against the original code when supplied.

## Raw input contract

| Input | Purpose | Candidate free source |
| --- | --- | --- |
| Game ID, teams, date, status, final points | Outcomes, chronological replay, margin, SOS | NBA game logs; schedule and box-score feeds |
| Tip-off timestamp, venue ID and location | Prediction cutoff, home/neutral status, rest/travel | Schedule and box-score metadata |
| PTS, FGM, FGA, 3PM, FTA, OREB, DREB, AST, TOV, STL for both teams | All eight PAF components | Team game logs or box scores |
| Largest lead for each team | LRE | BoxScoreSummaryV3 OtherStats documents biggestLead; verify coverage |
| Arena latitude, longitude, IANA timezone | Haversine distance and dated UTC offsets | Small versioned venue lookup; not yet sourced |
| Prior results and opponent histories | Dynamic SOS and rolling performance | Derived locally |

Use stable IDs, not team names, as keys. Keep one games row and two team-game rows per completed game. Treat null as missing, not zero. Check totals against the opponent row and official final score. A team's never having led is a valid zero requiring a model rule.

## Published formulas

Let i be the home team and j the away team for a non-neutral game. Below, beta numbering follows the appendix, not the differing notation in the body.

    ORTF = RD_j + exp(abs(TzD_i) / 3) + beta_2 * TD_i
    TROF = RD_i + exp(abs(TzD_j) / 3) + beta_2 * TD_j
    z = (r_j - (r_i + HFA)) / c + beta_1 * log(ORTF) - beta_1 * log(TROF)
    p_home = 1 / (1 + b ** z)
    p_away = 1 - p_home

The paper does not clearly specify the unqualified log base. Confirm it in code. HFA is a rating offset, not a probability percentage. Neutral-site handling requires an explicit rule. Compute one home probability and its complement; do not give both teams home advantage.

    SOS_t = (2 * WR_opponent + mean(WR_opponents_of_opponent)) / 3
    LRE = abs(final_point_margin) / largest_lead
    POSS = FGA + 0.44 * FTA - OREB + TOV
    X1 = 100 * (PTS - opponent_PTS) / POSS
    X2 = (FGM + 0.5 * three_PM) / FGA
    X3 = PTS / (2 * (FGA + 0.44 * FTA))
    X4_paper = OREB / (OREB + opponent_OREB)
    X5_paper = DREB / (DREB + opponent_DREB)
    X6 = AST / TOV
    X7 = TOV / (FGA + 0.44 * FTA + TOV)
    X8 = STL / (opponent_FGA + 0.44 * opponent_FTA + opponent_TOV)
    S = sum(alpha_k * Xk for k in 1..8)
    AGPF = S / (1 + S)
    PAF = AGPF / prior_average_AGPF

The paper prints X7 and X8 as percentages. Confirm whether the original implementation used fractions or 0–100 values; mixing units changes the fitted weights. The prior_average above is an intended chronological implementation rule; the appendix's averaging bounds need reconciliation with the code.

    win_delta = k * (1 - p) * (1 + SOS_t) * (1 + beta_3 * log2(1 + LRE)) * (1 + beta_4 * (PAF - 1))
    loss_delta = k * (0 - p) * (1 - SOS_t) * (1 + beta_3 * log2(1 + LRE)) * (1 - beta_4 * (PAF - 1))
    new_rating = old_rating + delta

## Derivation timing

Before tip-off: ratings, home/neutral context, past-only SOS, rest, estimated venue-to-venue travel, timezone changes, and historical performance averages. After final: result, margin, largest lead, current box-score metrics and PAF; then rating updates.

Rest: propose calendar days between game dates minus one (back-to-back = zero), with an explicit season-opener prior. Verify the original convention. No full-season average imputation using future games.

Travel: Haversine between consecutive known venues in kilometres; actual itineraries are unknown. Timezones: dated offsets via IANA zones, accounting for daylight saving. Missing venue details remain flagged.

## Questions to resolve before optimization

- Rebound denominators: standard team OREB fraction uses opponent DREB; standard DREB fraction uses opponent OREB. Preserve a record of any correction to the paper.
- LRE: zero largest lead, and the intended denominator for losing teams.
- AGPF: negative net efficiency can make S negative and S/(1+S) singular near -1; PAF can also divide by zero. Define a stable revision before fitting.
- SOS: season openers, repeated-opponent weighting, and whether histories reset each season.
- Rating drift: asymmetric adjustments are not zero-sum. Define season carryover and centring rules.
- Multiplier bounds: guard against a winning update becoming negative because a fitted performance factor changes sign.
- Identifiability: b and c encode a shared rating-to-log-odds scale; constrain the parameterization rather than freely tuning redundant parameters.
- Regularization and feature scales: fit only from the training partition. Record every formula change and its rationale.

## Original constants (reference only; not NBA estimates)

Initial Elo 1500; b 99.39; c 993.39; HFA 72.52; k 32; beta_1 0.02; beta_2 0.000001; beta_3 0.7; beta_4 0.02. Alphas: 0.25, 0.20, 0.15, 0.10, 0.10, 0.10, 0.05, 0.05.

## Connectivity observations — 2026-10-12

Direct requests from the development host, outside its restricted-network sandbox:

- NBA CDN sample box score 0022400001: HTTP 403.
- NBA CDN scheduleLeagueV2_1: HTTP 403.
- stats.nba.com LeagueGameLog, 2024–25: read timeout at 15 seconds.

These failures do not establish worldwide unavailability or field coverage. No NBA raw dataset was successfully downloaded. Do not bypass access denials. Test from the intended execution environment and consider another documented free source if necessary.

References:
- https://github.com/swar/nba_api
- https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leaguegamelog.md
- https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/boxscoresummaryv3.md
