"""Independent season archives and a current-season default."""

import json
from datetime import date
from pathlib import Path

from .data import write_json


def season_label(year):
    return f"{year}-{str(year + 1)[-2:]}"


def current_season(today=None):
    today = today or date.today()
    return season_label(today.year if today.month >= 7 else today.year - 1)


def load_index(root, today=None):
    entries = json.loads((Path(root) / "index.json").read_text())["seasons"]
    labels = [entry["season"] for entry in entries]
    if len(labels) != len(set(labels)):
        raise ValueError("Duplicate season archives")
    current = current_season(today)
    if current not in labels:
        # Current view stays the default even before a season's first published snapshot.
        entries.append({"season": current, "status": "pending", "file": None})
    return sorted(entries, key=lambda e: e["season"], reverse=True), current


def load_season(root, entry):
    if not entry.get("file"):
        return None
    root = Path(root).resolve()
    path = (root / entry["file"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Season path leaves archive directory")
    payload = json.loads(path.read_text())
    if payload["season"] != entry["season"]:
        raise ValueError("Season index and archive disagree")
    return payload


def publish_archive(root, result, games, coverage):
    years = {int(g["season"]) for g in games}
    if len(years) != 1:
        raise ValueError("Archive must contain one season")
    label = season_label(next(iter(years)) - 1)
    root = Path(root)
    output = {"season": label, "status": "partial_historical_replay",
              "published_at": coverage["collected_at"], "result": result,
              "coverage": {k: coverage[k] for k in ["start", "end", "discovered", "parsed", "failures"]}}
    write_json(root / label / "snapshot.json", output)
    write_json(root / label / "games.json", games)
    write_json(root / label / "collection_manifest.json", coverage)
    manifest_path = root / "index.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"seasons": []}
    manifest["seasons"] = [e for e in manifest["seasons"] if e["season"] != label]
    manifest["seasons"].append({"season": label, "status": output["status"], "file": f"{label}/snapshot.json"})
    manifest["seasons"].sort(key=lambda e: e["season"], reverse=True)
    write_json(manifest_path, manifest)
    return label
