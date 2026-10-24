"""Verify existing model comparisons on identical games and regenerate the UI audit."""
import json
import hashlib
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nba_forecast.data import write_json
from nba_forecast.evaluation import compare_variants


def audit(root):
    rows=[]; folds=[]
    for season in ['2023-24','2024-25','2025-26']:
        result=json.loads((root/f'data/seasons/{season}/snapshot-v0.3.json').read_text())['result']
        data_hash=hashlib.sha256((root/f'data/seasons/{season}/games.json').read_bytes()+(root/f'data/seasons/{season}/replay-inputs.json.gz').read_bytes()).hexdigest()
        for row in result['predictions']:
            row['source_data_sha256']=data_hash
        comparison=compare_variants(result['predictions'])
        for name,scores in comparison['metrics'].items():
            expected=result['model_comparison'][name]['metrics_all_issued']
            for metric in ['log_loss','brier_score','winner_accuracy']:
                if abs(scores[metric]-expected[metric])>1e-12:
                    raise ValueError(f'Stored scores differ: {season} {name} {metric}')
        folds.append({'season':season,'all_games':comparison,'established':compare_variants(result['predictions'],established=True)})
        rows.extend(result['predictions'])
    pooled=compare_variants(rows)
    published=[{k:r[k] for k in ['game_id','start','home','away','home_win','forecast_cutoff','eligible_for_evaluation','home_probability','away_probability']} for r in rows]
    report={'protocol':'Exact matched retrospective next-season samples; no candidate-specific omissions.',
            'pooled':pooled,'folds':folds,'published_rows':published}
    write_json(root/'models/nba-v0.3/matched-evaluation.json',report)
    return report

if __name__=='__main__':
    report=audit(Path(__file__).resolve().parents[1]);print('Matched',report['pooled']['games'],'games across all three procedures.')
