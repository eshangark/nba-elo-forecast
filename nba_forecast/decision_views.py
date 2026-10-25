"""Focused Matchup and Accuracy tabs; existing dashboard tabs remain intact."""
import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from .accuracy_data import (SOURCES, accuracy_catalog, evidence_before, favorite_calibration, season_scores,
                            team_bands, team_scores)
from .dashboard_data import previous_seasons
from .dashboard_views import matchup_details
from .reliability import forecast_reliability
from .replay import metrics


def matchup_lookup(archive, original_archive, archives, entries, season):
    st.subheader('Matchup lookup')
    st.write('Use Matchup for a focused review of one upcoming game. Search for a matchup, then read its win probabilities alongside team strength, season evidence and forecast reliability. Calibration evidence shows how similar forecasts performed; Player coverage exposes missing histories and unresolved availability, and Why this forecast? explains the probability breakdown. This view uses the same saved forecasts and calculations as Games. Select the current season for upcoming games.')
    upcoming = (archive or {}).get('upcoming', [])
    if not upcoming:
        st.info('No upcoming forecasts are stored for this season. Select the current season to look up an upcoming matchup.')
        return
    by_id = {r['game_id']: r for r in upcoming}
    chosen = st.selectbox('Find an upcoming game', list(by_id), key=f'focused_matchup_{season}',
                          format_func=lambda key: f"{by_id[key]['away']} at {by_id[key]['home']} · "
                          + pd.to_datetime(by_id[key]['start']).tz_convert('America/New_York').strftime('%b %d, %I:%M %p %Z'))
    row = by_id[chosen]; result = archive['result']
    now = datetime.now(timezone.utc).isoformat()
    completions = {g['game_id']: g['last_play_at'] for g in archive.get('_internal', {}).get('games', [])}
    checks = forecast_reliability(row, result['predictions'], completions, archive.get('published_at'), now)
    fingerprint = result.get('forecast_model_sha256', archive.get('_internal', {}).get('forecast_model_sha256'))
    history = previous_seasons(archives, entries, season, fingerprint)
    st.caption(f"Saved forecast ID: {row['game_id']} · issued {row.get('issued_at', 'time unavailable')} · model {row.get('model_version', 'version unavailable')}.")
    matchup_details(row, archive, result, archives, season, original_archive, history, completions, checks, now)


def _table(records, *, percentages=()):
    if not records:
        st.info('No qualifying records for this selection.')
        return
    config = {name: st.column_config.NumberColumn(format='percent') for name in percentages}
    config.update({name: st.column_config.NumberColumn(format='%+.2f')
                   for name in ['Calibration gap (pp)', 'Wins − expected']})
    config['Expected wins'] = st.column_config.NumberColumn(format='%.2f')
    st.dataframe(pd.DataFrame(records), hide_index=True, width='stretch', column_config=config)


