"""Streamlit season browser over versioned forecast snapshots."""

from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from nba_forecast.seasons import load_index, load_season
from nba_forecast.ui import native_select

ROOT = Path(__file__).resolve().parent
ARCHIVES = ROOT / "data" / "seasons"
PUBLIC_MODEL = 'injury'


def model_frame(records):
    """Display the published forecast; preserve older issued model versions."""
    rows = []
    for original in records:
        row = dict(original)
        row['Coverage'] = {'complete': 'Both teams submitted', 'partial_or_unsubmitted': 'Partial / unsubmitted',
                           'elo_fallback': 'Elo fallback'}.get(row.get('injury_status'), 'Earlier model')
        source = row.get('injury_source')
        row['Injury report'] = pd.to_datetime(source['published_at']).tz_convert('America/New_York').strftime('%b %d, %I:%M %p %Z') if source else 'Unavailable'
        rows.append(row)
    return pd.DataFrame(rows)

st.set_page_config(page_title="NBA Elo Forecast", page_icon="🏀", layout="wide",
                   menu_items={"About": "NBA Elo Forecast — team ratings and pregame probabilities."})
st.title("NBA Elo Forecast")
st.caption("Team strength, matchup probabilities, and the record behind each forecast.")

@st.fragment(run_every="60s")
def render_dashboard():
    today = datetime.now(ZoneInfo("America/New_York")).date()
    entries, current = load_index(ARCHIVES, today)
    lookup = {e["season"]: e for e in entries}
    selected = native_select("Season", list(lookup), index=list(lookup).index(current),
                            format_func=lambda s: s + (" · Current" if s == current else " · Archive"),
                            key="selected_season")
    archive = load_season(ARCHIVES, lookup[selected])
    version_three = bool(archive and archive.get('result', {}).get('model_version') == '0.3.0')
    teams_tab, games_tab, method_tab = st.tabs(["Teams", "Games", "Methodology"])

    with teams_tab:
        st.caption("Compare team strength for the selected season. Teams are ordered by Elo, with higher ratings indicating stronger teams; ratings change as completed games are processed.")
    with games_tab:
        st.caption("Explore win probabilities for upcoming games and compare past predictions with final outcomes. Historical seasons show reconstructed forecasts; current-season games retain predictions actually issued before tip-off.")
    with method_tab:
        st.caption("See how matchup probabilities and Elo updates are calculated, explore the fitted constants, and review how accurately the model's probabilities match game outcomes.")
        st.html("""<style>
            [data-testid="stLatex"] .katex-display {
                overflow-x: auto;
                overflow-y: hidden;
                padding-block: 0.35rem;
            }
        </style>""")
        st.subheader("Pregame win probability")
        st.latex(r"p_i=\frac{1}{1+10^{z_i}},\qquad z_i=\frac{r_j-r_i-Hh}{c}+\gamma\ln(F_i/G_i),\qquad p_j=1-p_i")
        st.markdown(r"""
- **Teams:** $i$ is the home team and $j$ is the away team.
- **Win probability ($p_i$, $p_j$):** each team's predicted chance of winning before tip-off.
- **Elo ratings ($r_i$, $r_j$):** the teams' pregame strength ratings.
- **Home advantage ($Hh$):** fitted advantage $H$, with $h=1$ at home and $h=0$ at a neutral venue.
- **Rating scale ($c$):** converts Elo differences into probability differences.
- **Rest and travel context ($F_i/G_i$):** combines rest, estimated travel, and time-zone changes.
- **Fatigue weight ($\gamma$):** controls the influence of that context on the probability.
        """)
        st.subheader("Elo update after a completed game")
        st.latex(r"r_{i,\mathrm{new}}=r_i+K(y_i-p_i)(1+s_i\beta S_i)(1+\phi\log_2(1+L_i))(1+s_i\lambda(P_i-1))")
        st.markdown(r"""
- **Updated Elo ($r_{i,\mathrm{new}}$):** the team's rating after the completed game, before league recentering.
- **Outcome ($y_i$):** $1$ for a win and $0$ for a loss.
- **Prediction error ($y_i-p_i$):** the difference between the outcome and that team's pregame win probability.
- **Update size ($K$):** the base sensitivity of Elo to the result.
- **Result direction ($s_i$):** $s_i=2y_i-1$, giving $+1$ for a win and $-1$ for a loss.
- **Schedule strength ($S_i$):** the opponent's prior record and its previous opponents' records, weighted by $\beta$.
- **Lead retention ($L_i$):** final margin divided by the largest lead of either team, weighted by $\phi$.
- **Relative performance ($P_i$):** box-score performance compared with the team's prior average, weighted by $\lambda$.
        """)
        st.caption("Only prior information enters the probability. Outcomes and current-game box scores enter the rating update after completion; league ratings are then recentered at 1500.")
        if version_three:
            st.subheader('Season carryover')
            st.latex(r'r_{\mathrm{start}}=1500+\rho(r_{\mathrm{previous\ final}}-1500),\qquad \rho=0.5')
            st.markdown('- **Carryover ($\\rho$):** retain half the previous season’s rating deviation from 1500. Season records reset.')
            st.subheader('Injury-adjusted probability')
            st.latex(r'q_i=\sigma\!\left(\operatorname{logit}(p_i)+b+\mathbf{w}^{\mathsf T}\mathbf{d}_i\right),\qquad q_j=1-q_i')
            st.markdown(r'''
- **Base probability ($p_i$):** the original Elo forecast; this remains the probability used in rating updates.
- **Published probability ($q_i$):** the single dashboard forecast after the fitted injury correction.
- **Inputs ($\mathbf{d}_i$):** standardized base log odds, injury-status contributions based on earlier player minutes/value, and missing-report indicators.
- **Fitted correction ($b,\mathbf{w}$):** regularized coefficients selected using earlier seasons only.
            ''')
            st.caption('Unavailable or stale report/game coverage falls back to carryover Elo. An unsubmitted team is recorded as unknown, never healthy. Neither probability correction feeds back into Elo.')
            with st.expander('How injury data becomes a forecast'):
                st.markdown('''
1. **Collect:** the scheduled job checks official NBA injury PDFs every two hours. It verifies the publication time and matches the report to the game, teams and date. Reports more than 16 hours old or dated in the future are rejected.
2. **Match players:** normalized report names map to ESPN player IDs. Earlier completed box scores supply minutes and a descriptive Game Score per minute. Ambiguous names and missing histories remain unknown.
3. **Build features:** expected minutes use a ten-appearance exponential half-life. Value per minute is shrunk toward 0.3 using 80 prior minutes. Out, Doubtful, Questionable and Probable each have separate minutes and value totals; their effects are learned rather than assigned fixed absence probabilities.
4. **Predict:** home-minus-away status totals and coverage indicators enter the fitted logistic correction below. Coefficients and standardization are frozen from earlier seasons. Every issued revision stores its report timestamp and hash.
5. **Update after games:** completed results update Elo using the base probability. Injury adjustments affect the published win probability directly; they do not change the Elo rankings.
                ''')
                st.latex(r'A_{t,s}=\sum_{a\in(t,s)}\bar m_a/240,\qquad B_{t,s}=\sum_{a\in(t,s)}\bar m_a v_a/80,\qquad v_a=(V_a+24)/(M_a+80)')
                st.markdown('- **Status totals ($A_{t,s}, B_{t,s}$):** expected minutes and expected minutes times value for team $t$, status $s$.\n- **Player history ($M_a,V_a$):** exponentially discounted prior minutes and Game Scores.\n- **Correction inputs:** home-minus-away totals, base log odds, and explicit report/player-history coverage indicators, standardized using training means and scales.')
                st.caption('If no verified report covers the matchup, the forecast equals base Elo. Partial submissions use missingness indicators. The next scheduled collection picks up report changes; the page itself reads saved outputs.')
            st.caption('Methodological basis: Bradley–Terry logistic paired comparisons with sequential Elo updates. Whole-History Rating’s joint optimization of past rating trajectories is not implemented. Full research references are in the technical paper.')
        with st.expander("Rest, travel, and time-zone inputs"):
            st.latex(r"F_i=RD_j+e^{|TZ_i|/3}+\nu TD_i,\qquad G_i=RD_i+e^{|TZ_j|/3}+\nu TD_j")
            st.markdown(r"""
- **Rest ($RD$):** intervening calendar days between games.
- **Travel ($TD$):** estimated distance between venue cities in kilometres.
- **Time-zone change ($TZ$):** the change in venue time-zone offsets in hours.
- **Travel weight ($\nu$):** the fitted coefficient on estimated travel.
            """)
            st.caption("The paper includes the complete feature derivations and fitting method.")

    if archive is None:
        with teams_tab:
            st.info("This season's ratings are being prepared. Select an archived season to explore available history.")
        with games_tab:
            st.info("No forecasts have been published for this season yet.")
        result = None
    elif archive["status"] == "prepared":
        with teams_tab:
            st.info("All teams start at 1500. NBA parameters are fitted; live forecasts for this season have not been published yet.")
            st.dataframe(pd.DataFrame(archive["teams"])[["team", "elo"]].rename(columns={"team": "Team", "elo": "Initial Elo"}),
                         hide_index=True, width="stretch")
        with games_tab:
            st.info("No forecasts have been published for this season yet.")
        result = None
    else:
        result = archive["result"]
        is_live = archive["status"] == "live"
        if is_live:
            updated = pd.to_datetime(archive["published_at"], utc=True).tz_convert("America/New_York")
            st.caption(f"Observed forecast snapshot · Last updated {updated:%b %d, %Y at %I:%M %p %Z}")
            st.caption("Forecast updates are scheduled every two hours. This page refreshes the saved snapshot each minute.")
            status_path = ARCHIVES / selected / "update_status.json"
            if status_path.exists() and json.loads(status_path.read_text())["state"] == "failed":
                st.warning("The latest update failed. Showing the last valid ratings and forecasts.")
            if version_three and archive['_internal'].get('auxiliary_status', {}).get('injuries', {}).get('state') == 'unavailable':
                st.warning('The official injury report is unavailable or stale. Upcoming forecasts use the carryover Elo fallback until a valid report is collected.')
        else:
            coverage_label = "Complete regular season" if archive["status"] == "complete_historical_replay" else "Partial season"
            st.caption(f"Historical model replay · {archive['coverage']['start']} to {archive['coverage']['end']} · {coverage_label}")
        with teams_tab:
            st.subheader("Team ratings")
            if is_live and not archive["coverage"]["parsed"]:
                st.info('Season initialization retains 50% of the previous season’s Elo deviation from 1500. Preseason results are excluded.' if version_three else
                        'Season initialization: all teams start at 1500. Preseason results are excluded; ratings will change after regular-season games.')
            rankings = pd.DataFrame(result["rankings"])
            shown = rankings[["team", "elo", "games", "wins"]].copy()
            shown["Record"] = shown["wins"].astype(str) + "–" + (shown["games"] - shown["wins"]).astype(str)
            shown = shown[["team", "elo", "Record", "games"]].rename(columns={"team": "Team", "elo": "Elo", "games": "Games"})
            st.dataframe(shown, hide_index=True, width="stretch", column_config={"Elo": st.column_config.NumberColumn(format="%.1f")})
            team = native_select("Team history", sorted(rankings["team"].tolist()), key="team_history")
            history = []
            for game in result["predictions"]:
                side = "home" if game["home"] == team else "away" if game["away"] == team else None
                if side:
                    history.append({"Date": pd.to_datetime(game["start"]), "Elo": game[side + "_rating_after"]})
            if history:
                st.line_chart(pd.DataFrame(history).set_index("Date"), y="Elo")
        with games_tab:
            st.subheader("Games")
            if version_three:
                st.caption('Elo + injuries is the published model, selected for the lowest retrospective log loss and Brier score. Archived forecasts retain the model version originally used.')
                st.caption('Coverage describes team report submission. Unmatched players and missing player histories remain explicitly unknown.')
            upcoming = archive.get("upcoming", [])
            if upcoming:
                future = model_frame(upcoming)
                future["start"] = pd.to_datetime(future["start"], utc=True).dt.tz_convert("America/New_York").dt.strftime("%b %d, %I:%M %p %Z")
                future["Home win %"] = future["home_probability"] * 100
                future["Away win %"] = future["away_probability"] * 100
                st.markdown("**Upcoming**")
                columns = ["start", "home", "away", "Home win %", "Away win %"]+(['Coverage', 'Injury report'] if version_three else [])
                st.dataframe(future[columns].rename(
                    columns={"start": "Tip-off", "home": "Home", "away": "Away"}), hide_index=True,
                    column_config={"Home win %": st.column_config.NumberColumn(format="%.1f%%"),
                                   "Away win %": st.column_config.NumberColumn(format="%.1f%%")})
            if is_live:
                st.caption("Upcoming probabilities use current ratings and announced rest/travel schedules, and are revised when new results or schedule changes arrive.")
            if archive.get("awaiting_final"):
                st.info(f"{len(archive['awaiting_final'])} started or delayed game(s) awaiting validated final data.")
            if result["predictions"]:
                st.markdown("**Past games**")
                frame = model_frame(result["predictions"])
                frame["Date"] = pd.to_datetime(frame["start"], utc=True).dt.tz_convert("America/New_York").dt.date
                dates = sorted(frame["Date"].unique(), reverse=True)
                picked_date = native_select("Game date", dates, key=f"game_date_{selected}")
                daily = frame[frame["Date"] == picked_date].copy()
                daily["Home win %"] = daily["home_probability"] * 100
                daily["Away win %"] = daily["away_probability"] * 100
                daily["Final score"] = daily["home_score"].astype(str) + "–" + daily["away_score"].astype(str)
                daily["Winner"] = daily.apply(lambda g: g["home"] if g["home_win"] else g["away"], axis=1)
                columns = ["home", "away", "Home win %", "Away win %", "Final score", "Winner"]+(['Coverage'] if version_three else [])
                st.dataframe(daily[columns].rename(
                    columns={"home": "Home", "away": "Away"}), hide_index=True, width="stretch",
                    column_config={"Home win %": st.column_config.NumberColumn(format="%.1f%%"),
                                   "Away win %": st.column_config.NumberColumn(format="%.1f%%")})
                if is_live:
                    st.caption("Probabilities are the last stored forecast before tip-off. A blank probability means the game was backfilled without an issued forecast.")
                else:
                    st.caption("These probabilities were reconstructed from historical data. They were not issued live before those games.")
            else:
                st.info("No completed regular-season games are stored for this season yet.")
        with method_tab:
            if result["status"] == "live_forecasts":
                st.info("Frozen NBA model · Evaluation includes genuinely issued pregame forecasts only. Backfilled games can update ratings but never become live predictions.")
                st.download_button("Download issued forecast history", json.dumps(archive["_internal"]["forecasts"], indent=2),
                                   file_name=f"{selected}-issued-forecasts.json", mime="application/json")
            elif result['status'] == 'retrospective_historical_replay':
                st.info('Retrospective comparison · Each season uses only earlier seasons for fitting and selection. These previously studied outcomes are not a fresh independent test.')
            elif result["status"] == "fitted_historical_replay":
                role = {"training": "Training history", "validation": "Validation season", "held_out_test": "Held-out test season"}[result["evaluation_role"]]
                st.info(f"{role} · Parameters fitted on 2021–22 through 2023–24 and frozen before validation and testing.")
            else:
                st.warning("Unfitted development replay; these scores are a pipeline check.")
            comparison = result.get('model_comparison', {}).get(PUBLIC_MODEL)
            m = comparison['metrics'] if comparison else result["metrics"]
            evaluation_window = 'established'
            if version_three:
                evaluation_window = native_select('Evaluation window', ['all', 'established'],
                                                   format_func=lambda value: 'All games, including openers' if value == 'all' else 'After ten prior games per team',
                                                   key=f'evaluation_window_{selected}')
                if comparison and evaluation_window == 'all':
                    m = comparison['metrics_all_issued']
                st.caption("Scoring: Elo + injuries. Live scores include only forecasts issued with the current frozen model bundle; earlier versions remain in the issued-history download.")
            if m["games"]:
                cols = st.columns(4)
                cols[0].metric("Evaluation games", m["games"])
                cols[1].metric("Brier score", f"{m['brier_score']:.3f}")
                cols[2].metric("Log loss", f"{m['log_loss']:.3f}")
                cols[3].metric("Winner accuracy", f"{m['winner_accuracy']:.1%}")
            st.caption(f"Model {result['model_version']}. "+('Evaluation includes opening games.' if version_three and evaluation_window == 'all' else
                       'Evaluation begins once both teams have played 10 games; opening games still update ratings and retain forecasts.'))
            if is_live and not m["games"]:
                all_scores = comparison['metrics_all_issued'] if comparison else result['metrics_all_issued']
                st.caption(f"{all_scores['games']} completed games have comparable issued forecasts. Primary evaluation waits until both teams have ten prior games.")
            calibration = pd.DataFrame(m["calibration"])
            if not calibration.empty:
                st.dataframe(calibration.rename(columns={"games": "Games", "mean_probability": "Mean forecast",
                                                         "observed_home_win_rate": "Observed home win rate"}), hide_index=True)
            st.subheader("Season datasets")
            if version_three:
                st.download_button('Download published forecasts', json.dumps([{k: v for k, v in row.items() if k not in {'probability_models', 'forecast_features'}} for row in result['predictions']], indent=2),
                                   file_name=f'{selected}-v0.3-forecasts.json', mime='application/json')
            for filename, label in [("team_games.csv", "Clean box scores"), ("model_features.csv", "Original v0.2 model features")]:
                path = ARCHIVES / selected / filename
                if path.exists():
                    st.download_button(label, path.read_bytes(), file_name=f"{selected}-{filename}", mime="text/csv")

    with method_tab:
        st.write("Each season has its own stored history. Model versions and data coverage are preserved so archived results remain interpretable.")
        st.caption("Sources: ESPN records archived by SportsDataverse, validated against primary ESPN summaries where needed; official NBA injury reports; GeoNames venue-city coordinates and time zones. Travel is an estimate between cities.")
        with st.expander("Fitted NBA constants"):
            st.json(result['parameters'] if result else json.loads((ROOT / 'models/nba-v0.3/bundle.json').read_text())['core_parameters'])
        if version_three:
            with st.expander('Published-model historical evaluation'):
                evaluation = json.loads((ROOT/'models/nba-v0.3/evaluation.json').read_text())
                rows = []
                for fold in evaluation['folds']:
                    m = fold['model_comparison'][PUBLIC_MODEL]['metrics_all_issued']
                    rows.append({'Season': fold['season'], 'Games': m['games'], 'Log loss': m['log_loss'],
                                 'Brier': m['brier_score'], 'Winner accuracy': m['winner_accuracy']})
                st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={
                    'Log loss': st.column_config.NumberColumn(format='%.4f'),
                    'Brier': st.column_config.NumberColumn(format='%.4f'),
                    'Winner accuracy': st.column_config.NumberColumn(format='percent')})
                st.caption('Retrospective backtests include opening games and missing-report fallbacks. These are reconstructed results, not live accuracy claims. Research comparisons remain documented in the paper.')
        st.markdown("[Technical paper on GitHub](https://github.com/eshangark/nba-elo-forecast/blob/main/paper/main.pdf)")
        with st.expander("Technical manuscript source"):
            st.download_button("Download LaTeX source", (ROOT / "paper" / "main.tex").read_text(),
                               file_name="nba-elo-forecast.tex", mime="text/plain")


render_dashboard()
