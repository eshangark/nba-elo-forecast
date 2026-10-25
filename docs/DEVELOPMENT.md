# Development and operation

Run commands from the repository root using Python 3.12. `requirements.txt` installs the dashboard; `requirements-live.txt` adds the PDF parser for collection; `requirements-fit.txt` adds scientific, parquet and tree-training dependencies. Live probability scoring uses portable JSON and the standard library, not scikit-learn or pickle. The live collector runs on macOS/Linux; Windows users can use WSL.

## Tests

The dashboard uses Streamlit's polling file watcher to avoid Linux inotify
instance limits leaving imported modules stale after a deployment. If a
deployment reports an import name that exists in the published source, check
the cloud logs for watcher failures and reboot the app from **Manage app**.
A passing clean-start test does not verify an already-running cloud process.

```sh
python -m pip install -r requirements-fit.txt
python -m unittest discover -s tests -v
```

The suite checks equations, canonical frozen replays, feature derivations, source normalization, chronology, correction handling, immutable forecast revisions, and season switching. Cross-platform numerical comparisons permit floating-point differences within 1e-12 while retaining exact identifiers, flags, and structure.

[Code validation](../.github/workflows/ci.yml) installs the full dependencies and runs all checks without contacting ESPN or refitting constants. Data-only updater commits do not trigger that extra workflow; collection performs its own core checks and input validation.

## Reproduce the research

The committed game records and frozen parameters reproduce the recorded evaluation through the canonical replay tests. To rebuild data and refit the original training protocol:

```sh
python scripts/download_geography.py
python scripts/download_history.py --output data/raw/history
python scripts/build_history.py --archive-dir data/raw/history --cities data/raw/geography/cities15000.zip --cache data/raw/espn --output data/processed/history
python scripts/fit_model.py --history data/processed/history --output data/processed/fitted --seed 42 --maxiter 150
```

These commands write local research outputs, leaving frozen release files intact. Mutable archives and optimizer/platform differences can affect a refit. Source hashes and full-precision optimizer settings are recorded with the release.

To run the comparator study:

```sh
python scripts/compare_models.py
```

See [evaluation](EVALUATION.md) for protocols and interpretation. `scripts/publish_history.py` writes committed historical archives; review regenerated outputs before replacing an existing release.

## Reproduce v0.3 models

```sh
python -m pip install -r requirements-fit.txt
python scripts/prepare_forecaster_data.py --output data/raw/forecasters
python scripts/fit_forecasters.py --players data/raw/forecasters/players --reports data/raw/forecasters/reports.json --output data/processed/nba-v0.3 --backtest
```

The preparation command caches free historical player archives and official morning PDFs, records source hashes/errors and requires at least 95% verified report-date coverage before fitting. `--offline` validates cached files without network calls. Inspect `data-quality.json` and selection reports before promoting an artifact. The fit command preserves original `snapshot.json` files and creates separate `snapshot-v0.3.json` historical outputs; review those before changing the season index. The original core fit still optimizes its warmup-filtered objective. The two probability heads select settings on the last prior season and refit only earlier seasons.

The bundle freezes carryover, season-start ratings, player/form histories, core parameters, ordered/scaled head features and numerical tree nodes. Tree export is tested against the fitted estimator. Refit output is not prospective evidence, and small preparation differences can change the boosted candidate selected.

## Collect live data

```sh
python -m pip install -r requirements-live.txt
python scripts/download_geography.py
python scripts/update_live.py --cities data/raw/geography/cities15000.zip
```

The default horizon covers seven Eastern-calendar dates, including the entire last date; `--horizon-days 14` extends it. Normal runs revisit the previous seven dates and unresolved events. `--full-refresh` rechecks the whole current-season provider calendar for older corrections. Requests use individual dates and provider calendar metadata; scoreboard and checked final-summary responses are refreshed.

A filesystem lock permits one writer. Validated output is atomically saved to `data/seasons/SEASON/live.json`; failure leaves the last valid bundle intact and records an attempt in `update_status.json`. Raw responses remain in ignored local caches. Version 0.3 retains half of previous final Elo deviations; season records reset and preseason results are excluded. A later season can initialize from a complete compatible prior live season; incomplete or incompatible histories block that transition.

## Live forecast lifecycle

