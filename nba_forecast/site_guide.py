"""Visitor-facing overview; no forecasting or data processing."""
import streamlit as st


def home_view():
    st.subheader('Understand the forecast before you decide')
    st.write('NBA Elo Forecast brings together team strength, pregame win probabilities and the evidence behind them. Explore upcoming matchups, revisit past predictions and check how forecasts have performed across teams, seasons and probability ranges. Use the tabs above to move between views; the Season selector applies throughout the dashboard.')
    st.markdown('**A useful starting point**')
    st.write('Open Matchup and search for an upcoming game. Read the predicted chances alongside team strength, season evidence and player coverage. Then compare the mean forecast with actual historical win rates in Calibration evidence, checking the sample size and interval. Use Accuracy when you want to explore that record in more detail. A higher win probability alone does not establish that a bet is worth its price.')
    st.markdown('**Explore the dashboard**')
    sections = [
        ('Matchup · Focus on one game', 'Search upcoming games and review their saved probabilities, team-strength context, calibration evidence, injury coverage and forecast explanation in one place.'),
        ('Accuracy · Check the track record', 'Look up a team and season, compare expected with actual wins, and explore probability bands, calibration gaps, sampling intervals, winner accuracy, Brier score and log loss.'),
        ('Teams · Compare league strength', 'Browse Elo rankings, current-season records and team rating histories. Elo describes relative team strength; a lower-ranked team can still be favored in a particular matchup.'),
        ('Games · Browse the schedule and results', 'Review upcoming forecasts or choose a past date and matchup. Inspect the original issued forecast where available, or a clearly labeled current-method replay, with the final score kept separate from pregame evidence.'),
        ('Methodology · Understand the model', 'Read how Elo, home court, rest, travel, season carryover and injury inputs produce a forecast. Review evaluation results, fitted constants, the technical paper and downloadable season datasets.'),
        ('Data and updates · Know what you are reading', 'The collector is scheduled every two hours, and open pages reread saved snapshots each minute. Check the displayed update status. Player-data gaps remain explicit. When no usable injury report is available, forecasts fall back to base Elo.'),
    ]
    for index in range(0, len(sections), 2):
        columns = st.columns(2)
        for column, (title, explanation) in zip(columns, sections[index:index+2]):
            with column.container(border=True):
                st.markdown('**'+title+'**')
                st.write(explanation)
    with st.expander('How to interpret the evidence'):
        st.write('Win probability is a pregame estimate, not a guarantee. Calibration asks whether similar forecasts matched observed win rates; its sampling interval describes a historical group, not this game’s true probability. Team evidence can be sparse and older rosters may differ from today’s. Keep original issued forecasts, earlier-season-fitted chronological backtests and current-method replays separate: training replays measure historical fit, not unseen-game accuracy.')
    with st.container(border=True):
        st.markdown('**Video walkthrough · Planned**')
        st.caption('A future narrated demo will walk through selecting a matchup, interpreting forecast reliability and checking the Accuracy explorer. No video is available yet.')
