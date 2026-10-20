"""
extra_metrics.py
----------------
Metrics from the older blueprint, computed only from NAV history and the benchmark
series already used by benchmark.py (nothing is estimated):

  downside_capture      How much of the benchmark's losses the fund took, in the months the
                        benchmark fell: mean(fund monthly return) / mean(benchmark monthly
                        return) over those months (arithmetic means). Below 1.00 (100%) = the
                        fund lost less than the benchmark. LOWER IS BETTER. Needs >= 6 down months.

  jensen_alpha, beta    Regression of the fund's monthly EXCESS returns (over the risk-free rate) on the
                        benchmark's, using the last `years` (default 3) years of month-end returns:
                            excess_fund = alpha_m + beta * excess_bench + error
                        beta  = cov(fund, bench) / var(bench)  (1.0 = moves with the benchmark;
                                above 1 = amplifies it; below 1 = dampens it).
                        jensen_alpha = alpha_m * 12, the annual return beyond what beta explains
                                (a fraction: 0.02 = +2 percentage points a year).
                        Needs >= `min_months` common months and a benchmark no staler than the fund.
                        The benchmark is usually an index-fund proxy that trails the true TRI by roughly
                        its expense ratio, which flatters alpha a little (see README).

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


EMPTY_ALPHA_BETA = {"jensen_alpha": None, "beta": None, "alpha_beta_months": 0}


def alpha_beta(fund_df: pd.DataFrame, bench_df: pd.DataFrame, risk_free_rate: float,
               years: float = 3.0, min_months: int = 24, max_staleness_days: int = 10) -> dict:
    """Beta and Jensen's alpha of the fund against the benchmark (see the module docstring).
    Always returns the three keys of EMPTY_ALPHA_BETA; the first two are None when not measurable."""
    out = dict(EMPTY_ALPHA_BETA)
    if fund_df is None or bench_df is None or fund_df.empty or bench_df.empty:
        return out
    if (fund_df["date"].max() - bench_df["date"].max()).days > max_staleness_days:
        return out                                   # benchmark lags the fund: do not compare mismatched months
    f, b = _month_end_returns(fund_df), _month_end_returns(bench_df)
    common = f.index.intersection(b.index)
    n = int(round(years * 12))
    common = common[-n:]
    if len(common) < min_months:
        return out
    rf_m = (1.0 + risk_free_rate) ** (1.0 / 12.0) - 1.0
    fe, be = f[common] - rf_m, b[common] - rf_m
    var_b = float(be.var(ddof=1))
    if not np.isfinite(var_b) or var_b <= 0:
        return out
    beta = float(np.cov(fe.values, be.values, ddof=1)[0, 1] / var_b)
    alpha_m = float(fe.mean() - beta * be.mean())
    out.update(jensen_alpha=alpha_m * 12.0, beta=beta, alpha_beta_months=int(len(common)))
    return out


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
