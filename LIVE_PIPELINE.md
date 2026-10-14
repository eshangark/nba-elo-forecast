# Observed forecasts and after-game updates

The collector uses the frozen NBA v0.2 configuration. It has been run against the actual free ESPN feed, publishing the first three regular-season forecasts for 2026–27. There are no completed regular-season games in that initial snapshot; preseason results are excluded and all teams still start at 1500. The pipeline supports manual runs and a two-hour GitHub Actions schedule. Private Streamlit hosting is prepared but not deployed.

## Run an update

Use Python 3.10+ on macOS or Linux. No fitting dependencies or paid API key are needed.

```sh
python scripts/download_geography.py
python scripts/update_live.py --cities data/raw/geography/cities15000.zip
```

The default looks seven Eastern-calendar dates ahead, including the whole last date. Use `--horizon-days 14` for a larger window. Normal updates revisit the previous seven dates plus unresolved events; `--full-refresh` checks the current season's entire provider calendar, including older corrections. All scoreboard and checked final-summary requests refresh their cached responses. ESPN date-range queries were rejected in the source check, so the collector uses individual calendar dates with source-provided whitelist metadata.

## Storage and guarantees

- `data/seasons/SEASON/live.json` is the atomic authoritative bundle: rankings, completed games, upcoming probabilities, issued revisions, parameter registry, source provenance, and correction log.
- `update_status.json` records the latest attempt. Ingestion or validation failure leaves the published bundle intact, and the app warns that it is showing the last valid data.
- A filesystem lock permits one collector writer at a time and releases automatically when its process exits.
- Raw responses remain under ignored `data/raw/`; no credentials are stored.

The current season index points to the live bundle. Completed historical archives retain their original reconstructed predictions. Each new season resets ratings rather than carrying over previous ratings.

## Forecast issuance

A forecast is recorded only when the collector observes a scheduled game whose tip-off is still in the future. Issue time is taken **after** fetching the source records; the CLI has no backdate option. New input state or schedule context adds a revision. Identical inputs reuse the existing revision. Old records retain their exact probabilities, timestamps, IDs, model/configuration identifiers, and pregame context.

Upcoming estimates keep current ratings fixed while projecting rest and venue travel through the announced schedule. They do not invent outcomes or future rating changes. These estimates are revised after new results or schedule changes. Games already started never receive newly issued pregame forecasts.

After completion, the displayed probability is the latest stored revision issued before the actual recorded start and matching the opponents. A game discovered only after completion has a blank prediction: it can update ratings, but is never converted into a live forecast. Live probability metrics use issued forecasts only; primary scoring additionally requires ten observed prior games for both teams at issuance. The bundle also retains descriptive scores for all issued forecasts.

## Rating state and corrections

Current rating state is deterministically reconstructed from validated completed games. A timeline predicts an internal update expectation at each tip-off using source-completion proxies for earlier games, then updates and recenters ratings at completion. This permits corrected data or missed collections to rebuild state without applying a game twice. These internal estimates are not treated as issued forecasts. Source completion timestamps are availability proxies and do not prove historical provider publication timing.

Rating replay is separate from the immutable issuance ledger: corrected outcomes/boxes can change present ratings and future revisions, while earlier issued probabilities remain unchanged. Evaluation joins issued forecasts to the latest validated outcomes. Changing model configuration also preserves old revisions and their registered constants.

Live updates are processed after individual completions when the collector runs; the historical evaluation froze an entire daily slate. The two operational cutoff policies differ, so the historical 68.56% result is not a measured accuracy of this live service. Future issued forecasts will establish that evidence.

## Checks

Tests exercise duplicate polling, correction replay, preservation of issued probabilities, missed-game backfill, future-time rejection, failed collection, single-writer locking, preseason/Cup exclusion, and live UI views. A successful manual feed fetch verifies current source connectivity, not automatic operation or guaranteed endpoint availability.

## Scheduled operation

`.github/workflows/update-live.yml` runs at minute 17 every two hours in UTC and can also be started manually from GitHub Actions. Actions scheduling is best-effort and may be delayed; this is periodic collection rather than a push feed. Standard jobs time out after three minutes; a manual full refresh can run for ten minutes. Checkout and Python setup actions are pinned to verified vendor commit hashes.

Core checks precede ingestion. Failed collection leaves the valid bundle intact and publishes the failure status when possible; the workflow still fails so GitHub records the error. A branch-head check and ordinary fast-forward push protect newer commits. No GitHub secrets, paid API keys, Actions caches, or artifacts are required. Only processed season data is committed.

The schedule is designed to fit the shared free Actions allowance; paid usage is blocked by the account’s existing zero-dollar Actions budget. Other repositories and manual runs share that allowance. If it is exhausted, updates can stop until the allowance resets. Hosting remains a separate pending private deployment.

The first successful cloud run passed 36 core checks, skipped nine optional frontend/fitting checks, refreshed the ESPN feed, and committed the new snapshot in 40 seconds. The full local suite passes all 45 tests. Ubuntu 24.04 is pinned to the verified runner platform.
