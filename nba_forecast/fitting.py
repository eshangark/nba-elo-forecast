"""Chronological parameter fitting with a verified accelerated replay."""

import math
from dataclasses import asdict

import numpy as np
from numba import njit
from scipy.optimize import differential_evolution

from .model import ALPHA_BASE, Parameters, box_features, timestamp
from .replay import replay

FIXED_C = Parameters().c
BOUNDS = [(1, 80), (0, 180), (0, 0.5), (-8, -1), (0, 2), (0, 0.25), (0, 1)] + [(-5, 5)] * 7
PARAMETER_NAMES = ["k", "home_advantage", "fatigue_weight", "log10_travel_weight",
                   "lead_weight", "performance_weight", "schedule_weight"] + [f"alpha_logit_{i}" for i in range(1,8)]


def decode(vector):
    logits = np.append(np.asarray(vector[7:]), 0.0)
    weights = np.exp(logits - logits.max())
    weights /= weights.sum()
    return Parameters(k=float(vector[0]), c=FIXED_C, home_advantage=float(vector[1]),
                      fatigue_weight=float(vector[2]), travel_weight=10**float(vector[3]),
                      lead_weight=float(vector[4]), performance_weight=float(vector[5]),
                      schedule_weight=float(vector[6]), alpha_weights=tuple(float(w) for w in weights))


def initial_vector():
    p = Parameters()
    return np.array([p.k, p.home_advantage, p.fatigue_weight, math.log10(p.travel_weight),
                     p.lead_weight, p.performance_weight, p.schedule_weight,
                     *[math.log(w/ALPHA_BASE[-1]) for w in ALPHA_BASE[:-1]]])


def prepare(games, warmup=10):
    games = sorted(games, key=lambda g:(timestamp(g["start"]),g["game_id"]))
    reference = replay(games, warmup_games=warmup)
    teams = sorted({g[s]["id"] for g in games for s in ["home","away"]})
    index = {team:i for i,team in enumerate(teams)}
    rows = reference["predictions"]
    pairs = np.array([[index[g["home"]["id"]],index[g["away"]["id"]]] for g in games],dtype=np.int64)
    context = np.array([[r["home_context"]["rest"],r["away_context"]["rest"],
                         math.exp(abs(r["home_context"]["timezone_change"])/3),
                         math.exp(abs(r["away_context"]["timezone_change"])/3),
                         r["home_context"]["travel"],r["away_context"]["travel"]] for r in rows])
    features = np.empty((len(games),2,8),dtype=np.float64)
    for i,g in enumerate(games):
        for j,(side,other) in enumerate([("home","away"),("away","home")]):
            x=box_features(g[side],g[other])
            features[i,j]=[x[0]/10,x[1],x[2],x[3],x[4],x[5]/3,-x[6],x[7]]
    values = np.array([[r["home_sos"],r["away_sos"],float(not g["neutral"]),
                       abs(g["home"]["points"]-g["away"]["points"])/max(g["home"]["largest_lead"],g["away"]["largest_lead"]),
                       r["home_win"],float(r["eligible_for_evaluation"])] for r,g in zip(rows,games)])
    return pairs,context,features,values


