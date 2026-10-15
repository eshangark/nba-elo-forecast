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
    teams_tab, games_tab, method_tab = st.tabs(["Teams", "Games", "Methodology"])

    with method_tab:
        st.html("""<style>
            [data-testid="stLatex"] .katex-display {
                overflow-x: auto;
                overflow-y: hidden;
                padding-block: 0.35rem;
            }
        </style>""")
        st.subheader("Pregame win probability")
        st.latex(r"p_i=\left[1+10^{\frac{r_j-r_i-Hh}{c}+\gamma\ln(F_i/G_i)}\right]^{-1},\qquad p_j=1-p_i")
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
        st.latex(r"r_i^{+}=r_i+K(y_i-p_i)(1+s_i\beta S_i)(1+\phi\log_2(1+L_i))(1+s_i\lambda(Q_i-1))")
        st.markdown(r"""
- **Updated Elo ($r_i^{+}$):** the team's rating after the completed game, before league recentering.
- **Outcome ($y_i$):** $1$ for a win and $0$ for a loss.
- **Prediction error ($y_i-p_i$):** the difference between the outcome and that team's pregame win probability.
- **Update size ($K$):** the base sensitivity of Elo to the result.
- **Result direction ($s_i$):** $s_i=2y_i-1$, giving $+1$ for a win and $-1$ for a loss.
- **Schedule strength ($S_i$):** the opponent's prior record and its previous opponents' records, weighted by $\beta$.
- **Lead retention ($L_i$):** final margin divided by the largest lead of either team, weighted by $\phi$.
- **Relative performance ($Q_i$):** box-score performance compared with the team's prior average, weighted by $\lambda$.
        """)
        st.caption("Only prior information enters the probability. Outcomes and current-game box scores enter the rating update after completion; league ratings are then recentered at 1500.")
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
        else:
            coverage_label = "Complete regular season" if archive["status"] == "complete_historical_replay" else "Partial season"
            st.caption(f"Historical model replay · {archive['coverage']['start']} to {archive['coverage']['end']} · {coverage_label}")
        with teams_tab:
            st.subheader("Team ratings")
            if is_live and not archive["coverage"]["parsed"]:
                st.info("Season initialization: all teams start at 1500. Preseason results are excluded; ratings will change after regular-season games.")
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
            upcoming = archive.get("upcoming", [])
            if upcoming:
                future = pd.DataFrame(upcoming)
                future["start"] = pd.to_datetime(future["start"], utc=True).dt.tz_convert("America/New_York").dt.strftime("%b %d, %I:%M %p %Z")
                future["Home win %"] = future["home_probability"] * 100
                future["Away win %"] = future["away_probability"] * 100
                st.markdown("**Upcoming**")
                st.dataframe(future[["start", "home", "away", "Home win %", "Away win %"]].rename(
                    columns={"start": "Tip-off", "home": "Home", "away": "Away"}), hide_index=True,
                    column_config={"Home win %": st.column_config.NumberColumn(format="%.1f%%"),
                                   "Away win %": st.column_config.NumberColumn(format="%.1f%%")})
            if is_live:
                st.caption("Upcoming probabilities use current ratings and announced rest/travel schedules, and are revised when new results or schedule changes arrive.")
            if archive.get("awaiting_final"):
                st.info(f"{len(archive['awaiting_final'])} started or delayed game(s) awaiting validated final data.")
            if result["predictions"]:
                st.markdown("**Past games**")
                frame = pd.DataFrame(result["predictions"])
                frame["Date"] = pd.to_datetime(frame["start"], utc=True).dt.tz_convert("America/New_York").dt.date
                dates = sorted(frame["Date"].unique(), reverse=True)
                picked_date = native_select("Game date", dates, key=f"game_date_{selected}")
                daily = frame[frame["Date"] == picked_date].copy()
                daily["Home win %"] = daily["home_probability"] * 100
                daily["Away win %"] = daily["away_probability"] * 100
                daily["Final score"] = daily["home_score"].astype(str) + "–" + daily["away_score"].astype(str)
                daily["Winner"] = daily.apply(lambda g: g["home"] if g["home_win"] else g["away"], axis=1)
                st.dataframe(daily[["home", "away", "Home win %", "Away win %", "Final score", "Winner"]].rename(
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
            elif result["status"] == "fitted_historical_replay":
                role = {"training": "Training history", "validation": "Validation season", "held_out_test": "Held-out test season"}[result["evaluation_role"]]
                st.info(f"{role} · Parameters fitted on 2021–22 through 2023–24 and frozen before validation and testing.")
            else:
                st.warning("Unfitted development replay; these scores are a pipeline check.")
            m = result["metrics"]
            if m["games"]:
                cols = st.columns(4)
                cols[0].metric("Evaluation games", m["games"])
                cols[1].metric("Brier score", f"{m['brier_score']:.3f}")
                cols[2].metric("Log loss", f"{m['log_loss']:.3f}")
                cols[3].metric("Winner accuracy", f"{m['winner_accuracy']:.1%}")
            st.caption(f"Model {result['model_version']}. Evaluation begins once both teams have played 10 games; opening games still update ratings and retain forecasts.")
            if is_live and not m["games"]:
                st.caption(f"{result['metrics_all_issued']['games']} completed games have issued forecasts. Primary evaluation waits until both teams have ten prior games.")
            calibration = pd.DataFrame(m["calibration"])
            if not calibration.empty:
                st.dataframe(calibration.rename(columns={"games": "Games", "mean_probability": "Mean forecast",
                                                         "observed_home_win_rate": "Observed home win rate"}), hide_index=True)
            st.subheader("Season datasets")
            for filename, label in [("team_games.csv", "Clean box scores"), ("model_features.csv", "Model inputs and derived features")]:
                path = ARCHIVES / selected / filename
                if path.exists():
                    st.download_button(label, path.read_bytes(), file_name=f"{selected}-{filename}", mime="text/csv")

    with method_tab:
        st.write("Each season has its own stored history. Model versions and data coverage are preserved so archived results remain interpretable.")
        st.caption("Sources: ESPN records archived by SportsDataverse, validated against primary ESPN summaries where needed; GeoNames supplies venue-city coordinates and time zones. Travel is an estimate between cities.")
        with st.expander("Fitted NBA constants"):
            st.json(json.loads((ROOT / "models" / "nba-v0.2" / "parameters.json").read_text()))
        comparison_path = ROOT / "models" / "comparison-v0.2" / "results.json"
        if comparison_path.exists():
            with st.expander("Comparison with simple Elo"):
                comparison = json.loads(comparison_path.read_text())
                rows = []
                for fold in comparison["frozen_release_comparison"]:
                    for label, field in [("Multifactor v0.2", "full_metrics"), ("Fitted simple Elo", "simple_metrics")]:
                        scores = fold[field]
                        rows.append({"Season": fold["evaluation_season"], "Model": label,
                                     "Games": scores["games"], "Log loss": scores["log_loss"],
                                     "Brier": scores["brier_score"], "Winner accuracy": scores["winner_accuracy"]})
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                             column_config={"Log loss": st.column_config.NumberColumn(format="%.4f"),
                                            "Brier": st.column_config.NumberColumn(format="%.4f"),
                                            "Winner accuracy": st.column_config.NumberColumn(format="percent")})
                st.caption("Both models fitted on 2021–22 through 2023–24. Retrospective comparison; four expanding-window checks also favor the multifactor model on probability scores. Individual weights remain unstable.")
                st.markdown("[Comparison protocols and results](https://github.com/eshangark/nba-elo-forecast/blob/main/docs/EVALUATION.md)")
        st.markdown("[Technical paper on GitHub](https://github.com/eshangark/nba-elo-forecast/blob/main/paper/main.pdf)")
        with st.expander("Technical manuscript source"):
            st.download_button("Download LaTeX source", (ROOT / "paper" / "main.tex").read_text(),
                               file_name="nba-elo-forecast.tex", mime="text/plain")


render_dashboard()
