"""
metrics.py
----------
Pure calculation functions that turn a NAV history DataFrame
(columns: date, nav) into the metrics used for shortlisting:

    - CAGR over N years (1, 3, 5 ... configurable)
    - Annualized volatility, downside deviation, max drawdown
    - Risk-adjusted ratios (Sharpe-style and Sortino)
    - Rolling-return consistency
    - SIP XIRR
    - Benchmark-relative metrics (beta, alpha, tracking error, information
      ratio, up/down capture, excess CAGR, rolling beat %)
    - Data-quality diagnostics (last NAV date, suspicious daily jumps)

COMMON WINDOW: the risk metrics, the return leg of the Sharpe/Sortino
ratios, the rolling stats and the benchmark-relative metrics are all
computed over the same trailing `risk_window_years` window for every fund,
so a fund isn't penalized for having lived through more market cycles than
another. A fund without enough history gets None for those metrics.

All functions are defensive: if there isn't enough history to compute a
metric, they return None rather than raising, so a fund can still be
scored on whatever metrics ARE available.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

BENCH_KEYS = ["beta", "alpha", "tracking_error", "information_ratio",
              "up_capture", "down_capture", "excess_cagr", "rolling_beat_pct",
              "bench_months"]


def _nav_on_or_before(df: pd.DataFrame, target_date) -> float | None:
    """Finds the NAV on the closest available date on/before target_date.
    Binary search (O(log n)); assumes df is sorted by date ascending, which
    both the downloader and the cache loader guarantee."""
    dates = df["date"].values
    pos = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(target_date)), side="right")) - 1
    if pos < 0:
        return None
    return float(df["nav"].iloc[pos])


def years_of_history(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    span = df["date"].max() - df["date"].min()
    return span.days / 365.25


def _window_start(df: pd.DataFrame, years: float) -> pd.Timestamp:
    return df["date"].max() - pd.Timedelta(days=int(years * 365.25))


def has_window_coverage(df: pd.DataFrame, years: float, tol_days: int = 45) -> bool:
    """True if the NAV history reaches back (within tol_days) to the start
    of the trailing `years` window."""
    if df.empty:
        return False
    return df["date"].min() <= _window_start(df, years) + pd.Timedelta(days=tol_days)


def calculate_cagr(df: pd.DataFrame, years: float) -> float | None:
    """CAGR over the trailing `years` period, computed from the latest NAV
    back to the NAV `years` ago. Returns None if not enough history."""
    if df.empty:
        return None

    end_date = df["date"].max()
    start_date = end_date - timedelta(days=int(years * 365.25))

    end_nav = float(df.iloc[-1]["nav"])
    start_nav = _nav_on_or_before(df, start_date)

    if start_nav is None or start_nav <= 0:
        return None
    # Require the fund to actually have history stretching back close to
    # the requested start date, otherwise the CAGR would be misleading.
    if df["date"].min() > start_date + timedelta(days=30):
        return None

    return (end_nav / start_nav) ** (1 / years) - 1


def calculate_monthly_returns(df: pd.DataFrame) -> pd.Series:
    """Resamples NAV to month-end and computes month-over-month returns."""
    s = df.set_index("date")["nav"].resample("ME").last().dropna()
    return s.pct_change().dropna()


def window_monthly_returns(df: pd.DataFrame, window_years: float | None = None) -> pd.Series:
    """Monthly returns restricted to the trailing `window_years`. Returns an
    EMPTY series if the fund doesn't have history covering the window (so
    every fund is measured on the same footing or not at all)."""
    r = calculate_monthly_returns(df)
    if window_years is None:
        return r
    if not has_window_coverage(df, window_years):
        return r.iloc[0:0]
    return r[r.index > _window_start(df, window_years)]


def calculate_volatility(df: pd.DataFrame, window_years: float | None = None) -> float | None:
    """Annualized volatility, derived from the standard deviation of
    monthly returns (std * sqrt(12)) over the trailing window."""
    monthly_returns = window_monthly_returns(df, window_years)
    if len(monthly_returns) < 6:
        return None
    return float(monthly_returns.std() * np.sqrt(12))


def calculate_max_drawdown(df: pd.DataFrame, window_years: float | None = None) -> float | None:
    """Largest peak-to-trough decline within the trailing window, as a
    NEGATIVE fraction (e.g. -0.32 means a 32% drawdown). Closer to zero is
    better."""
    if df.empty:
        return None
    if window_years is not None:
        if not has_window_coverage(df, window_years):
            return None
        df = df[df["date"] >= _window_start(df, window_years)]
        if df.empty:
            return None
    nav = df.set_index("date")["nav"]
    running_max = nav.cummax()
    drawdown = (nav - running_max) / running_max
    return float(drawdown.min())


def calculate_risk_return_ratio(cagr: float | None, volatility: float | None,
                                 risk_free_rate: float) -> float | None:
    """Sharpe-style ratio: (return - risk free rate) / volatility.
    The caller passes the CAGR measured over the SAME window as the
    volatility."""
    if cagr is None or volatility is None or volatility == 0:
        return None
    return (cagr - risk_free_rate) / volatility


# ---------------------------------------------------------------------------
# Downside deviation / Sortino ratio
# ---------------------------------------------------------------------------

def monthly_rate(annual_rate: float) -> float:
    """Converts an annualized rate to its equivalent monthly rate."""
    return (1 + annual_rate) ** (1 / 12) - 1


def calculate_downside_deviation(monthly_returns: pd.Series, mar: float = 0.0) -> float | None:
    """Annualized downside deviation: like volatility, but only penalizes
    returns that fall below the minimum acceptable return `mar` (a MONTHLY
    rate), ignoring upside swings entirely.
    sqrt(mean(min(r - mar, 0)^2)) * sqrt(12).

    For a Sortino ratio whose numerator subtracts the risk-free rate, `mar`
    should be the monthly risk-free rate so numerator and denominator use
    the same hurdle."""
    if len(monthly_returns) < 6:
        return None
    shortfalls = np.minimum(monthly_returns - mar, 0)
    return float(np.sqrt(np.mean(shortfalls ** 2)) * np.sqrt(12))


def calculate_sortino_ratio(cagr: float | None, downside_deviation: float | None,
                             risk_free_rate: float) -> float | None:
    """Like the Sharpe-style risk_return_ratio, but divides by downside
    deviation instead of total volatility, so only "bad" risk is penalized."""
    if cagr is None or downside_deviation is None or downside_deviation == 0:
        return None
    return (cagr - risk_free_rate) / downside_deviation


# ---------------------------------------------------------------------------
# Rolling returns (consistency)
# ---------------------------------------------------------------------------

def calculate_rolling_returns(df: pd.DataFrame, window_years: float = 3.0) -> pd.Series:
    """Computes trailing CAGR at every month-end across the fund's history
    (not just as of today), so you can see how the fund performed across
    many different entry points rather than one lucky/unlucky snapshot.
    Returns a Series of CAGR values indexed by the window's end date.

    Note: consecutive monthly windows overlap almost completely, so these
    values are strongly autocorrelated."""
    monthly_nav = df.set_index("date")["nav"].resample("ME").last().dropna()
    if monthly_nav.empty:
        return pd.Series(dtype=float)
    window_days = int(window_years * 365.25)

    idx = monthly_nav.index
    navs = monthly_nav.values.astype(float)
    start_dates = idx - pd.Timedelta(days=window_days)
    # For each month-end, the last month-end on/before its window start.
    pos = idx.searchsorted(start_dates, side="right") - 1
    valid = pos >= 0
    safe_pos = np.where(valid, pos, 0)
    # Require the available start point to be reasonably close to the target
    # start date so short-history funds don't get spurious windows.
    gap_ok = (start_dates - idx[safe_pos]) <= pd.Timedelta(days=45)
    start_nav = navs[safe_pos]
    ok = valid & gap_ok & (start_nav > 0)

    cagr = np.full(len(navs), np.nan)
    cagr[ok] = (navs[ok] / start_nav[ok]) ** (1 / window_years) - 1
    return pd.Series(cagr, index=idx, dtype=float).dropna()


def _restrict_to_window(series: pd.Series, df: pd.DataFrame, within_years: float | None) -> pd.Series:
    """Keeps only rolling windows that END inside the trailing common window."""
    if within_years is None:
        return series
    return series[series.index > _window_start(df, within_years)]


def rolling_return_stats(df: pd.DataFrame, window_years: float = 3.0,
                         within_years: float | None = None, min_windows: int = 12,
                         hurdle: float = 0.12) -> dict:
    """Summarizes rolling returns into consistency metrics, using only the
    rolling windows that END within the trailing `within_years` (so all funds
    are judged over the same calendar period). Requires at least
    `min_windows` windows, otherwise returns all None."""
    empty = {"rolling_avg": None, "rolling_min": None, "rolling_positive_pct": None,
             "rolling_above_hurdle_pct": None, "rolling_std": None, "rolling_windows": 0}
    if within_years is not None and not has_window_coverage(df, within_years):
        return empty
    rolling = _restrict_to_window(calculate_rolling_returns(df, window_years), df, within_years)
    if len(rolling) < min_windows:
        return {**empty, "rolling_windows": int(len(rolling))}

    return {
        "rolling_avg": float(rolling.mean()),
        "rolling_min": float(rolling.min()),
        "rolling_positive_pct": float((rolling > 0).mean()),
        "rolling_above_hurdle_pct": float((rolling > hurdle).mean()),
        "rolling_std": float(rolling.std()),
        "rolling_windows": int(len(rolling)),
    }


# ---------------------------------------------------------------------------
# SIP XIRR
# ---------------------------------------------------------------------------

def _xirr(cashflows: list[tuple[pd.Timestamp, float]], guess: float = 0.15) -> float | None:
    """Solves for the annualized internal rate of return of a series of
    dated cashflows via Newton-Raphson, falling back to bisection if it
    doesn't converge. cashflows: list of (date, amount) -- outflows
    (investments) negative, inflows (redemption) positive."""
    if len(cashflows) < 2:
        return None

    t0 = cashflows[0][0]
    days = np.array([(d - t0).days / 365.0 for d, _ in cashflows])
    amounts = np.array([a for _, a in cashflows])

    def npv(rate):
        return np.sum(amounts / (1 + rate) ** days)

    def dnpv(rate):
        return np.sum(-days * amounts / (1 + rate) ** (days + 1))

    rate = guess
    for _ in range(100):
        f, fprime = npv(rate), dnpv(rate)
        if fprime == 0:
            break
        new_rate = rate - f / fprime
        if not np.isfinite(new_rate) or new_rate <= -0.9999:
            break
        if abs(new_rate - rate) < 1e-6:
            return float(new_rate)
        rate = new_rate

    # Newton-Raphson didn't converge cleanly -- fall back to bisection over
    # a wide, sane range of annualized returns.
    lo, hi = -0.9, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if np.isnan(f_lo) or np.isnan(f_hi) or f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-6:
            return float(mid)
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return float((lo + hi) / 2)


def calculate_sip_xirr(df: pd.DataFrame, years: float, monthly_amount: float = 1000.0) -> float | None:
    """Simulates a fixed monthly SIP over the trailing `years` period and
    returns the annualized XIRR an investor would actually have earned --
    which differs from lumpsum CAGR because it accounts for money going in
    at many different NAV levels, not just the start and end."""
    if df.empty:
        return None

    end_date = df["date"].max()
    start_date = end_date - pd.Timedelta(days=int(years * 365.25))
    if df["date"].min() > start_date + pd.Timedelta(days=45):
        return None  # not enough history for this SIP window

    sip_dates = pd.date_range(start=start_date, end=end_date, freq="MS")
    if len(sip_dates) < 6:
        return None

    nav_indexed = df.set_index("date")["nav"].sort_index()
    idx = nav_indexed.index
    total_units = 0.0
    cashflows = []
    for d in sip_dates:
        pos = idx.searchsorted(d, side="left")  # first NAV date >= d
        if pos >= len(idx):
            continue
        nav_on_date = nav_indexed.iloc[pos]
        units = monthly_amount / nav_on_date
        total_units += units
        cashflows.append((idx[pos], -monthly_amount))

    if total_units == 0 or len(cashflows) < 6:
        return None

    final_nav = float(df.iloc[-1]["nav"])
    final_value = total_units * final_nav
    cashflows.append((end_date, final_value))

    return _xirr(cashflows)


# ---------------------------------------------------------------------------
# Data-quality diagnostics
# ---------------------------------------------------------------------------

def detect_nav_anomalies(df: pd.DataFrame, threshold: float = 0.20) -> tuple[int, float | None]:
    """Counts day-over-day NAV moves larger than `threshold` (absolute).
    Real diversified equity funds almost never move 20% in a day, so such
    jumps usually mean a data error, an unadjusted unit split/merger, or a
    scheme restructure. Returns (count, largest absolute daily move)."""
    if len(df) < 2:
        return 0, None
    moves = df["nav"].pct_change().abs().dropna()
    if moves.empty:
        return 0, None
    return int((moves > threshold).sum()), float(moves.max())


# ---------------------------------------------------------------------------
# Benchmark-relative metrics
# ---------------------------------------------------------------------------

def _geo_mean(returns: pd.Series) -> float | None:
    if len(returns) == 0:
        return None
    return float(np.prod(1 + returns.values) ** (1 / len(returns)) - 1)


def calculate_benchmark_stats(fund_df: pd.DataFrame, bench_df: pd.DataFrame,
                              risk_free_rate: float, window_years: float,
                              rolling_window_years: float = 3.0,
                              min_coverage: float = 0.9,
                              min_rolling_windows: int = 12) -> dict:
    """Compares a fund to a benchmark NAV series over the common trailing
    window, using aligned month-end returns.

        beta               regression slope of fund excess return on benchmark excess return
        alpha              annualized Jensen's alpha (monthly intercept x 12)
        tracking_error     annualized std of (fund - benchmark) monthly returns
        information_ratio  annualized mean active return / tracking error
        up_capture         geometric fund return / geometric benchmark return, benchmark-up months
        down_capture       same for benchmark-down months (LOWER is better)
        excess_cagr        fund CAGR minus benchmark CAGR over the window
        rolling_beat_pct   share of rolling windows (ending in the window) where fund CAGR > benchmark CAGR
        bench_months       number of aligned months actually used

    Returns all-None (bench_months still reported) if the aligned history
    is shorter than `min_coverage` of the window."""
    out = {k: None for k in BENCH_KEYS}
    f = window_monthly_returns(fund_df, window_years)
    b = calculate_monthly_returns(bench_df)
    if f.empty or b.empty:
        out["bench_months"] = 0
        return out

    joined = pd.concat([f.rename("f"), b.rename("b")], axis=1, join="inner").dropna()
    out["bench_months"] = int(len(joined))
    needed = max(24, int(round(window_years * 12 * min_coverage)))
    if len(joined) < needed:
        return out

    rf_m = monthly_rate(risk_free_rate)
    ex_f, ex_b = joined["f"] - rf_m, joined["b"] - rf_m
    var_b = ex_b.var()
    if not np.isfinite(var_b) or var_b == 0:
        return out

    beta = ex_f.cov(ex_b) / var_b
    out["beta"] = float(beta)
    out["alpha"] = float((ex_f.mean() - beta * ex_b.mean()) * 12)

    active = joined["f"] - joined["b"]
    te = active.std() * np.sqrt(12)
    out["tracking_error"] = float(te)
    out["information_ratio"] = float(active.mean() * 12 / te) if te and te > 1e-9 else None

    up, down = joined[joined["b"] > 0], joined[joined["b"] < 0]
    if len(up) >= 6:
        gb = _geo_mean(up["b"])
        gf = _geo_mean(up["f"])
        out["up_capture"] = float(gf / gb) if gb and abs(gb) > 1e-9 else None
    if len(down) >= 6:
        gb = _geo_mean(down["b"])
        gf = _geo_mean(down["f"])
        out["down_capture"] = float(gf / gb) if gb and abs(gb) > 1e-9 else None

    n = len(joined)
    cagr_f = float(np.prod(1 + joined["f"].values) ** (12 / n) - 1)
    cagr_b = float(np.prod(1 + joined["b"].values) ** (12 / n) - 1)
    out["excess_cagr"] = cagr_f - cagr_b

    roll_f = _restrict_to_window(calculate_rolling_returns(fund_df, rolling_window_years), fund_df, window_years)
    roll_b = calculate_rolling_returns(bench_df, rolling_window_years)
    both = pd.concat([roll_f.rename("f"), roll_b.rename("b")], axis=1, join="inner").dropna()
    if len(both) >= min_rolling_windows:
        out["rolling_beat_pct"] = float((both["f"] > both["b"]).mean())

    return out


# ---------------------------------------------------------------------------
# Everything for one fund
# ---------------------------------------------------------------------------

def compute_all_metrics(df: pd.DataFrame, risk_free_rate: float,
                         sip_years: float = 3.0, sip_monthly_amount: float = 1000.0,
                         rolling_window_years: float = 3.0,
                         risk_window_years: float = 5.0,
                         nav_jump_threshold: float = 0.20,
                         rolling_min_windows: int = 12,
                         rolling_hurdle: float = 0.12) -> dict:
    """Computes the full (benchmark-independent) metrics dict for one fund's
    NAV history. Risk metrics, the Sharpe/Sortino return leg and rolling
    stats are all measured over the trailing `risk_window_years`."""
    df = df.sort_values("date").reset_index(drop=True)  # lookups below rely on date order

    cagr_1y = calculate_cagr(df, 1)
    cagr_3y = calculate_cagr(df, 3)
    cagr_5y = calculate_cagr(df, 5)

    volatility = calculate_volatility(df, risk_window_years)
    max_dd = calculate_max_drawdown(df, risk_window_years)

    # Return leg of the ratios is measured over the SAME window as the risk
    # leg (previously 3y CAGR was divided by full-history volatility).
    cagr_window = calculate_cagr(df, risk_window_years)
    risk_return_ratio = calculate_risk_return_ratio(cagr_window, volatility, risk_free_rate)

    monthly_window = window_monthly_returns(df, risk_window_years)
    # MAR = monthly risk-free rate so Sortino's numerator and denominator
    # share the same hurdle.
    downside_dev = calculate_downside_deviation(monthly_window, mar=monthly_rate(risk_free_rate))
    sortino_ratio = calculate_sortino_ratio(cagr_window, downside_dev, risk_free_rate)

    rolling_stats = rolling_return_stats(
        df, window_years=rolling_window_years, within_years=risk_window_years,
        min_windows=rolling_min_windows, hurdle=rolling_hurdle)
    sip_xirr = calculate_sip_xirr(df, years=sip_years, monthly_amount=sip_monthly_amount)

    n_anom, max_move = detect_nav_anomalies(df, nav_jump_threshold)

    return {
        "cagr_1y": cagr_1y,
        "cagr_3y": cagr_3y,
        "cagr_5y": cagr_5y,
        "volatility": volatility,
        "max_drawdown": max_dd,
        "risk_return_ratio": risk_return_ratio,
        "downside_deviation": downside_dev,
        "sortino_ratio": sortino_ratio,
        "rolling_avg": rolling_stats["rolling_avg"],
        "rolling_min": rolling_stats["rolling_min"],
        "rolling_positive_pct": rolling_stats["rolling_positive_pct"],
        "rolling_above_hurdle_pct": rolling_stats["rolling_above_hurdle_pct"],
        "rolling_std": rolling_stats["rolling_std"],
        "rolling_windows": rolling_stats["rolling_windows"],
        "sip_xirr": sip_xirr,
        "history_years": years_of_history(df),
        "last_nav_date": df["date"].max().strftime("%Y-%m-%d") if not df.empty else None,
        "nav_anomalies": n_anom,
        "max_daily_move": max_move,
    }
