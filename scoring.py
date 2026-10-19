"""
scoring.py
----------
The scoring engine: turns a table of per-fund metrics into one score and a rank.
Pure pandas, no network and no config import, so it is easy to test.

How a score is built
    1. Each metric is turned into a comparable score across the funds being ranked:
         zscore     (value - mean) / std            (0 when std == 0)
         percentile (average rank - 1) / (n - 1) * 100   (50 when only one fund has a value)
       Lower-is-better metrics (see LOWER_IS_BETTER) are sign-flipped first.
       max_drawdown is stored as a negative fraction (-0.30 = a 30% fall), so a SMALLER
       fall is already the higher number and needs no flip.
    2. The weighted average of those scores is the composite_score, using the missing-data
       policy:
         renormalize_available  average over the metrics the fund HAS (weights rescaled);
                                a fund whose measured weight is below `min_coverage` is
                                marked INSUFFICIENT_DATA and not ranked.
         average                a missing metric counts as an average score.
    3. Whatever the method, final_score_0_100 is also computed from percentile scores,
       with the same policy, and score_<metric> / contrib_<metric> columns show each
       metric's 0-100 score and its points inside that final score.
"""

import numpy as np
import pandas as pd

LOWER_IS_BETTER = {"downside_capture"}


def _active(weights):
    return {m: w for m, w in weights.items() if w and w > 0}


def _zscores(oriented: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(np.nan, index=oriented.index, columns=oriented.columns)
    for m in oriented.columns:
        v = oriented[m]
        mean, std = v.mean(), v.std()
        if v.notna().sum() < 2 or not np.isfinite(std) or std == 0:
            out[m] = v.where(v.isna(), 0.0)          # no spread -> no discriminating power
        else:
            out[m] = (v - mean) / std
    return out


def _percentiles(oriented: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(np.nan, index=oriented.index, columns=oriented.columns)
    for m in oriented.columns:
        v = oriented[m]
        n = int(v.notna().sum())
        if n == 0:
            continue
        if n == 1:
            out[m] = v.where(v.isna(), 50.0)
        else:
            out[m] = (v.rank(method="average") - 1) / (n - 1) * 100.0
    return out


def score_and_rank(df: pd.DataFrame, weights: dict, policy: str = "renormalize_available",
                   min_coverage: float = 0.7, method: str = "zscore",
                   min_group_size: int = 1) -> pd.DataFrame:
    """Returns a copy of df with rank, status, confidence, composite_score, final_score_0_100,
    score_coverage, score_missing and score_<m> / contrib_<m> columns, ranked funds first."""
    if policy not in ("renormalize_available", "average"):
        raise ValueError(f"unknown missing-data policy '{policy}'")
    if method not in ("zscore", "percentile"):
        raise ValueError(f"unknown scoring method '{method}'")
    if df.empty:
        return df.copy()

    act = _active(weights)
    if not act:
        raise ValueError("no metric has a weight above zero")
    scored = df.copy().reset_index(drop=True).drop(columns=["rank"], errors="ignore")
    for m in act:
        if m not in scored.columns:
            scored[m] = np.nan
    vals = scored[list(act)].apply(pd.to_numeric, errors="coerce")
    oriented = vals.copy()
    for m in LOWER_IS_BETTER & set(act):
        oriented[m] = -oriented[m]

    w = pd.Series(act, dtype=float)
    total_w = float(w.sum())
    measured = oriented.notna()
    measured_w = measured.mul(w, axis=1).sum(axis=1)
    coverage = measured_w / total_w
    scored["score_coverage"] = coverage
    scored["score_missing"] = measured.apply(lambda r: ", ".join(m for m in act if not r[m]), axis=1)

    Z, P = _zscores(oriented), _percentiles(oriented)
    primary = Z if method == "zscore" else P
    neutral_primary = 0.0 if method == "zscore" else 50.0

    def combine(S, neutral):
        if policy == "renormalize_available":
            num = S.mul(w, axis=1).sum(axis=1, skipna=True)
            return (num / measured_w).where(measured_w > 0)
        return S.fillna(neutral).mul(w, axis=1).sum(axis=1) / total_w

    composite = combine(primary, neutral_primary)
    final = combine(P, 50.0)
    eps = 1e-9
    insufficient = coverage + eps < min_coverage
    composite = composite.where(~insufficient)
    final = final.where(~insufficient)
    scored["composite_score"] = composite
    scored["final_score_0_100"] = final

    denom = measured_w if policy == "renormalize_available" else pd.Series(total_w, index=scored.index)
    for m in act:
        scored[f"score_{m}"] = P[m]
        contrib = (P[m].fillna(50.0 if policy == "average" else 0.0) * act[m]) / denom
        scored[f"contrib_{m}"] = contrib.where(~insufficient)

    scored["status"] = np.where(insufficient, "INSUFFICIENT_DATA", "RANKED")

    sort_key = scored["scheme_code"].astype(str) if "scheme_code" in scored.columns else pd.Series(scored.index.astype(str))
    scored["_k"] = sort_key.values
    scored["_unranked"] = scored["composite_score"].isna()
    scored = scored.sort_values(["_unranked", "composite_score", "_k"], ascending=[True, False, True],
                                kind="mergesort").reset_index(drop=True)
    n_ranked = int((~scored["_unranked"]).sum())
    ranks = pd.array([i + 1 if i < n_ranked else pd.NA for i in range(len(scored))], dtype="Int64")
    scored = scored.drop(columns=["_k", "_unranked"])
    scored.insert(0, "rank", ranks)
    scored["confidence"] = "OK" if n_ranked >= min_group_size else f"LOW (only {n_ranked} ranked, need {min_group_size}+)"
    return scored
