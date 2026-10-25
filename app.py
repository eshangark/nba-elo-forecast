"""Streamlit season browser over versioned forecast snapshots."""

from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from nba_forecast.seasons import load_index, load_season
from nba_forecast.ui import native_select
from nba_forecast.forecasting import Forecaster
from nba_forecast.live import digest
from nba_forecast.dashboard_views import matchup_overview, performance_view, past_game_details

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
    original_archive = dict(archive) if archive else None
    current_replay = None
    stale_replay = False
    replay_path = ARCHIVES / selected / 'current-model.json'
    if archive and replay_path.exists():
        candidate = json.loads(replay_path.read_text())
        bundle = Forecaster(json.loads((ROOT/'models/nba-v0.3/bundle.json').read_text()))
        if (candidate['result']['forecast_model_sha256'] == bundle.fingerprint
                and candidate['source_result_sha256'] == digest(archive['result'])):
            current_replay = candidate
            archive['result'] = candidate['result']
        else:
            stale_replay = True
    version_three = bool(archive and archive.get('result', {}).get('model_version') == '0.3.0')
    teams_tab, games_tab, method_tab = st.tabs(["Teams", "Games", "Methodology"])

    with teams_tab:
        st.caption("Compare team strength for the selected season. Teams are ordered by Elo, with higher ratings indicating stronger teams; ratings change as completed games are processed.")
    with games_tab:
        st.caption("Explore win probabilities and completed-game outcomes. " +
                   ("Past-game tables replay the current methodology with pregame inputs. Select a matchup to inspect its evidence or original issued forecast where available." if current_replay else
                    "Past games show original stored forecasts while the current-method replay is unavailable."))
        if stale_replay:
            st.info("The current-method replay is being rebuilt for this model or data snapshot. Showing original stored forecasts in the meantime.")
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
            st.caption('Unavailable or stale report/game coverage falls back to carryover Elo. An unsubmitted team is recorded as unknown, never healthy. The injury correction does not feed back into Elo.')
            with st.expander('How injury data becomes a forecast'):
                st.markdown('''
1. **Collect:** the scheduled job checks official NBA injury PDFs every two hours. It verifies the publication time and matches the report to the game, teams and date. Reports more than 16 hours old or dated in the future are rejected.
2. **Match players:** normalized report names map to ESPN player IDs. Earlier completed box scores supply minutes and a descriptive Game Score per minute. Ambiguous names and missing histories remain unknown.
3. **Build features:** expected minutes use a ten-appearance exponential half-life. Value per minute is shrunk toward 0.3 using 80 prior minutes. Out, Doubtful, Questionable and Probable each have separate minutes and value totals; their effects are learned rather than assigned fixed absence probabilities.
4. **Predict:** home-minus-away status totals and coverage indicators enter the fitted logistic correction. Coefficients and standardization are frozen from earlier seasons. Every issued revision stores its report timestamp and hash.
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
            st.markdown(
                "**How to read these forecasts.** Start with win probability, then select a matchup and inspect "
                "**forecast reliability** before deciding. A 70% estimate means a team is favored, but losses are "
                "still expected. Under **Calibration evidence**, compare the mean forecast with the actual win rate: "
                "the league summary pools favorites in a similar probability range; the team table shows how often "
                "each specific team won in its own displayed range. Check the game count and interval together: "
                "small samples give weaker evidence, and the interval describes the historical win rate, not this "
                "game's probability. Check **team strength**, **season evidence** and **Player coverage** too: a "
                "weak team can be favored against a weaker opponent, and incomplete reports or missing player "
                "histories leave uncertainty. Historical results reflect older rosters and models. For past games, "
                "check whether you are viewing an original issued forecast or a replay. Win probability alone "
                "does not establish that a bet is worth its price."
            )
            if version_three:
                st.caption('Elo + injuries is the published model, selected for the lowest retrospective log loss and Brier score.')
                st.caption('Injury data describes report availability. Submitted reports can still contain unmatched players or missing histories.')
            upcoming = archive.get("upcoming", [])
            if upcoming:
                matchup_overview(upcoming,archive,result,ARCHIVES,entries,selected,result.get('forecast_model_sha256',archive.get('_internal',{}).get('forecast_model_sha256')), original_archive=original_archive)
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
                daily["Prediction"] = daily.apply(lambda g: 'Unavailable' if pd.isna(g['home_probability']) else
                                                   'Correct' if int(g['home_probability'] >= 0.5) == g['home_win'] else 'Incorrect', axis=1)
                columns = ["home", "away", "Home win %", "Away win %", "Final score", "Winner", "Prediction"]
                past_table=st.dataframe(daily[columns].rename(
                    columns={"home": "Home", "away": "Away"}), hide_index=True, width="stretch",
                    on_select='rerun',selection_mode='single-row',key=f'past_table_{selected}_{picked_date}',
                    column_config={"Home win %": st.column_config.NumberColumn(format="%.1f%%"),
                                   "Away win %": st.column_config.NumberColumn(format="%.1f%%")})
                if current_replay:
                    st.caption("Current-method retrospective replay. Correct means the team given at least 50% won; an exact 50% tie picks home. Only pregame inputs enter each prediction. Original issued forecasts are preserved separately.")
                elif is_live:
                    st.caption("Original issued forecasts. A blank probability means no pregame forecast was recorded.")
                else:
                    st.caption("Historical reconstructed forecasts; not issued live.")
                st.caption('Select a past-game row or choose a matchup below to inspect its pregame evidence.')
                daily_ids=set(daily['game_id'])
                past_game_details([r for r in result['predictions'] if r['game_id'] in daily_ids],original_archive,result,
                                  bool(current_replay),ARCHIVES,entries,selected,ROOT,past_table.selection.rows)
            else:
                st.info("No completed regular-season games are stored for this season yet.")
        with method_tab:
            performance_view(ROOT,original_archive,result,selected)
            st.subheader("Season datasets")
            if version_three:
                st.download_button('Download selected-season replay' if current_replay else 'Download stored forecasts', json.dumps([{k: v for k, v in row.items() if k not in {'probability_models', 'forecast_features'}} for row in result['predictions']], indent=2),
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
        st.markdown("[Technical paper on GitHub](https://github.com/eshangark/nba-elo-forecast/blob/main/paper/main.pdf)")
        with st.expander("Technical manuscript source"):
            st.download_button("Download LaTeX source", (ROOT / "paper" / "main.tex").read_text(),
                               file_name="nba-elo-forecast.tex", mime="text/plain")


render_dashboard()