Forecasts are issued only for games still in the future, with issue time taken after source collection. The CLI cannot backdate them. Changed model state or schedule context appends a revision; identical inputs reuse the existing record. Earlier probabilities, IDs, timestamps, registered constants, and context remain unchanged.

Upcoming forecasts hold current ratings fixed while projecting rest and venue travel through the announced schedule. They do not invent future outcomes. After completion, the displayed prediction is the latest revision issued before the actual recorded start and matching the opponents. Games first observed after completion have blank predictions and never become live forecast observations.

Validated completed games deterministically rebuild current rating state. A timeline computes internal update expectations at tip-off and updates/recenters ratings at completion. Corrected source games can alter present ratings and future revisions without applying a game twice or rewriting issued forecasts. Internal replay expectations are not issued predictions. Evaluation joins the original ledger to the latest validated outcomes; model changes retain old parameter configurations.

## Hosting and scheduling

| Component | Configuration |
| --- | --- |
| Frontend | Streamlit Community Cloud, `main`, `app.py`, Python 3.12 |
| Production model | `models/nba-v0.3/bundle.json` |
| Backend | GitHub Actions at minute 17 every two UTC hours |
| Browser refresh | Rereads saved snapshots every minute while open |

The [hosted application](https://eshan-nba-elo-forecast.streamlit.app/) is publicly accessible. App sharing and repository visibility are separate settings. Page refresh does not fetch provider data or fit parameters.

The [update workflow](../.github/workflows/update-live.yml) supports scheduled and manual runs, and refreshes forecasts after a model/collector release is pushed. Standard jobs time out after five minutes; manual full-refresh jobs have ten minutes. Core checks precede ingestion. Failed collection can publish a failure status while keeping the valid snapshot, and the job reports failure. A branch-head check and ordinary push prevent overwriting concurrent changes. Only processed season data is committed by the updater; raw caches are not uploaded. NBA injury-source failures visibly fall back to Elo while keeping valid team updates. Player-source failures leave explicit gaps in player histories.

Collection uses free endpoints without an availability guarantee. GitHub scheduling may be delayed, included Actions usage is shared across repositories, and exhaustion can stop updates. Paid usage is disabled in the current account configuration. Streamlit may sleep inactive apps. Use the saved successful collection timestamp to assess freshness.

For maintenance, inspect [workflow runs](https://github.com/eshangark/nba-elo-forecast/actions/workflows/update-live.yml) or start a manual full refresh; use Streamlit **Manage app** for build logs and sharing. Disable the Actions workflow if collection must stop. Dependency/runtime changes require renewed hosting checks.

## Contributions and model changes

Keep changes focused and include relevant validation. Update [`paper/main.tex`](../paper/main.tex) when equations, feature definitions, sources, fitting, or evaluation change. Keep [`paper/main.pdf`](../paper/main.pdf) synchronized; with Tectonic installed:

```sh
tectonic --outdir paper paper/main.tex
```

Inspect the PDF after compiling. Keep credentials, personal filesystem paths, raw downloads, environments, and generated build files outside tracked files; retain third-party notices.

Preserve the frozen v0.2 configuration and issued ledger. New formulas, constraints, or training studies require a separately versioned model and evaluation protocol. The observed 2025–26 test cannot become an untouched test again. Carryover and both probability heads are implemented in v0.3. Prospective comparisons remain necessary; the boosted challenger is not a claim of stable superiority. Original issued rows and v0.2 artifacts remain unchanged.

## Rebuild the current-method dashboard views

Run `python scripts/replay_current.py` after changing the active model. It rebuilds all five archived seasons from committed normalized pregame inputs and the current season from recorded pregame cutoffs, without changing original archives or issued forecasts. The live collector runs this step after successful collection, and the scheduled workflow commits the resulting `current-model.json` files. Regenerating inputs after changing player-history derivations requires the validated source player observations already included in the compressed replay inputs; provider corrections should be documented as a new input snapshot.

## Test a model change on a shared sample

Use `compare_samples` from `nba_forecast.evaluation` with baseline and candidate rows containing the same canonical IDs, outcomes, cutoff timestamps, eligibility and source-snapshot IDs. Pass `established=True` only when the same ten-prior-game window is intended for every model. Do not independently filter candidates or silently intersect their available games. Run `python scripts/audit_comparisons.py` and the full test suite before publishing; inspect accuracy, log-loss and Brier differences on the saved sample ID. The existing three-season audit preserves old chronological archives and does not refit on their outcomes.
