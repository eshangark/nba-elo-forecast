"""Readable matchup and performance views over saved, versioned outputs."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from .dashboard_data import (elo_ranks, previous_seasons, recent_record, injury_label,
                             probability_steps, data_gaps, issued_rows)
from .evaluation import favorite_bands, compare_variants
from .replay import metrics
from .ui import native_select


def matchup_overview(upcoming, archive, result, archives, entries, season, fingerprint):
    ranks = elo_ranks(result['rankings'])
    history = previous_seasons(archives,entries,season,fingerprint)
    previous = history[0]['ranks'] if history else {}
    completions = {g['game_id']:g['last_play_at'] for g in archive.get('_internal',{}).get('games',[])}
    records = []
    for row in upcoming:
        before = row.get('issued_at',row['start'])
        forms = [recent_record(row[s],result['predictions'],before,completions) for s in ['home','away']]
        records.append({'Tip-off':pd.to_datetime(row['start'],utc=True).tz_convert('America/New_York').strftime('%b %d, %I:%M %p %Z'),
                        'Home':row['home'],'Away':row['away'],'Home win %':row['home_probability']*100,
                        'Away win %':row['away_probability']*100,
                        'Elo rank · H / A':f"#{ranks.get(row['home'],'?')} / #{ranks.get(row['away'],'?')}",
                        'Prior final rank · H / A':f"#{previous.get(row['home'],'?')} / #{previous.get(row['away'],'?')}",
                        'Last 10 · H / A':f"{forms[0]['wins']}–{forms[0]['losses']} / {forms[1]['wins']}–{forms[1]['losses']}", 'Injury data':injury_label(row)})
    st.markdown('**Upcoming**')
    table = st.dataframe(pd.DataFrame(records),hide_index=True,width='stretch',on_select='rerun',selection_mode='single-row',
                        key=f'matchup_table_{season}',column_config={
                            'Home win %':st.column_config.NumberColumn(format='%.1f%%',width=75),
                            'Away win %':st.column_config.NumberColumn(format='%.1f%%',width=75),
                            'Tip-off':st.column_config.TextColumn(width=130),
                            'Home':st.column_config.TextColumn(width=150),'Away':st.column_config.TextColumn(width=150),
                            'Elo rank · H / A':st.column_config.TextColumn(width=90),
                            'Prior final rank · H / A':st.column_config.TextColumn(width=90),
                            'Last 10 · H / A':st.column_config.TextColumn(width=100),
                            'Injury data':st.column_config.TextColumn(width=180)})
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
    st.write(f"**{row['home']} {row['home_probability']:.1%} · {row['away']} {row['away_probability']:.1%}**")
    st.caption('Model estimate, not a guaranteed outcome. Team strength, information completeness and probability accuracy are different things.')
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
        data = [{'Season':season,'Team':name,'Model Elo rank':ranks.get(name),'Recent record':recent_record(name,result['predictions'],row.get('issued_at',row['start']),completions)['label']}
                for name in [row['home'],row['away']]]
        for item in history:
            for name in [row['home'],row['away']]:
                data.append({'Season':item['season'],'Team':name,'Model Elo rank':item['ranks'].get(name),'Recent record':'Season-end rank'})
        st.dataframe(pd.DataFrame(data),hide_index=True,width='stretch')
        trajectories=[]
        for name in [row['home'],row['away']]:
            for past in result['predictions']:
                side='home' if past['home']==name else 'away' if past['away']==name else None
                if side and pd.to_datetime(past['start']) < pd.to_datetime(row.get('issued_at',row['start'])):
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
    historical,issued,replayed=st.tabs(['Historical chronological backtests','Original forecasts this season','Current-method replay'])
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
        st.caption('Replay scores are separate from the historical chronological benchmark and original live scores. Calibration evidence is shown in those two tabs, excluding training replays.')
