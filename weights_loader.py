"""
weights_loader.py
-----------------
Reads and validates weights.ini (score weights + scoring policy).

Nothing is ever silently replaced: a missing file, a missing or unknown metric,
a non-numeric or negative weight, or a total other than 100 raises WeightsError
with a message saying what is wrong.
"""

import configparser
import os

KNOWN_METRICS = [
    "cagr_1y", "cagr_3y", "cagr_5y", "risk_return_ratio", "sortino_ratio",
    "rolling_positive_pct", "sip_xirr", "max_drawdown", "benchmark_excess_return",
    "rolling_beat_benchmark_pct", "portfolio_quality",
    "downside_capture", "quartile_consistency",
]
POLICIES = ("renormalize_available", "average")
METHODS = ("zscore", "percentile")
TOLERANCE = 1e-6


class WeightsError(ValueError):
    pass


def load(path: str) -> dict:
    """Returns {version, policy, min_coverage (fraction), method, min_group_size,
    weights (fractions summing to 1.0, every known metric present), weights_percent, path}."""
    if not os.path.exists(path):
        raise WeightsError(f"Weights file not found: {path}")
    cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"), interpolation=None)
    cp.optionxform = str  # keep metric names exactly as written
    try:
        cp.read(path, encoding="utf-8")
    except configparser.Error as exc:
        raise WeightsError(f"{path}: cannot be parsed ({exc})")
    for section in ("meta", "weights_percent"):
        if section not in cp:
            raise WeightsError(f"{path}: missing [{section}] section")

    meta = cp["meta"]

    def need(key):
        if key not in meta:
            raise WeightsError(f"{path}: [meta] is missing '{key}'")
        return meta[key].strip()

    def number(text, label, minimum=None, maximum=None):
        try:
            v = float(text)
        except ValueError:
            raise WeightsError(f"{path}: {label} must be a number, got '{text}'")
        if v != v or v in (float("inf"), float("-inf")):
            raise WeightsError(f"{path}: {label} must be finite, got '{text}'")
        if minimum is not None and v < minimum or maximum is not None and v > maximum:
            raise WeightsError(f"{path}: {label} must be between {minimum} and {maximum}, got {v}")
        return v

    version = need("version")
    policy = need("missing_data_policy")
    if policy not in POLICIES:
        raise WeightsError(f"{path}: missing_data_policy must be one of {POLICIES}, got '{policy}'")
    method = need("scoring_method")
    if method not in METHODS:
        raise WeightsError(f"{path}: scoring_method must be one of {METHODS}, got '{method}'")
    min_cov = number(need("minimum_coverage_percent"), "minimum_coverage_percent", 0, 100) / 100.0
    group = int(number(need("min_group_size"), "min_group_size", 1))

    raw = dict(cp["weights_percent"])
    unknown = [k for k in raw if k not in KNOWN_METRICS]
    if unknown:
        raise WeightsError(f"{path}: unknown metric(s) in [weights_percent]: {', '.join(unknown)}. "
                           f"Known: {', '.join(KNOWN_METRICS)}")
    missing = [k for k in KNOWN_METRICS if k not in raw]
    if missing:
        raise WeightsError(f"{path}: [weights_percent] is missing: {', '.join(missing)} "
                           f"(list every metric; use 0 to switch one off)")
    pct = {k: number(v.strip(), f"weight '{k}'", 0) for k, v in raw.items()}
    total = sum(pct.values())
    if abs(total - 100.0) > 0.01:
        raise WeightsError(f"{path}: weights add up to {total:g}, not 100")
    return {"version": version, "policy": policy, "min_coverage": min_cov, "method": method,
            "min_group_size": group, "weights_percent": {k: pct[k] for k in KNOWN_METRICS},
            "weights": {k: pct[k] / total for k in KNOWN_METRICS}, "path": os.path.abspath(path)}
