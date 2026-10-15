# Roadmap

The first implementation includes the canonical NBA model, five clean historical seasons, fitted constants, comparator diagnostics, the Streamlit dashboard, and scheduled after-game collection. The frozen production model remains version 0.2.0.

## Prospective evaluation

- Accumulate genuinely issued forecasts and completed regular-season outcomes.
- Track collection failures, source latency, and forecast coverage alongside probability scores.
- Compare live calibration with historical replay, explicitly accounting for their different cutoff policies.

## Future research

- Study coefficient bounds, regularization, and feature ablations with a separately versioned protocol.
- Evaluate season initialization and carryover using training data and a new evaluation design.
- Review later seasons prospectively rather than selecting changes against the already observed 2025–26 test.

These are research directions, not implemented features or promised performance gains. Preserve issued forecasts and the current frozen configuration throughout future changes.
