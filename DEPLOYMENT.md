# Deployment and operation

The initial NBA Elo Forecast release is deployed at:

**https://eshan-nba-elo-forecast.streamlit.app/**

The app and GitHub repository are private. Sign in with an authorized Streamlit/GitHub account to view it. Sharing settings are managed separately from repository visibility.

## Components

| Component | Configuration |
| --- | --- |
| Frontend | Streamlit Community Cloud, `main`, root `app.py`, Python 3.12 |
| Model | Frozen `models/nba-v0.2/parameters.json` |
| Collection | GitHub Actions at minute 17 every two UTC hours |
| Current data | Atomic `data/seasons/SEASON/live.json` bundle |
| Browser freshness | Rereads the saved snapshot every minute while the page is open |
| Historical data | Five complete regular seasons, 2021–22 through 2025–26 |

Page refresh does not fetch ESPN data or refit constants. It displays outputs from the independent backend process. GitHub scheduling is best-effort and can be delayed; this is periodic after-game collection, not an instantaneous event feed.

## Verification

- The hosted application loads without an exception and defaults to the current season.
- Upcoming probabilities, team ratings, archived season selection, and held-out evaluation are visible.
- The 2025–26 box-score download has 2,460 rows, with all fields matching the stored dataset.
- Light and dark themes work; the simplified menu contains theme selection and About.
- The sharing panel's “Make this app public” option is unchecked.
- The cloud updater has refreshed the feed and committed its snapshot. Model and interface checks are covered by the test suite.

## Cost and limits

No paid service, API key, or extra credential is configured. GitHub Actions uses the account's shared included allowance, with paid usage disabled in the current account configuration. Standard jobs have a three-minute timeout, and a manual full-refresh job can run for ten minutes. No raw-response cache or workflow artifacts are uploaded.

If included Actions usage runs out, updates can stop until the allowance resets. Streamlit Community Cloud may sleep an inactive app; opening it can require a wake-up/build delay. Freshness always refers to the saved successful collection time.

## Maintenance

- [Workflow runs](https://github.com/eshangark/nba-elo-forecast/actions/workflows/update-live.yml): check failures or run an update manually. Select full refresh to recheck older source corrections.
- Streamlit **Manage app**: inspect build logs and settings; keep sharing private.
- GitHub **Actions → Update NBA forecasts → Workflow options**: disable the schedule if collection must stop.
- Preserve the issued-forecast ledger when correcting source data or changing models. A new fitting study must retain the current release's configuration and archives.
- Repository commits are picked up by the hosted app. Changes to dependencies or the Python runtime require renewed deployment checks.

The current season starts all teams at 1500 and excludes preseason results. Initial upcoming probabilities can therefore be similar; historical accuracy is not a live accuracy claim. Prospective scoring will accumulate only as genuinely issued forecasts reach completed regular-season outcomes.
