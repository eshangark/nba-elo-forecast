"""Read-only recovery of pregame evidence for stored past-game forecasts."""
import copy
import gzip
import json
from itertools import groupby
from pathlib import Path

from .forecasting import FeatureState, carryover_ratings, log_odds
from .live import rebuild, digest
from .model import Engine, Parameters, slate_date, timestamp


def _load_inputs(directory):
    path=directory/'replay-inputs.json.gz'
    return json.loads(gzip.decompress(path.read_bytes())) if path.exists() else {'players':{},'contexts':{}}


def _engine(params,ratings):
    engine=Engine(Parameters(**params))
    for team,rating in ratings.items():engine.team(team).rating=rating
    return engine


def _daily_updates(engine,state,games,players,cutoff=None):
    """Never use a result/player appearance that completes at/after cutoff."""
    games=sorted(games,key=lambda g:(timestamp(g['start']),g['game_id']))
    for _,part in groupby(games,slate_date):
        batch=list(part)
        if cutoff is not None:
            batch=[g for g in batch if timestamp(g['last_play_at'])<cutoff]
        if not batch:continue
        predictions=[engine.predict(g) for g in batch]
        for game,prediction in zip(batch,predictions):
            engine.update(game,prediction)
            state.observe(game,prediction['home_probability'],players.get(game['game_id']))
        engine.recenter()


def _current_historical_seed(archives,season,params,roster):
    previous={};state=FeatureState()
    for directory in sorted(Path(archives).iterdir()):
        if not directory.is_dir() or directory.name>=season or not (directory/'games.json').exists():continue
        games=json.loads((directory/'games.json').read_text());inputs=_load_inputs(directory)
        universe={g[s]['id']:g[s]['name'] for g in games for s in ['home','away']}
        ratings=carryover_ratings(previous,universe,.5);engine=_engine(params,ratings)
        state.start_season(directory.name)
        _daily_updates(engine,state,games,inputs['players'])
        previous={team:t.rating for team,t in engine.teams.items()}
    state.start_season(season)
    return carryover_ratings(previous,roster,.5),state


