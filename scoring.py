"""
scoring.py
----------
Shared standardization used by BOTH the backward-looking composite score
(shortlist.score_and_rank) and the forward-looking tilt (forward_signals), so
the two are on exactly the same footing:

  - "zscore": robust z-score, (value - median) / (1.4826 * MAD), winsorized at
    +/- config.SCORE_WINSORIZE_Z. Falls back to mean/std if MAD is zero.
  - "percentile": percentile rank within the universe, centered at 0.
    Used automatically when the universe is smaller than
    config.SCORE_MIN_FUNDS_FOR_ZSCORE.

Standardization statistics always come from `universe` (the whole eligible
category), never from the handful of survivors being scored. A missing value
is scored neutrally (0 = category average).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config


def pct_rank(universe_values: pd.Series, values: pd.Series) -> pd.Series:
    """Percentile (0-1) of each of `values` within `universe_values`: the
    share of the universe at or below it. NaN stays NaN."""
    ref = np.sort(universe_values.dropna().astype(float).values)
    if len(ref) == 0:
        return pd.Series(np.nan, index=values.index)
    return values.astype(float).apply(
        lambda v: np.searchsorted(ref, v, side="right") / len(ref) if pd.notna(v) else np.nan)


def should_use_percentile(universe_size: int) -> bool:
    return (config.SCORING_METHOD.lower() == "percentile"
            or universe_size < config.SCORE_MIN_FUNDS_FOR_ZSCORE)


def standardize(universe_values: pd.Series, values: pd.Series,
                lower_is_better: bool = False, use_percentile: bool = False) -> pd.Series:
    """Standardizes `values` against `universe_values`; higher result = better.
    NaN -> 0.0 (neutral)."""
    u = universe_values.astype(float)
    s = values.astype(float)
    if lower_is_better:
        u, s = -u, -s

    if use_percentile:
        return (pct_rank(u, s) - 0.5).fillna(0.0)

    center = u.median()
    scale = 1.4826 * (u - center).abs().median()
    if pd.isna(scale) or scale == 0:
        center, scale = u.mean(), u.std()
    if pd.isna(scale) or scale == 0:
        return s * 0.0
    z = ((s - center) / scale).clip(-config.SCORE_WINSORIZE_Z, config.SCORE_WINSORIZE_Z)
    return z.fillna(0.0)


def weighted_score(df: pd.DataFrame, universe: pd.DataFrame, weights: dict,
                   lower_is_better: set, use_percentile: bool) -> pd.Series:
    """Weighted average of standardized metrics (weights are normalized to
    sum to 1 over the metrics supplied)."""
    total_w = sum(weights.values())
    total = pd.Series(0.0, index=df.index)
    for metric, w in weights.items():
        total += standardize(universe[metric], df[metric],
                             lower_is_better=metric in lower_is_better,
                             use_percentile=use_percentile) * (w / total_w)
    return total
