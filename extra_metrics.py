"""
extra_metrics.py
----------------
Two metrics from the older blueprint, computed only from NAV history and the benchmark
series already used by benchmark.py (nothing is estimated):

  downside_capture      How much of the benchmark's losses the fund took, in the months the
                        benchmark fell: mean(fund monthly return) / mean(benchmark monthly
                        return) over those months (arithmetic means). Below 1.00 (100%) = the
                        fund lost less than the benchmark. LOWER IS BETTER. Needs >= 6 down months.

  quartile_consistency  Share of rolling-return dates (month-ends, trailing-window CAGR) on which
                        the fund was in the top half (Q1 or Q2) of its peer group. Dates with
                        fewer than `min_peers` funds are skipped; needs >= 12 usable dates.
                        Also reports the share spent in the top quartile (Q1) alone.
                        Peer group = the funds being ranked in this run, so it is only as good
                        as that universe.
"""

import numpy as np
import pandas as pd

MIN_DOWN_MONTHS = 6
MIN_DATES = 12


def _month_end_returns(df: pd.DataFrame) -> pd.Series:
    s = df.set_index("date")["nav"].sort_index().resample("ME").last().dropna()
    return s.pct_change().dropna()


def downside_capture(fund_df: pd.DataFrame, bench_df: pd.DataFrame,
                     min_down_months: int = MIN_DOWN_MONTHS) -> float | None:
    if fund_df is None or bench_df is None or fund_df.empty or bench_df.empty:
        return None
    f, b = _month_end_returns(fund_df), _month_end_returns(bench_df)
    common = f.index.intersection(b.index)
    f, b = f[common], b[common]
    down = b < 0
    if int(down.sum()) < min_down_months:
        return None
    bench_mean = float(b[down].mean())
    if bench_mean == 0:
        return None
    return float(f[down].mean() / bench_mean)


def quartile_consistency(rolling_by_code: dict, min_peers: int = 8) -> dict:
    """rolling_by_code: {scheme_code: Series of trailing CAGR indexed by month-end}.
    Returns {scheme_code: {"quartile_consistency": share in top half or None,
                           "q1_share": share in top quartile or None, "windows": int}}."""
    out = {c: {"quartile_consistency": None, "q1_share": None, "windows": 0} for c in rolling_by_code}
    usable = {c: s for c, s in rolling_by_code.items() if s is not None and len(s)}
    if len(usable) < min_peers:
        return out
    table = pd.DataFrame(usable)
    n_valid = table.notna().sum(axis=1)
    table = table[n_valid >= min_peers]
    if table.empty:
        return out
    # fraction of peers that did better: 0.0 = best, close to 1.0 = worst
    ranks = table.rank(axis=1, ascending=False, method="average")
    n = table.notna().sum(axis=1)
    position = (ranks.sub(1, axis=0)).div((n - 1).replace(0, np.nan), axis=0)   # 0 best .. 1 worst
    top_half = (position <= 0.5).where(table.notna())
    top_quarter = (position <= 0.25).where(table.notna())
    for c in table.columns:
        k = int(table[c].notna().sum())
        out[c]["windows"] = k
        if k >= MIN_DATES:
            out[c]["quartile_consistency"] = float(top_half[c].dropna().mean())
            out[c]["q1_share"] = float(top_quarter[c].dropna().mean())
    return out