@njit(cache=True)
def probabilities(vector, pairs, context, features, values):
    weights=np.empty(8)
    maximum=max(0.0,np.max(vector[7:]))
    for i in range(7):weights[i]=math.exp(vector[7+i]-maximum)
    weights[7]=math.exp(-maximum)
    weights/=weights.sum()
    ratings=np.full(30,1500.0)
    history_sum=np.zeros(30)
    history_count=np.zeros(30)
    output=np.empty(len(pairs))
    travel_weight=10**vector[3]
    for i in range(len(pairs)):
        h,a=pairs[i,0],pairs[i,1]
        ortf=context[i,1]+context[i,2]+travel_weight*context[i,4]
        trof=context[i,0]+context[i,3]+travel_weight*context[i,5]
        z=math.log(10)*((ratings[h]-ratings[a]+vector[1]*values[i,2])/FIXED_C-vector[2]*math.log(ortf/trof))
        if z>=0:p=1/(1+math.exp(-z))
        else:
            expz=math.exp(z);p=expz/(1+expz)
        output[i]=p
        for side,team in [(0,h),(1,a)]:
            u=0.0
            for j in range(8):u+=weights[j]*features[i,side,j]
            if u>=0:current=1/(1+math.exp(-u))
            else:
                expu=math.exp(u);current=expu/(1+expu)
            current=max(1e-6,min(1-1e-6,current))
            baseline=history_sum[team]/history_count[team] if history_count[team]>0 else current
            ratio=max(0.25,min(4.0,current/baseline))
            y=values[i,4] if side==0 else 1-values[i,4]
            expectation=p if side==0 else 1-p
            sign=2*y-1
            delta=vector[0]*(y-expectation)*(1+sign*vector[6]*values[i,side])
            delta*=(1+vector[4]*math.log2(1+values[i,3]))*(1+sign*vector[5]*(ratio-1))
            ratings[team]+=delta
            history_sum[team]+=current
            history_count[team]+=1
    return output


def loss(vector, prepared):
    total,count=0.0,0
    for arrays in prepared:
        p=probabilities(vector,*arrays)
        selected=arrays[-1][:,5].astype(bool)
        y=arrays[-1][selected,4]
        p=np.clip(p[selected],1e-12,1-1e-12)
        total+=float(np.sum(-y*np.log(p)-(1-y)*np.log1p(-p)))
        count+=len(y)
    if not count:raise ValueError("No games after the warm-up")
    return total/count


def fit(training_seasons, seed=42, maxiter=150, warmup=10):
    prepared=[prepare(g,warmup) for g in training_seasons]
    initial=initial_vector()
    # Verify the numerical implementation before allowing it to fit any parameter.
    for games,arrays in zip(training_seasons,prepared):
        reference=replay(games,decode(initial),warmup_games=warmup)
        expected=np.array([r["home_probability"] for r in reference["predictions"]])
        if not np.allclose(probabilities(initial,*arrays),expected,atol=1e-11,rtol=0):
            raise AssertionError("Accelerated replay does not match canonical engine")
    print(f"Fitting {sum(len(a[0]) for a in prepared)} training games; {sum(int(a[-1][:,5].sum()) for a in prepared)} scored after warm-up",flush=True)
    baseline=loss(initial,prepared)
    iterations=[]
    def progress(intermediate_result):
        iterations.append(float(intermediate_result.fun))
        if len(iterations)%10==0:print(f"Generation {len(iterations)}: training log loss {intermediate_result.fun:.6f}",flush=True)
    optimized=differential_evolution(lambda v:loss(v,prepared),BOUNDS,rng=seed,maxiter=maxiter,popsize=8,
                                    tol=1e-5,polish=True,x0=initial,callback=progress,workers=1)
    if not math.isfinite(optimized.fun) or optimized.fun>baseline:
        raise ValueError("Fitted objective does not improve on the starting parameters")
    params=decode(optimized.x)
    # Canonical verification at the fitted point also covers parameter-dependent PAF history.
    for games,arrays in zip(training_seasons,prepared):
        expected=np.array([r["home_probability"] for r in replay(games,params,warmup_games=warmup)["predictions"]])
        if not np.allclose(probabilities(optimized.x,*arrays),expected,atol=1e-11,rtol=0):
            raise AssertionError("Fitted accelerated replay disagrees with canonical engine")
    return params,{"method":"bounded differential evolution with L-BFGS-B polish","seed":seed,
                   "warmup_games_per_team":warmup,"bounds":dict(zip(PARAMETER_NAMES,BOUNDS)),
                   "initial_training_log_loss":baseline,"fitted_training_log_loss":float(optimized.fun),
                   "iterations":int(optimized.nit),"function_evaluations":int(optimized.nfev),
                   "optimizer_success":bool(optimized.success),"optimizer_message":str(optimized.message),
                   "training_trace":iterations,"parameters":asdict(params),
                   "fixed_constants":{"exponent_base":10,"c":FIXED_C,"initial_rating":1500,"timezone_scale_hours":3},
                   "training_season_end_years":[g[0]["season"] for g in training_seasons]}
