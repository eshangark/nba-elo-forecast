"""Streamlit season browser over versioned forecast snapshots."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from nba_forecast.seasons import load_index, load_season

ROOT = Path(__file__).resolve().parent
ARCHIVES = ROOT / "data" / "seasons"

st.set_page_config(page_title="NBA Elo Forecast", page_icon="🏀", layout="wide")
st.title("NBA Elo Forecast")
st.caption("Team strength, matchup probabilities, and the record behind each forecast.")

today = datetime.now(ZoneInfo("America/New_York")).date()
entries, current = load_index(ARCHIVES, today)
lookup = {e["season"]: e for e in entries}
selected = st.selectbox("Season", list(lookup), index=list(lookup).index(current),
                        format_func=lambda s: s + (" · Current" if s == current else " · Archive"),
                        key="selected_season")
archive = load_season(ARCHIVES, lookup[selected])
teams_tab, games_tab, method_tab = st.tabs(["Teams", "Games", "Methodology"])

if archive is None:
    with teams_tab:
        st.info("This season's ratings are being prepared. Select an archived season to explore available history.")
    with games_tab:
        st.info("No forecasts have been published for this season yet.")
    result = None
elif archive["status"] == "prepared":
    with teams_tab:
        st.info("Season setup: all teams start at 1500. Calibrated ratings and forecasts will appear when the model is ready.")
        st.dataframe(pd.DataFrame(archive["teams"])[["team", "elo"]].rename(columns={"team": "Team", "elo": "Initial Elo"}),
                     hide_index=True, width="stretch")
    with games_tab:
        st.info("No forecasts have been published for this season yet.")
    result = None
else:
    result = archive["result"]
    st.caption(f"Historical model replay · {archive['coverage']['start']} to {archive['coverage']['end']} · Partial season")
    with teams_tab:
        st.subheader("Team ratings")
        rankings = pd.DataFrame(result["rankings"])
        shown = rankings[["team", "elo", "games", "wins"]].copy()
        shown["Record"] = shown["wins"].astype(str) + "–" + (shown["games"] - shown["wins"]).astype(str)
        shown = shown[["team", "elo", "Record", "games"]].rename(columns={"team": "Team", "elo": "Elo", "games": "Games"})
        st.dataframe(shown, hide_index=True, width="stretch", column_config={"Elo": st.column_config.NumberColumn(format="%.1f")})
        team = st.selectbox("Team history", sorted(rankings["team"].tolist()), key="team_history")
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
            future["Home win %"] = future["home_probability"] * 100
            future["Away win %"] = future["away_probability"] * 100
            st.markdown("**Upcoming**")
            st.dataframe(future[["start", "home", "away", "Home win %", "Away win %"]].rename(
                columns={"start": "Tip-off", "home": "Home", "away": "Away"}), hide_index=True,
                column_config={"Home win %": st.column_config.NumberColumn(format="%.1f%%"),
                               "Away win %": st.column_config.NumberColumn(format="%.1f%%")})
        st.markdown("**Past games**")
        frame = pd.DataFrame(result["predictions"])
        frame["Date"] = pd.to_datetime(frame["start"], utc=True).dt.tz_convert("America/New_York").dt.date
        dates = sorted(frame["Date"].unique(), reverse=True)
        picked_date = st.selectbox("Game date", dates, key=f"game_date_{selected}")
        daily = frame[frame["Date"] == picked_date].copy()
        daily["Home win %"] = daily["home_probability"] * 100
        daily["Away win %"] = daily["away_probability"] * 100
        daily["Final score"] = daily["home_score"].astype(str) + "–" + daily["away_score"].astype(str)
        daily["Winner"] = daily.apply(lambda g: g["home"] if g["home_win"] else g["away"], axis=1)
        st.dataframe(daily[["home", "away", "Home win %", "Away win %", "Final score", "Winner"]].rename(
            columns={"home": "Home", "away": "Away"}), hide_index=True, width="stretch",
            column_config={"Home win %": st.column_config.NumberColumn(format="%.1f%%"),
                           "Away win %": st.column_config.NumberColumn(format="%.1f%%")})
        st.caption("These probabilities were reconstructed from historical data. They were not issued live before those games.")
    with method_tab:
        st.warning("Development model: constants have not been fitted to NBA history. This short sample verifies the pipeline; it is not a final accuracy estimate.")
        m = result["metrics"]
        if m["games"]:
            cols = st.columns(3)
            cols[0].metric("Evaluation games", m["games"])
            cols[1].metric("Brier score", f"{m['brier_score']:.3f}")
            cols[2].metric("Log loss", f"{m['log_loss']:.3f}")
        st.caption(f"Evaluation from {result['evaluation_from']}; earlier games initialize ratings. Model {result['model_version']}.")
        calibration = pd.DataFrame(m["calibration"])
        if not calibration.empty:
            st.dataframe(calibration.rename(columns={"games": "Games", "mean_probability": "Mean forecast",
                                                     "observed_home_win_rate": "Observed home win rate"}), hide_index=True)

with method_tab:
    st.subheader("How the model works")
    st.write("Pregame probabilities combine the teams' Elo difference with home court, rest, estimated travel, and time-zone changes. After completed games, ratings update using the result, schedule strength, lead retention, and box-score performance.")
    st.write("Each season has its own stored history. Model versions and data coverage are preserved so archived results remain interpretable.")
    st.markdown("[Technical manuscript on GitHub](https://github.com/eshangark/nba-elo-forecast/blob/main/paper/main.tex)")
    with st.expander("Technical manuscript source"):
        st.download_button("Download LaTeX source", (ROOT / "paper" / "main.tex").read_text(),
                           file_name="nba-elo-forecast.tex", mime="text/plain")
