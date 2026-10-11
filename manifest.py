"""
manifest.py
-----------
Writes a small JSON "run manifest" next to the outputs so any ranking can be
reproduced and audited later: when it ran, the exact query/arguments, every
setting in config.py at that moment, library versions, which benchmark was
used, how many funds survived each stage, and how fresh the underlying NAV
data was.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config


def config_snapshot() -> dict:
    """All UPPER_CASE settings in config.py, JSON-safe."""
    snap = {}
    for key in dir(config):
        if not key.isupper():
            continue
        try:
            json.dumps(getattr(config, key))
            snap[key] = getattr(config, key)
        except TypeError:
            snap[key] = repr(getattr(config, key))
    return snap


def config_hash(snapshot: dict) -> str:
    blob = json.dumps(snapshot, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def write_manifest(path: str, run_info: dict) -> dict:
    snap = config_snapshot()
    manifest = {
        "run_started_utc": run_info.get("started_utc"),
        "run_finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": run_info.get("status", "unknown"),
        "query": run_info.get("query"),
        "category": run_info.get("category"),
        "arguments": run_info.get("arguments", {}),
        "benchmark": run_info.get("benchmark"),
        "forward_signals": run_info.get("forward"),
        "category_valuation": run_info.get("category_valuation"),
        "counts": run_info.get("counts", {}),
        "latest_nav_date": run_info.get("latest_nav_date"),
        "outputs": run_info.get("outputs", []),
        "config_hash": config_hash(snap),
        "config": snap,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    return manifest
