# Dataset guide

This release includes five complete NBA regular seasons, 2021–22 through 2025–26: 1,230 games per season, 6,150 games total, and two team-game rows per game. Playoffs, preseason, All-Star games, and Cup finals are excluded.

## Historical season files

Each `seasons/YYYY-YY/` archive contains:

| File | Meaning |
| --- | --- |
| `games.json` | Validated game records, box-score counts, venues, availability-time proxies, quality flags |
| `team_games.csv` | Two normalized team box-score rows per game |
| `model_features.csv` | Pregame contexts and probabilities, plus explicitly named postgame update features |
| `snapshot.json` | Reconstructed forecasts, outcomes, final ratings, evaluation, and calibration bins |
| `collection_manifest.json` | Coverage checks, source URLs/hashes, retrieval metadata, and source replacements |

Pregame features use prior games only. Postgame columns describe information available after completion and must not be used to predict that same game's outcome. CSVs include identifiers and eligibility flags; IDs should be treated as strings. Detailed units and formulas are in [DATA_AND_FORMULAS.md](../DATA_AND_FORMULAS.md).

## Current season

`seasons/index.json` identifies the available seasons and their snapshot paths. The current-season `live.json` is the authoritative atomic bundle: ratings, observed source games, schedule, issued forecast revisions, parameter registry, and correction history. `update_status.json` records collection status. The initial `snapshot.json` is retained as a seed and is not the active live ledger.

Historical predictions are reconstructed replays. Current-season predictions are scored as live only if actually issued before the recorded game start; backfilled games without issued forecasts are excluded. See [LIVE_PIPELINE.md](../LIVE_PIPELINE.md).

## Provenance and reuse

ESPN supplies the underlying basketball records. SportsDataverse provides ESPN-derived archives, supplemented by validated primary ESPN summaries. GeoNames provides city coordinates and time zones. Source repairs and availability-time assumptions are disclosed; city distances do not represent actual team itineraries.

See [SOURCES.md](../SOURCES.md) and `../third_party/` for attribution. Provider data, raw-source test fixtures, and derived datasets are separate from original project code; a project code license does not grant rights to provider records. GeoNames material retains its CC BY 4.0 attribution requirements. No blanket license for all dataset contents is asserted here.

Raw parquet files, geography downloads, and response caches are intentionally excluded from Git. Rebuilding requires network access and may receive revised provider records; manifests identify the downloads used for the recorded release.
