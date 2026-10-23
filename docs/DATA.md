# Data and sources

## Coverage and files

Five complete NBA regular seasons, 2021–22 through 2025–26, contain 1,230 games each, 30 teams, and 82 games per team: 6,150 games and 12,300 team-game rows. Preseason, playoffs, All-Star games, and the NBA Cup final are excluded. Cup games counting toward the regular season are included.

Each historical directory under [`data/seasons/`](../data/seasons/) contains:

| File | Contents |
| --- | --- |
| `games.json` | Validated game records, box-score counts, venues, availability-time proxies, quality flags |
| `team_games.csv` | Two normalized team box-score rows per game |
| `model_features.csv` | Pregame context and probabilities, plus explicitly named postgame update features |
| `snapshot.json` | Preserved original v0.2 forecasts, outcomes, final ratings and evaluation |
| `snapshot-v0.3.json` | Corrected retrospective carryover, injury and boosted forecasts for the three evaluation seasons |
| `collection_manifest.json` | Coverage checks, source URLs/hashes, retrieval metadata, and source replacements |

Treat IDs as strings. Postgame columns describe information available after completion and must not predict that same game's outcome. The [paper](../paper/main.pdf) defines every derived feature, equation, unit, and numerical convention; [`model.py`](../nba_forecast/model.py) is the canonical implementation. The active core coefficients, player/form initialization state, logistic scalers/weights, portable trees and feature order are in the [v0.3 model bundle](../models/nba-v0.3/bundle.json). The original [v0.2 parameters](../models/nba-v0.2/parameters.json) remain preserved.

[`data/seasons/index.json`](../data/seasons/index.json) identifies available seasons and snapshot paths. The current-season `live.json` is the authoritative atomic bundle: ratings, observed games, schedule, issued revisions, parameter registry, source provenance, and correction history. `update_status.json` records the latest collection attempt. The initial `snapshot.json` is retained as a seed, not the active ledger.

## Required inputs

| Input | Source | Use |
| --- | --- | --- |
| Game/team IDs, tip-off, season, status, final scores | ESPN schedule/header | Chronology, outcomes, margin, schedule strength |
| Venue city and neutral status | ESPN venue metadata | Home advantage and travel context |
| PTS, FGM, FGA, 3PM, 3PA, FTM, FTA, OREB, DREB, AST, player TOV, STL | ESPN team/player box scores | Postgame performance features |
| Largest lead for both teams | ESPN box score or validated score path | Lead retention |
| Latitude, longitude, IANA time zone | GeoNames | Venue-city distance and time-zone proxies |
| Completion-time proxy | Terminal EndGame wallclock or dated final recap | Prior-result availability checks |

Rest is the number of intervening Eastern calendar dates; back-to-back games have zero rest days. Season openers use three rest days and zero travel/time-zone change. Travel uses Haversine kilometres between consecutive venue cities. Both cities' time-zone offsets are evaluated at the current tip-off to avoid artificial changes from daylight saving time. These are context proxies, not measured itineraries.

## Validation and repairs

Validation enforces unique game/team identities, opponent pairing, header-score agreement, finite nonnegative integer counts, shot-attempt constraints, scoring identities, plausible assists/steals, positive feature denominators, and peak leads consistent with final margins. Missing values are never silently converted to zero; unresolved records block publication.

873 historical games required validated primary ESPN replacements, mostly for incomplete archival play-by-play. Largest leads can be recovered only from a score path ending at the header score. Team aggregates can be repaired only from complete player rows with matching point/shooting totals. Turnovers consistently mean summed **player turnovers**, excluding provider non-player team turnovers. Repairs are recorded in season manifests and [`data_quality.json`](../models/nba-v0.2/data_quality.json).

Seventeen games use final-recap publication times as completion proxies. One game with source play dates shifted by a day uses a flagged conservative tip-off-plus-eight-hours availability bound, not an observed completion time. Source corrections may be present in historical records; replay does not establish when they first reached a live feed.

## Forecast timing

Historical forecasts freeze an entire Eastern-calendar slate at the earlier of 10:00 Eastern and one hour before its first tip-off. All previous slates must be complete by that cutoff. Results and box scores update ratings after the slate; current-game features never enter that game's prediction.