def past_game_evidence(row,source_archive,view_result,archives,root):
    """Enrich a COPY; retain the exact selected forecast, never issue/rewrite one.

    Ratings and player histories can be reconstructed from pre-cutoff records.
    If rating parity fails, leave ranks/player history unknown rather than use
    today's state. Published probabilities are never recomputed here.
    """
    row=copy.deepcopy(row);archive=copy.deepcopy(source_archive)
    archive['result']=copy.deepcopy(view_result);archive['_historical_evidence']=True
    internal=source_archive.get('_internal',{});season=source_archive['season']
    cutoff_text=row.get('issued_at') or row.get('forecast_cutoff')
    notes=[]
    directory=Path(archives)/season
    games=internal.get('games')
    if games is None:
        path=directory/'games.json';games=json.loads(path.read_text()) if path.exists() else []
    completions={g['game_id']:g['last_play_at'] for g in games}
    game=next((g for g in games if g['game_id']==row['game_id']),None)
    params=internal.get('parameter_registry',{}).get(row.get('parameter_hash'),{}).get('parameters',view_result.get('parameters'))
    # Erase current-state context first. It must never be substituted for the past.
    archive['result']['rankings']=[]
    archive['_internal']={'parameter_registry':copy.deepcopy(internal.get('parameter_registry',{})),'games':copy.deepcopy(games)}
    if not cutoff_text or timestamp(cutoff_text)>=timestamp(row['start']) or game is None or not params:
        notes.append('Pregame state cannot be recovered: a valid cutoff, game source or model parameters are missing.')
        return {'row':row,'archive':archive,'completions':completions,'notes':notes,'verified':False}
    cutoff=timestamp(cutoff_text)
    roster={g[s]['id']:g[s]['name'] for g in games for s in ['home','away']}
    row.update(home_id=game['home']['id'],away_id=game['away']['id'])
    inputs=_load_inputs(directory) if not internal else {'contexts':{},'players':internal.get('player_games',{})}
    context={}
    if row.get('kind')=='issued_live':
        context={'cutoff':cutoff_text,'report':row.get('injury_report'),'source':row.get('injury_source')}
    elif internal:
        candidates=[f for f in internal.get('forecasts',[]) if f['game_id']==row['game_id']
                    and f.get('issued_at') and timestamp(f['issued_at'])==cutoff]
        if candidates:
            captured=candidates[-1];context={'cutoff':cutoff_text,'report':captured.get('injury_report'),'source':captured.get('injury_source')}
    else:
        candidate=inputs['contexts'].get(row['game_id'],{})
        if candidate.get('cutoff') and timestamp(candidate['cutoff'])==cutoff:context=candidate
    source=context.get('source');report=context.get('report')
    if row.get('model_version')=='0.2.0' and 'base_home_probability' not in row:
        report=None
        notes.append('This older model did not retain injury-correction inputs; later injury data are not substituted.')
    usable_context=bool(source and timestamp(source['published_at'])<=cutoff
                        and (cutoff-timestamp(source['published_at'])).total_seconds()<=16*3600)
    if report is not None and usable_context:
        row['injury_report']=copy.deepcopy(report)
    elif report is not None:
        row.pop('injury_report',None);row.pop('forecast_features',None)
        row['injury_status']='unverified_report'
        notes.append('Captured injury-report timing is unverified; it is excluded from recovered coverage.')
    if not internal and row.get('kind')=='current_method_replay':
        ratings,state=_current_historical_seed(archives,season,params,roster)
    elif internal:
        initial=internal.get('initialization',{})
        ratings=initial.get('ratings',{team:1500. for team in roster})
        state=FeatureState(initial.get('feature_seed'))
    else:
        ratings=view_result.get('initial_ratings',{team:1500. for team in roster});state=FeatureState()
        fold_path=Path(root)/f'models/nba-v0.3/folds/{int(season[:4])+1}.json'
        if view_result.get('model_version')=='0.3.0' and fold_path.exists():
            bundle=json.loads(fold_path.read_text());state=FeatureState(bundle['initialization']['features'])
    try:
        if internal:
            prior=[g for g in games if timestamp(g['last_play_at'])<cutoff]
            engine,_=rebuild(prior,Parameters(**params),roster,cutoff,initial_ratings=ratings,
                             feature_seed=state.data,player_games=inputs['players'])
            state=engine.forecast_features
        else:
            engine=_engine(params,ratings)
            _daily_updates(engine,state,games,inputs['players'],cutoff)
        if any(abs(engine.team(row[s+'_id']).rating-row[s+'_rating'])>1e-8 for s in ['home','away']):
            raise ValueError('Recovered ratings do not match the selected stored forecast')
        rankings=[{'team_id':team,'team':roster[team],'elo':t.rating,'games':t.games,'wins':t.wins} for team,t in engine.teams.items()]
        archive['result']['rankings']=rankings
        token=digest({'cutoff':cutoff_text,'game_id':row['game_id'],'player_history':state.data['player_history']})
        # These tokens identify recovered display state, never an issued forecast.
        row['_captured_state_sha256']=row.get('state_sha256');row['state_sha256']=token
        archive['_internal'].update(feature_state=state.data,state_sha256=token)
        if report is not None and usable_context and row.get('base_home_probability') is not None:
            features,coverage=state.injury_features(game,report)
            recovered=[log_odds(row['base_home_probability'])]+features
            saved=(row.get('forecast_features') or {}).get('injury')
            if saved and (len(saved)!=len(recovered) or max(abs(a-b) for a,b in zip(saved,recovered))>1e-8):
                notes.append('Saved player covariates differ from recoverable history; retaining captured covariates and leaving player value history unavailable.')
                archive['_internal'].pop('state_sha256',None)
            elif not saved:
                row['forecast_features']={'injury':recovered}
                row['injury_coverage']={s:c for s,c in zip(['home','away'],coverage)}
        notes.append('League ranks and player histories are reconstructed from records completed strictly before this forecast cutoff; the stored probability is unchanged.')
        return {'row':row,'archive':archive,'completions':completions,'notes':notes,'verified':True}
    except (ValueError,KeyError) as error:
        notes.append(f'Pregame ranks/player history unavailable: {error}. Current state has not been substituted.')
        archive['result']['rankings']=[];archive['_internal'].pop('feature_state',None);archive['_internal'].pop('state_sha256',None)
        return {'row':row,'archive':archive,'completions':completions,'notes':notes,'verified':False}
