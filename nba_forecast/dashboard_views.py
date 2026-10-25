"""Readable matchup and performance views over saved, versioned outputs."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from .dashboard_data import (elo_ranks, previous_seasons, recent_record, injury_label,
                             probability_steps, data_gaps, issued_rows)
from .evaluation import favorite_bands, compare_variants
from .replay import metrics
from .model import timestamp
from .ui import native_select
from .past_games import past_game_evidence
from .reliability import (forecast_reliability, calibration_context, captured_adjustment,
                          forecast_dependence, team_calibration_evidence, player_impact_evidence)


def matchup_overview(upcoming, archive, result, archives, entries, season, fingerprint, original_archive=None):
    ranks = elo_ranks(result['rankings'])
    history = previous_seasons(archives,entries,season,fingerprint)
    previous = history[0]['ranks'] if history else {}
    completions = {g['game_id']:g['last_play_at'] for g in archive.get('_internal',{}).get('games',[])}
    records = []
    now = datetime.now(timezone.utc).isoformat()
    checks = {r['game_id']: forecast_reliability(r, result['predictions'], completions, archive.get('published_at'), now) for r in upcoming}
    for row in upcoming:
        before = row.get('issued_at',row['start'])
        forms = [recent_record(row[s],result['predictions'],before,completions) for s in ['home','away']]
        records.append({'Tip-off':pd.to_datetime(row['start'],utc=True).tz_convert('America/New_York').strftime('%b %d, %I:%M %p %Z'),
                        'Home':row['home'],'Away':row['away'],'Home win %':row['home_probability']*100,
                        'Away win %':row['away_probability']*100,
                        'Elo rank · H / A':f"#{ranks.get(row['home'],'?')} / #{ranks.get(row['away'],'?')}",
                        'Prior final rank · H / A':f"#{previous.get(row['home'],'?')} / #{previous.get(row['away'],'?')}",
                        'Last 10 · H / A':f"{forms[0]['wins']}–{forms[0]['losses']} / {forms[1]['wins']}–{forms[1]['losses']}", 'Injury data':injury_label(row),
                        'Input status':checks[row['game_id']]['injury']['label'],
                        'Team-strength context':forecast_dependence(row,result['rankings'])['strength_label'],
                        'Season evidence':checks[row['game_id']]['maturity']})
    st.markdown('**Upcoming**')
    table = st.dataframe(pd.DataFrame(records)[['Tip-off','Home','Away','Home win %','Away win %','Input status','Team-strength context','Season evidence','Elo rank · H / A','Prior final rank · H / A','Last 10 · H / A','Injury data']],hide_index=True,width='stretch',on_select='rerun',selection_mode='single-row',
                        key=f'matchup_table_{season}',column_config={
                            'Home win %':st.column_config.NumberColumn(format='%.1f%%',width=75),
                            'Away win %':st.column_config.NumberColumn(format='%.1f%%',width=75),
                            'Tip-off':st.column_config.TextColumn(width=130),
                            'Home':st.column_config.TextColumn(width=150),'Away':st.column_config.TextColumn(width=150),
                            'Elo rank · H / A':st.column_config.TextColumn(width=90),
                            'Prior final rank · H / A':st.column_config.TextColumn(width=90),
                            'Last 10 · H / A':st.column_config.TextColumn(width=100),
                            'Injury data':st.column_config.TextColumn(width=180),
                            'Input status':st.column_config.TextColumn(width=180,help='Observable report and player-data limitations, not a confidence score.'),
                            'Team-strength context':st.column_config.TextColumn(width=160),
                            'Season evidence':st.column_config.TextColumn(width=160)})
    st.caption(('Prior final ranks: '+history[0]['season']+'. ' if history else 'No previous-season archive. ')+'H / A means home / away. Ranks are model Elo ranks, not standings. Recent records use up to ten completed games. Select a row or choose a matchup below for details.')
    ids = [r['game_id'] for r in upcoming]; by_id = {r['game_id']:r for r in upcoming}
    selected_rows = table.selection.rows
    if selected_rows:
        clicked = ids[selected_rows[0]]
        if st.session_state.get(f'last_clicked_matchup_{season}') != clicked:
            st.session_state[f'matchup_details_{season}'] = {'value':clicked}
            st.session_state[f'last_clicked_matchup_{season}'] = clicked
    st.subheader('Matchup details')
    chosen = native_select('Choose matchup',ids,key=f'matchup_details_{season}',
                           format_func=lambda key:f"{by_id[key]['away']} at {by_id[key]['home']} · {pd.to_datetime(by_id[key]['start']).strftime('%b %d')}")
    row = by_id[chosen]
    matchup_details(row,archive,result,archives,season,original_archive or archive,history,completions,checks[row['game_id']],now)


def matchup_details(row,archive,result,archives,season,original_archive,history,completions,check,now):
    ranks=elo_ranks(result['rankings'])
    st.write(f"**{row['home']} {row['home_probability']:.1%} · {row['away']} {row['away_probability']:.1%}**")
    st.caption('Model estimate, not a guaranteed outcome. Team strength, information completeness and probability accuracy are different things.')
    reliability_view(row, check, archive, original_archive, archives, completions, now)
    tabs = st.tabs(['Why this forecast?','Team history & form','Information gaps'])
    with tabs[0]:
        params = archive.get('_internal',{}).get('parameter_registry',{}).get(row.get('parameter_hash'),{}).get('parameters',result['parameters'])
        steps = probability_steps(row,params)
        if steps:
            st.dataframe(pd.DataFrame(steps),hide_index=True,width='stretch',column_config={
                'Home win %':st.column_config.NumberColumn(format='%.1f%%'),
                'Change (pp)':st.column_config.NumberColumn(format='%+.1f')})
            st.caption('These stages reconstruct the stored forecast. Changes are percentage points for the home team; the away probability is the complement. The breakdown depends on this order and is not a causal attribution. The final correction includes fitted recalibration, not only player absences.')
        else:
            st.info('A verified numerical breakdown is unavailable for this stored model version.')
        favored = row['home'] if row['home_probability'] >= .5 else row['away']
        favorite_rank = ranks.get(favored)
        if favorite_rank and favorite_rank > len(ranks)/2:
            st.write(f'{favored} is favored in this matchup despite a model rank of #{favorite_rank}. A team can be weaker league-wide and still be favored against this opponent; matchup context and the probability correction also matter.')
        if 'home_context' in row:
            st.write(f"Rest: {row['home']} {row['home_context']['rest']} intervening days; {row['away']} {row['away_context']['rest']}.")
            st.write(f"Estimated travel: {row['home_context']['travel']:.0f} km home-side, {row['away_context']['travel']:.0f} km away-side. These are venue-city estimates.")
        report_rows=[]
        for side in ['home','away']:
            report=(row.get('injury_report') or {}).get(row.get(side+'_id'))
            if report and report['submitted']:
                for player in report['players']:
                    report_rows.append({'Team':row[side],'Reported player':player.get('name','Name unavailable'),
                                        'Status':player['status'],'Identity match':'Matched' if player.get('athlete') else 'Unmatched'})
        if report_rows:
            st.markdown('**Players in the captured report**')
            st.dataframe(pd.DataFrame(report_rows),hide_index=True,width='stretch')
            st.caption('These are reported participation designations, not a confirmed starting lineup or fixed probabilities of playing.')
        if row.get('injury_source'):
            source = row['injury_source']; when=pd.to_datetime(source['published_at']).tz_convert('America/New_York')
            st.caption(f'Injury report published {when:%b %d, %I:%M %p %Z}. Forecast issued '+str(row.get('issued_at','not recorded'))+'.')
    with tabs[1]:
        data = [{'Season':season,'Team':name,'Model Elo rank':ranks.get(name),'Recent record':recent_record(name,result['predictions'],row.get('issued_at') or row.get('forecast_cutoff') or row['start'],completions)['label']}
                for name in [row['home'],row['away']]]
        for item in history:
            for name in [row['home'],row['away']]:
                data.append({'Season':item['season'],'Team':name,'Model Elo rank':item['ranks'].get(name),'Recent record':'Season-end rank'})
        st.dataframe(pd.DataFrame(data),hide_index=True,width='stretch')
        trajectories=[]
        for name in [row['home'],row['away']]:
            for past in result['predictions']:
                side='home' if past['home']==name else 'away' if past['away']==name else None
                if side and pd.to_datetime(completions.get(past['game_id'],past['start'])) < pd.to_datetime(row.get('issued_at') or row.get('forecast_cutoff') or row['start']):
                    trajectories.append({'Date':pd.to_datetime(past['start']),'Team':name,'Elo':past[side+'_rating_after']})
        if trajectories:
            st.line_chart(pd.DataFrame(trajectories),x='Date',y='Elo',color='Team')
        state=archive.get('_internal',{}).get('feature_state',{})
        rotation_rows=[]
        for side in ['home','away']:
            team=row.get(side+'_id'); rotation=state.get('last_rotation',{}).get(team); previous_minutes=state.get('previous_season_minutes',{}).get(team)
            if rotation and previous_minutes:
                share=sum(m for athlete,m in rotation.items() if athlete in previous_minutes)/sum(rotation.values())
                rotation_rows.append({'Team':row[side],'Returning observed minutes':f'{share:.0%}'})
        if rotation_rows:
            st.dataframe(pd.DataFrame(rotation_rows),hide_index=True)
        st.caption('Returning observed minutes describes the last completed rotation, not the current roster or confirmed lineup. Historical rank alone does not account for trades, development or coaching changes.')
    with tabs[2]:
        for message in data_gaps(row,result['rankings']):
            st.markdown('- '+message)
        st.caption('These are observable limitations, not an invented confidence score. Report submission does not mean every player is matched or every injury effect is known.')


def past_game_details(daily_rows,original_archive,current_result,has_current_replay,archives,entries,season,root,selected_rows=None):
    st.subheader('Past-game details')
    ids=[r['game_id'] for r in daily_rows]
    if not ids:return
    by_id={r['game_id']:r for r in daily_rows};date_key=str(pd.to_datetime(daily_rows[0]['start']).tz_convert('America/New_York').date())
    key=f'past_matchup_{season}_{date_key}'
    if selected_rows:
        clicked=ids[selected_rows[0]]
        if st.session_state.get(key+'_last_click')!=clicked:
            st.session_state[key]={'value':clicked};st.session_state[key+'_last_click']=clicked
    chosen=native_select('Choose past matchup',ids,key=key,
                         format_func=lambda identifier:f"{by_id[identifier]['away']} at {by_id[identifier]['home']}")
    live=original_archive.get('status')=='live'
    options=['current','stored'] if has_current_replay else ['stored']
    basis=native_select('Forecast record',options,key=f'past_basis_{season}',format_func=lambda value:
                        'Current-method replay' if value=='current' else 'Original issued forecast' if live else 'Stored historical replay')
    result=current_result if basis=='current' else original_archive['result']
    stored=next((r for r in result['predictions'] if r['game_id']==chosen),None)
    final=by_id[chosen]
    with st.expander('Final result',expanded=True):
        st.write(f"{final['home']} {final['home_score']} – {final['away_score']} {final['away']}")
        st.caption('The result is shown separately and is excluded from the pregame evidence below.')
    if not stored or stored.get('home_probability') is None or (live and basis=='stored' and stored.get('kind')!='issued_live'):
        st.info('No original pregame forecast was issued for this game. A reconstructed forecast is available only when explicitly selecting Current-method replay.')
        return
    if basis=='current':
        st.info('Current-method training replay: this season helped fit the active model. This reconstructs pregame inputs and is not the original issued forecast or an unseen test.' if result.get('evaluation_role')=='training_replay' else
                'Current-method retrospective replay using the saved pregame cutoff. This is separate from the original issued forecast.')
    elif live:
        st.caption('Original issued forecast · the recorded probability and model version are preserved. Recovered context is labeled separately.')
    else:
        st.caption('Stored historical replay · reconstructed, not issued live. Its fitting/evaluation role is documented in the season archive.')
    recovered=past_game_evidence(stored,original_archive,result,archives,root)
    row=recovered['row'];view=recovered['archive'];cutoff=row.get('issued_at') or row.get('forecast_cutoff')
    for note in recovered['notes']:st.caption(note)
    if not cutoff:
        st.info('The pregame cutoff was not retained, so a historical evidence panel cannot be shown safely.')
        return
    st.caption('Pregame information cutoff: '+pd.to_datetime(cutoff).tz_convert('America/New_York').strftime('%b %d, %Y at %I:%M %p %Z'))
    check=forecast_reliability(row,result['predictions'],recovered['completions'],None,cutoff)
    fingerprint=row.get('forecast_model_sha256')
    history=previous_seasons(archives,entries,season,fingerprint)
    matchup_details(row,view,view['result'],archives,season,original_archive,history,recovered['completions'],check,cutoff)


def reliability_view(row, checks, archive, original_archive, archives, completions, now):
    evidence_cutoff=row.get('issued_at') or row.get('forecast_cutoff')
    st.markdown('**Evidence supporting this forecast**')
    st.caption('Input checks describe what supports this estimate. They are not a probability of being correct, a betting recommendation, or a validated confidence grade.')
    columns = st.columns(3)
    columns[0].markdown('**Input status**\n\n'+checks['injury']['label'])
    strength=forecast_dependence(row,archive['result']['rankings'])
    columns[1].markdown('**Team-strength context**\n\n'+strength['strength_label'])
    columns[2].markdown('**Season evidence**\n\n'+checks['maturity'])
    if strength['rank'] is not None:
        st.write(f"{strength['favorite']} is favored here and ranks #{strength['rank']} of {len(archive['result']['rankings'])}; {strength['opponent']} ranks #{strength['opponent_rank']}. A league rank describes team strength, not certainty of winning this matchup.")
    if strength['base_probability'] is not None:
        st.write(f"{strength['favorite']}: base Elo {strength['base_probability']:.1%} → injury and probability correction {strength['adjustment_pp']:+.1f} points → published {strength['favorite_probability']:.1%}.")
    with st.expander('Inspect forecast reliability', expanded=True):
        evidence_tabs=st.tabs(['Calibration evidence','Player coverage','Forecast inputs'])
        with evidence_tabs[0]:
            st.markdown('**Latest-model history for this probability range**')
            from .accuracy_data import accuracy_catalog
            from .seasons import load_index
            root = Path(archives).parents[1]
            try:
                catalog, notices = accuracy_catalog(root, load_index(archives)[0], original_archive)
                latest = catalog['replay']
                cutoff = min(now, evidence_cutoff or now, key=timestamp)
                band = calibration_context(row, latest, before=cutoff, allow_replay=True)
                _reliability_band('Latest model · reconstructed history', band)
                st.caption('Recalculated with the active model, using results completed before this forecast cutoff. Historical training seasons describe model fit, not unseen-game accuracy. These are reconstructed forecasts, not predictions originally issued at the time.')
                if latest:
                    if row.get('forecast_model_sha256') != latest[0].get('forecast_model_sha256'):
                        st.caption('The inspected forecast used a different model; this latest-model history does not validate its original probability.')
                    team_evidence_view(row, latest, cutoff, 'Team calibration · latest-model historical fit', allow_replay=True)
                else:
                    for note in notices: st.caption(note)
            except (ValueError, KeyError, OSError) as error:
                st.info(f'Latest-model history is unavailable until its integrity checks pass: {error}')
            with st.expander('Earlier-fit benchmark and original issued track record'):
                st.markdown('**Historical calibration for this probability range**')
                audit_path = Path(archives).parents[1]/'models/nba-v0.3/matched-evaluation.json'
                if audit_path.exists():
                    historical_rows=json.loads(audit_path.read_text())['published_rows']
                    historical_completions={}
                    for prior_season in ['2023-24','2024-25','2025-26']:
                        games_path=Path(archives)/prior_season/'games.json'
                        if games_path.exists():
                            historical_completions.update({g['game_id']:g['last_play_at'] for g in json.loads(games_path.read_text())})
                    evidence = [{**r, 'kind':'chronological_backtest','last_play_at':historical_completions.get(r['game_id'])} for r in historical_rows]
                    evidence=[r for r in evidence if r.get('last_play_at') and timestamp(r['last_play_at'])<timestamp(evidence_cutoff or now)]
                    band = calibration_context(row, evidence)
                    _reliability_band('Retrospective chronological benchmark · 2023–24 through 2025–26', band)
                    st.caption('Grouped by favorite probability, not similar rosters, injury coverage or season stage. Earlier-prefix fitted models differ from the current frozen bundle; these outcomes were previously studied. Training replays are excluded.')
                    team_evidence_view(row,evidence,min(now,evidence_cutoff or now,key=timestamp),'Team calibration · historical chronological forecasts')
                else:
                    st.info('Historical calibration benchmark unavailable.')
                evidence = [{**r, 'last_play_at':completions.get(r['game_id'])} for r in issued_rows(original_archive)]
                cutoff = evidence_cutoff
                band = calibration_context(row, evidence, before=min(now, cutoff, key=timestamp), exact_model=True) if cutoff else None
                _reliability_band('Original issued forecasts · same frozen model · completed before this forecast', band)
                if cutoff:
                    team_evidence_view(row,evidence,min(now,cutoff,key=timestamp),'Team calibration · same-model issued forecasts',exact_model=True)
            st.caption('Intervals describe binomial sampling uncertainty, not model uncertainty, and ignore dependence between games. Counts are shown without assigning a confidence score.')
        with evidence_tabs[1]:
            st.markdown('**Injury coverage and unresolved availability**')
            st.dataframe(pd.DataFrame(checks['injury']['teams']), hide_index=True, width='stretch')
            st.caption('Unknown counts mean saved player coverage cannot be verified. Unmatched names and missing histories can overlap. Submitted reports are not confirmed lineups; Probable remains an unresolved designation.')
            impacts=player_impact_evidence(row,archive.get('_internal',{}))
            if impacts:
                st.markdown('**Reported players: minutes and value coverage**')
                st.dataframe(pd.DataFrame(impacts),hide_index=True,width='stretch',column_config={
                    'Expected minutes':st.column_config.NumberColumn(format='%.1f'),
                    'Game Score / minute':st.column_config.NumberColumn(format='%.2f'),
                    'Prior contribution proxy':st.column_config.NumberColumn(format='%.1f')})
                st.caption('Minutes and Game Score are prior-history proxies, not points lost, replacement quality or a causal player-impact estimate. Blank values mean history at this forecast cutoff is unavailable; later player data are never substituted.')
        with evidence_tabs[2]:
            st.markdown('**Captured timestamps**')
            if archive.get('_historical_evidence'):
                st.write(f"Pregame information cutoff: {evidence_cutoff or 'Unavailable'}. Captured injury report age at cutoff: {checks['report_age']}.")
                st.caption('Past-game evidence is evaluated at the pregame cutoff, not at the time this page is opened. A replay cutoff is not proof a forecast was issued live.')
            else:
                st.write(f"{checks['freshness']}. Snapshot published {checks['snapshot_age']}; forecast issued {checks['forecast_age']}; captured injury report published {checks['report_age']}.")
            st.caption('A forecast can retain its original issue time when a later collection finds unchanged inputs. Snapshot freshness uses the two-hour collection interval; it does not confirm that no newer injury news exists.')
            if checks['report_outdated']:
                st.warning('The captured injury report is now more than 16 hours old. The saved probability has not been recomputed by this page.')
            st.markdown('**Current-season evidence at issuance**')
            st.write(' · '.join(f"{team}: {count if count is not None else 'unknown'} prior completed games" for team, count in checks['counts'].items()))
            st.caption('Fewer than ten prior games is an early-season flag, matching the existing evaluation warmup; it is not a validated reliability threshold. Ratings retain prior-season carryover.')
            st.markdown('**Injury sensitivity**')
            adjustment = captured_adjustment(row)
            if adjustment is not None:
                st.write(f"Captured injury inputs + fitted recalibration changed the home team's probability ({row['home']}) by {adjustment:+.1f} percentage points versus base Elo.")
            else:
                st.write('The captured injury/recalibration adjustment is unavailable.')
            st.caption('Player-availability scenario sensitivity is unavailable. The captured adjustment is not an uncertainty range or a player-in/player-out forecast; no scenarios are generated here.')


def team_evidence_view(row,evidence,before,label,exact_model=False,allow_replay=False):
    st.markdown('**'+label+'**')
    records=[];details=[]
    for team in [row['home'],row['away']]:
        item=team_calibration_evidence(row,evidence,team,before,exact_model=exact_model,allow_replay=allow_replay)
        records.append({'Team':team,'Probability range':item['band'],'Games':item['games'],'Wins':item['wins'],
                        'Mean forecast':item['mean_forecast'],'Actual win rate':item['observed_win_rate'],'Winner accuracy':item['winner_accuracy'],
                        'Observed-rate 95% interval':item['observed_rate_interval_95'],
                        'Evidence':item['sample_label'] if item['games']<30 else 'Historical sample'})
        details.append({'Team':team,'Actual − predicted (pp)':item['raw_error_pp'],
                        'Pooled historical error (pp)':item['pooled_error_pp'],
                        'League-reference appearances':item['reference_appearances']})
    st.dataframe(pd.DataFrame(records),hide_index=True,width='stretch',column_config={
        'Team':st.column_config.TextColumn(width=190),
        'Winner accuracy':st.column_config.NumberColumn(format='percent'),
        'Mean forecast':st.column_config.NumberColumn(format='percent'),
        'Actual win rate':st.column_config.NumberColumn(format='percent')})
    st.caption('Each team uses its own ten-point probability range. The Wilson interval describes uncertainty in its historical win rate, not this game’s chance. It ignores dependence and model uncertainty; roster changes also limit relevance. Fewer than 30 games is marked a small sample.')
    with st.expander('Historical error and pooling details'):
        st.dataframe(pd.DataFrame(details),hide_index=True,width='stretch',column_config={
            'Team':st.column_config.TextColumn(width=190),
            'Actual − predicted (pp)':st.column_config.NumberColumn(format='%+.1f'),
            'Pooled historical error (pp)':st.column_config.NumberColumn(format='%+.1f')})
        st.caption('Negative historical error means this team won less often than forecast. Pooling blends its residual with 80 league-reference team appearances in that range. This is descriptive, not a new forecast or confidence score. Both sides of a game can enter league evidence. The pooling strength and small-sample label are display conventions, not validated reliability thresholds.')


def _reliability_band(label, band):
    st.write(label)
    if band is None:
        st.caption('No completed forecasts in this probability range. Reliability has not been established for this group.')
        return
    st.write(f"Favorites forecast at {band['band']}: {band['wins']} won out of {band['games']}. "
             f"Mean forecast {band['mean_forecast']:.1%}; observed win rate {band['observed_win_rate']:.1%}. "
             f"95% sampling interval {band['lower_95']:.1%}–{band['upper_95']:.1%}.")


def scorecard(rows, empty):
    m=metrics(rows)
    if not m['games']:
        st.info(empty);return
    columns=st.columns(4)
    columns[0].metric('Games scored',m['games'])
    columns[1].metric('Winner accuracy',f"{m['winner_accuracy']:.1%}")
    columns[2].metric('Log loss',f"{m['log_loss']:.3f}")
    columns[3].metric('Brier score',f"{m['brier_score']:.3f}")
    st.caption('Winner accuracy counts the higher-probability team winning; exactly 50% picks home. Lower log loss and Brier score are better probability scores.')


def calibration_view(rows):
    bands=favorite_bands(rows)
    st.markdown('**How often do favorites in each probability range win?**')
    if not bands:
        st.info('No eligible completed forecasts yet.');return
    frame=pd.DataFrame(bands).rename(columns={'band':'Favorite forecast','games':'Games','wins':'Wins',
         'mean_forecast':'Mean predicted win %','observed_win_rate':'Actual win %','lower_95':'Lower 95%','upper_95':'Upper 95%'})
    st.dataframe(frame,hide_index=True,width='stretch',column_config={k:st.column_config.NumberColumn(format='percent')
                  for k in ['Mean predicted win %','Actual win %','Lower 95%','Upper 95%']})
    st.caption('Bins are five percentage points wide: 60–65% means at least 60% and below 65%. Always read the game count. Wilson 95% intervals describe binomial sampling uncertainty only; games can be dependent and model/fitting uncertainty is not included.')


def performance_view(root, original_archive, result, season):
    st.subheader('Model performance')
    replayed,historical,issued=st.tabs(['Current-method replay','Historical chronological backtests','Original forecasts this season'])
    with historical:
        st.write('**Earlier-season fits, evaluated on 2023–24 through 2025–26 · 3,690 shared games, including openers.**')
        st.caption('Retrospective chronological evaluation. These outcomes were previously studied, so this is not newly untouched evidence. This is the historical benchmark, not the selected season’s live score.')
        audit_path=Path(root)/'models/nba-v0.3/matched-evaluation.json'
        if audit_path.exists():
            audit=json.loads(audit_path.read_text()); rows=audit['published_rows']
            scorecard(rows,'Historical benchmark unavailable.')
            calibration_view(rows)
            with st.expander('Compare model changes on the exact same games'):
                comparison=audit['pooled']; names={'base':'Carryover Elo','injury':'Elo + injuries','boosted':'Boosted research comparator'}
                table=[]
                for name,m in comparison['metrics'].items():
                    delta=comparison['difference_from_baseline'][name]
                    table.append({'Model':names[name],'Games':m['games'],'Accuracy':m['winner_accuracy'],
                                  'Log loss':m['log_loss'],'Brier':m['brier_score'],'Accuracy change (pp)':delta['winner_accuracy']*100})
                st.dataframe(pd.DataFrame(table),hide_index=True,column_config={'Accuracy':st.column_config.NumberColumn(format='percent')})
                st.caption('Shared sample SHA256: '+comparison['sample_sha256']+'. Different game lists, outcomes, cutoffs or warmup eligibility cause evaluation to fail. Research comparisons do not change the dashboard’s single forecast.')
                st.download_button('Download matched-sample audit',json.dumps(audit,indent=2),file_name='matched-evaluation.json',mime='application/json')
        else:
            st.info('The matched historical audit is being prepared.')
    with issued:
        rows=issued_rows(original_archive)
        st.write(f'**{season} · probabilities actually issued before tip-off**')
        st.caption('These retain the methods and information originally used. Replaying a newer method does not rewrite this track record. Different model versions may appear during this season.')
        scorecard(rows,'No original issued forecasts have completed for this selected season.')
        calibration_view(rows)
        if original_archive.get('_internal',{}).get('forecasts'):
            st.download_button('Download original issued forecast history',json.dumps(original_archive['_internal']['forecasts'],indent=2),
                               file_name=f'{season}-original-issued-forecasts.json',mime='application/json')
    with replayed:
        st.write(f'**{season} · reconstructed with the current methodology**')
        role=result.get('evaluation_role')
        st.info('Training replay: this season helped fit the active model. These scores measure historical fit, not unseen-game accuracy.' if role=='training_replay' else
                'Retrospective reconstruction, not the original issued track record or a newly held-out test.')
        window=native_select('Replay evaluation window',['all','established'],key=f'evaluation_window_{season}',
                             format_func=lambda x:'All games, including openers' if x=='all' else 'After ten prior games per team')
        rows=[r for r in result['predictions'] if r.get('home_probability') is not None and (window=='all' or r['eligible_for_evaluation'])]
        scorecard(rows,'No replay games qualify for this window.')
        calibration_view(rows)
        st.caption('Latest-model reconstructed scores and band rates are separate from the earlier-fit benchmark and original live scores. Training-season calibration describes historical fit, not unseen-game accuracy.')
