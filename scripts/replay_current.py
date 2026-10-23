"""Rebuild current-method season views without changing issued forecast ledgers."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_forecast.current_replay import refresh_current_replays

if __name__ == '__main__':
    refresh_current_replays(Path(__file__).resolve().parents[1])