def accuracy_lookup(root, entries, original_archive, selected):
    st.subheader('Accuracy explorer')
    st.write('Use Accuracy to explore the model’s track record by evidence source, season and team. Start with the selectors, then use Season overview, Team overview or Probability ranges for the comparison you need. Winner accuracy measures how often the favored team won; calibration compares mean forecast with actual win rate across games, and a small calibration gap is not an accuracy percentage. Select an upcoming matchup under Accuracy evidence cutoff to restrict evidence to what was available before that forecast. Keep original issued forecasts, chronological backtests and replays separate, and read sample sizes and intervals alongside the rates.')
    try:
        catalog, notices = accuracy_catalog(root, entries, original_archive)
    except (ValueError, KeyError, OSError) as error:
        st.error(f'Accuracy data integrity check failed: {error}. Scores are withheld rather than combining inconsistent records.')
        return
    source_column, cutoff_column = st.columns(2)
    source = source_column.selectbox('Accuracy evidence source', list(SOURCES), format_func=SOURCES.get, key='accuracy_source')
    source_rows = catalog[source]
    upcoming = {r['game_id']: r for r in (original_archive or {}).get('upcoming', [])}
    reference = cutoff_column.selectbox('Accuracy evidence cutoff', ['All completed games']+list(upcoming),
                             key=f'accuracy_cutoff_{selected}',
                             format_func=lambda key: key if key == 'All completed games' else
                             f"Before {upcoming[key]['away']} at {upcoming[key]['home']} · {upcoming[key].get('issued_at', upcoming[key]['start'])}")
    if reference != 'All completed games':
        source_rows = evidence_before(source_rows, upcoming[reference], source)
        st.caption('Restricted to results completed before this matchup’s saved cutoff. Issued evidence also requires its exact model fingerprint, matching Games. Select All available seasons to reproduce the full Games historical benchmark.')
    if source == 'chronological':
        st.caption('Retrospective chronological backtests: each season used earlier-season fits. Outcomes have already been studied; this is not fresh prospective evidence.')
    elif source == 'issued':
        st.caption('Original probabilities actually issued before tip-off. One scored forecast per completed game; different model versions may appear. Historical replays and unissued games are excluded.')
    else:
        st.warning('Current-method reconstruction, not the original issued track record. Training seasons measure historical fit. Replay calibration is excluded from reliability evidence.')
    if not source_rows:
        st.info('No evaluated forecasts are available for this evidence source.')
        for note in notices:
            st.caption(note)
        return
    seasons = sorted({r['season'] for r in source_rows}, reverse=True)
    choices = ['All available seasons']+seasons
    season_column, team_column = st.columns(2)
    scope = season_column.selectbox('Accuracy season', choices, index=choices.index(selected) if selected in choices else 0,
                         key=f'accuracy_season_{source}')
    rows = [r for r in source_rows if scope == choices[0] or r['season'] == scope]
    teams = sorted({r[s] for r in rows for s in ['home', 'away']})
    team = team_column.selectbox('Accuracy team lookup', ['All teams']+teams, key=f'accuracy_team_{source}_{scope}')
    filtered = rows if team == 'All teams' else [r for r in rows if team in [r['home'], r['away']]]
    scored = metrics(filtered)
    cols = st.columns(4)
    cols[0].metric('Evaluated games', scored['games'])
    cols[1].metric('Winner accuracy', f"{scored['winner_accuracy']:.1%}")
    cols[2].metric('Brier score', f"{scored['brier_score']:.3f}")
    cols[3].metric('Log loss', f"{scored['log_loss']:.3f}")
    st.caption('Each game is counted once in these scores. Winner accuracy picks home at exactly 50%, consistently with Games. Lower Brier score and log loss are better. Selecting a team restricts scores to its games.')
    if source == 'replay':
        roles = sorted({f"{r['season']}: {r.get('evaluation_role') or 'retrospective reconstruction'}" for r in rows})
        st.caption('Evaluation roles · '+' · '.join(roles))
    if source == 'issued':
        versions = sorted({str(r.get('model_version') or 'unrecorded') for r in filtered})
        st.caption('Issued model versions in this selection: '+', '.join(versions)+'.')
    season_tab, team_tab, calibration_tab = st.tabs(['Season overview', 'Team overview', 'Probability ranges'])
    with season_tab:
        _table(season_scores(filtered), percentages=['Winner accuracy'])
        st.caption('Season metrics use the same game probabilities and outcomes as the existing Methodology performance view when source and season match. League-wide team win rates are not averaged: counting both sides would force them to 50%.')
    with team_tab:
        records = team_scores(filtered)
        if team != 'All teams':
            records = [r for r in records if r['Team'] == team]
        if source == 'replay':
            records = [{k: r[k] for k in ['Team', 'Games', 'Winner accuracy', 'Brier score', 'Log loss']} for r in records]
        _table(records, percentages=['Winner accuracy', 'Mean forecast', 'Actual win rate'])
        st.caption('Team summaries use that team’s own probabilities and outcomes. Expected wins are the sum of its forecasts. Calibration gap is actual minus predicted in percentage points; positive means more wins than forecast. Winner accuracy still evaluates the game’s favored pick, including when this team was the underdog. Each game appears for two teams; do not sum team game counts as distinct games.')
        if team != 'All teams':
            st.markdown('**This team across seasons in the selected evidence source**')
            trend = []
            for season in seasons:
                summary = next((r for r in team_scores([r for r in source_rows if r['season'] == season]) if r['Team'] == team), None)
                if summary:
                    if source == 'replay':
                        summary = {k: summary[k] for k in ['Team', 'Games', 'Winner accuracy', 'Brier score', 'Log loss']}
                    trend.append({'Season': season, **summary})
            _table(trend, percentages=['Winner accuracy', 'Mean forecast', 'Actual win rate'])
    with calibration_tab:
        if source == 'replay':
            st.info('Calibration reliability tables exclude current-method replays, including seasons used for fitting. Select chronological backtests or original issued forecasts for calibration evidence.')
        elif team == 'All teams':
            st.markdown('**League calibration by favorite probability**')
            _table(favorite_calibration(rows), percentages=['Mean forecast', 'Actual win rate', 'Lower 95%', 'Upper 95%'])
            st.caption('Five-point bands use one favorite per game; these are the same bands used in Games. Select a team above for its own ten-point probability bands.')
        else:
            st.markdown(f'**{team}: calibration by its own probability range**')
            _table(team_bands(rows, team), percentages=['Mean forecast', 'Actual win rate'])
            st.caption('Ten-point bands include their lower boundary and exclude their upper boundary; the final band includes 100%. Empty bands remain visible. These use the same binning, Wilson intervals and small-sample labels as Games. Match a Games panel’s seasons, pregame cutoff and model fingerprint before comparing counts; this explorer otherwise includes all completed games in its selected scope.')
        st.caption('Intervals describe uncertainty in historical group win rates, not a range for an individual game’s probability. Small samples, changing rosters, game dependence and model uncertainty limit interpretation. A close season average can hide errors that cancel across probability bands.')
    with st.expander('Scored records and source coverage'):
        for note in notices:
            st.caption(note)
        st.caption(f"Source: {SOURCES[source]} · season scope: {scope} · team: {team}. Original issued rows use recorded issue cutoffs; chronological and replay rows retain their own pregame cutoffs. Source records are checked against stored game identities and results before scoring.")
        st.download_button('Download accuracy records', json.dumps(filtered, indent=2),
                           file_name=f'accuracy-{source}.json', mime='application/json', key='accuracy_records_download')