Live collection updates ratings after individual completions and stores actual forecast issue times. Only predictions genuinely issued before recorded tip-off are scored as live. Backfilled games without issued predictions can update ratings but are excluded from live scores. Primary scoring additionally requires ten observed prior games for each team at issuance. These cutoff policies differ, so historical accuracy is not a live-service claim. See [development and operation](DEVELOPMENT.md#live-forecast-lifecycle).

## Player and injury inputs

SportsDataverse's free `espn_nba_player_boxscores` release supplies `player_box_YEAR.parquet`. Played-player IDs, minutes and box counts are validated against canonical opponents, team totals and plausible complete minute totals. Float and integer player IDs normalize to the same string identity. Across the five seasons, 12,235 of 12,300 team-games pass; 65 inconsistent player histories are excluded rather than treated as absences. The core team records remain valid. Full archived player boxes stay in ignored raw caches; frozen player-history summaries needed for live initialization are in the model bundle.

Official NBA injury PDFs provide actual publication timestamps, matchup/date/team, player names and participation designations. Of 816 historical game dates, 815 morning reports were retrieved. Every production parse matched the audited records; independent PDF text checks verified designation counts. Exact unambiguous normalized names map to stable ESPN IDs; unmapped players are explicitly unknown. A full-season roster union, eventual minutes or final absence never becomes a pregame feature.

Player value uses earlier Game Score per minute, shrunk toward 0.3 with 80 prior minutes; expected minutes use a ten-observation exponential history. This is a descriptive proxy, not RAPM. Current-slate player histories are frozen at the morning historical cutoff, including cross-team trade/report overlaps. Live feature histories update only from completed games.

The live collector reads the official index or at most four already-due, distinct public quarter-hour PDF versions. It verifies the PDF header timestamp, rejects future/stale reports, and requires date/team/matchup agreement. An unavailable index is not evidence that a dated public PDF is absent. If no verified report covers a game, both adjusted models fall back to base Elo; an unsubmitted team is modeled with explicit missingness. No access-denied URL is retried.

New issued forecast rows store all three model probabilities, the actual standardized-model input vectors, report timestamp/hash, coverage, version and bundle fingerprint. The parameter registry preserves the numerical heads as well as core constants. Unavailable player records and injury-source errors are visible in `_internal.auxiliary_status`; an injury outage does not stop valid team-result ingestion. A mandatory game-source failure still preserves the last valid snapshot.

The two `tests/fixtures/injury-*.pdf` files are unmodified official NBA reports used to check old table headers, page continuations and unsubmitted teams. Their underlying source URLs follow the official `ak-static.cms.nba.com/referee/injury/Injury-Report_DATE_08AM.pdf` path. They retain provider rights; the project's MIT license does not relicense them.

## Sources and reuse

## Basketball records

ESPN is the underlying source of schedules, game metadata, team/player box scores, and play-by-play. Historical ingestion downloads free ESPN-derived parquet archives from [SportsDataverse](https://github.com/sportsdataverse/sportsdataverse-data):

- Release `espn_nba_schedules`: `nba_schedule_YEAR.parquet`
- Release `espn_nba_team_boxscores`: `team_box_YEAR.parquet`
- Release `espn_nba_pbp`: `play_by_play_YEAR.parquet`

YEAR is the season's ending year, 2022–2026. Each season's `collection_manifest.json` records exact release URLs, file sizes, and SHA-256 hashes. The SportsDataverse repository carries an MIT license; its license notice is retained under [`third_party/`](../third_party/). This attribution does not claim that the repository's software license resolves all rights in underlying provider records.

Primary replacements use ESPN's public NBA summary feed:
`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=GAME_ID`.
Collection manifests record replacement URLs, retrieval times, and hashes. Endpoints have no service guarantee. Raw source caches remain local; committed files contain validated normalized records and derived features.

## Official injury reports

[NBA publication policy](https://official.nba.com/nba-injury-report-2026-27-season/) and public timestamped PDFs under `https://ak-static.cms.nba.com/referee/injury/` supply status information. Publication continues during the day; later updates cannot enter a morning historical forecast. Header timestamps do not prove the source never received later corrections.

## Geography

[GeoNames cities15000](https://download.geonames.org/export/dump/) supplies city coordinates and IANA time zones under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). The geography archive hash is recorded in season manifests. City-centre coordinates approximate venue locations; distances do not measure actual travel itineraries.

Original project code and documentation use the [MIT License](../LICENSE). Provider records, raw-source fixtures, derived datasets, and third-party materials retain separate rights and notices. No blanket license for all dataset contents is asserted here; GeoNames material retains its CC BY 4.0 attribution requirements.

Raw parquet files, geography downloads, and response caches are excluded from Git. Rebuilding requires network access and may receive revised records; manifests identify downloads used for the recorded release.

## Current-method replay inputs and outputs

Each historical season has a deterministic `replay-inputs.json.gz`: normalized, validated prior-player observations (athlete ID, minutes and descriptive Game Score), date/team/matchup-matched injury statuses, cutoff timestamps and source hashes. These are derived provider records with the same reuse notices as the other datasets. A source archive hash and player validation failures accompany each season. Outcome columns remain in the existing `games.json`; own-game player observations enter history only after its pregame predictions.

`current-model.json` stores the current specification's retrospective predictions, reconstructed ratings, all-game and ten-prior-game scores, bundle fingerprint and source hashes. Original `snapshot*.json` and issued live ledgers remain intact. Historical inputs use the original morning cutoff; current-season rows use the last actual pregame issuance cutoff and recorded rest/travel inputs. Saved raw reports allow rebuilding injury features; older saved injury covariates use the current base probability and fitted head. Missing historical injury inputs fall back to Elo explicitly. Corrected historical provider records can differ from what the provider originally published; this reconstruction is not a historical source-vintage guarantee.

The collector regenerates these views after every successful update. Model/engine/input changes trigger that workflow, and `python scripts/replay_current.py` rebuilds them locally. Source-result and model fingerprints prevent the dashboard loading a replay for a different snapshot or bundle.
