# Contributing

## Development setup

Use Python 3.12 and run commands from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-fit.txt
python -m unittest discover -s tests -v
```

`requirements.txt` installs the dashboard runtime. `requirements-fit.txt` additionally installs the scientific and parquet dependencies needed for historical ingestion and fitting. The live collector uses the standard library on macOS/Linux; Windows users can run it through WSL.

## Changes and validation

Keep changes focused and describe the behavior, rationale, and relevant checks. The CI workflow runs the full test suite without contacting ESPN or refitting the model. Data-only updater commits do not trigger this additional workflow; the collector performs its own core checks and validation.

Tests cover the probability and rating equations, chronological replay, frozen-release results, derived features, source normalization, immutable forecast revisions, correction handling, and season switching. Cross-platform numerical comparisons allow a small floating-point tolerance while preserving exact IDs, flags, and structure.

For changes to equations, feature definitions, data sources, fitting, or evaluation, update `paper/main.tex` and the relevant documentation. Compile the manuscript and resolve errors before submitting it. Keep the committed `paper/main.pdf` synchronized with the source; for example, with Tectonic installed, run `tectonic --outdir paper paper/main.tex` and inspect the resulting PDF. The file is a standalone LaTeX article; it does not require external figures or bibliography files.

## Model and data releases

- Keep `models/nba-v0.2/` and recorded historical results reproducible. Use a new model directory/version for a new study.
- Do not retune against an already observed test season and describe it as untouched evaluation.
- Preserve the live ledger, original issue times, parameter registry, and source correction history. Never manufacture pregame predictions for backfilled outcomes.
- Reject incomplete formula inputs; do not silently fill missing source values or bypass validation.
- Record source URLs, retrieval times, hashes, and any repairs when publishing rebuilt datasets.
- The historical publisher writes committed archives. Review its output before running it against an existing release.

## Repository hygiene

Keep raw downloads, caches, virtual environments, credentials, and generated build files outside tracked files. Do not commit Streamlit secrets or personal filesystem paths. Retain third-party attribution and distinguish project code from provider data rights. Changing repository visibility or hosted-app sharing is a separate owner decision.
