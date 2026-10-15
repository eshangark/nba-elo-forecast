# Data attribution and provenance

## Basketball records

ESPN is the underlying source of schedules, game metadata, team/player box scores, and play-by-play. Historical ingestion downloads free ESPN-derived parquet archives from [SportsDataverse](https://github.com/sportsdataverse/sportsdataverse-data):

- Release `espn_nba_schedules`: `nba_schedule_YEAR.parquet`
- Release `espn_nba_team_boxscores`: `team_box_YEAR.parquet`
- Release `espn_nba_pbp`: `play_by_play_YEAR.parquet`

YEAR is the season's ending year, 2022–2026. Each season's `collection_manifest.json` records exact release URLs, file sizes, and SHA-256 hashes. The SportsDataverse repository carries an MIT license; its license notice is retained under `third_party/`. This attribution does not claim that the repository's software license resolves all rights in underlying provider records.

Primary replacements use ESPN's public NBA summary feed:
`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=GAME_ID`.
Collection manifests record replacement URLs, retrieval times, and hashes. Endpoints have no service guarantee. Raw source caches remain local; committed files contain validated normalized records and derived features.

## Geography

[GeoNames cities15000](https://download.geonames.org/export/dump/) supplies city coordinates and IANA time zones under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). The geography archive hash is recorded in season manifests. City-centre coordinates approximate venue locations; distances do not measure actual travel itineraries.
