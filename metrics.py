"""
metrics.py
----------
Pure calculation functions that turn a NAV history DataFrame
(columns: date, nav) into the metrics used for shortlisting:

    - CAGR over N years (1, 3, 4 ... configurable)
    - Annualized volatility (risk)
    - Risk-adjusted return ratio (Sharpe-style)
    - Max drawdown

All functions are defensive: if there isn't enough history to compute a
metric, they return None rather than raising, so a fund can still be
scored on whatever metrics ARE available.
"""

from datetime import timedelta

import numpy as np
import pandas as pd


def _nav_on_or_before(df: pd.DataFrame, target_date) -> float | None:
    """Finds the NAV on the closest available date on/before target_date."""
    subset = df[df["date"] <= target_date]
    if subset.empty:
        return None
    return float(subset.iloc[-1]["nav"])


def years_of_history(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    span = df["date"].max() - df["date"].min()
    return span.days / 365.25


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

    if years == 1:
        # Simple 1-year return (equivalent to CAGR for a 1-year period).
        return (end_nav / start_nav) - 1
    return (end_nav / start_nav) ** (1 / years) - 1


def calculate_monthly_returns(df: pd.DataFrame) -> pd.Series:
    """Resamples NAV to month-end and computes month-over-month returns."""
    s = df.set_index("date")["nav"].resample("ME").last().dropna()
    return s.pct_change().dropna()


def calculate_volatility(df: pd.DataFrame) -> float | None:
    """Annualized volatility, derived from the standard deviation of
    monthly returns (std * sqrt(12))."""
    monthly_returns = calculate_monthly_returns(df)
    if len(monthly_returns) < 6:
        return None
    return float(monthly_returns.std() * np.sqrt(12))


def calculate_max_drawdown(df: pd.DataFrame) -> float | None:
    """Largest peak-to-trough decline over the fund's history, as a
    negative fraction (e.g. -0.32 means a 32% drawdown)."""
    if df.empty:
        return None
    nav = df.set_index("date")["nav"]
    running_max = nav.cummax()
    drawdown = (nav - running_max) / running_max
    return float(drawdown.min())


def calculate_risk_return_ratio(cagr: float | None, volatility: float | None,
                                 risk_free_rate: float) -> float | None:
    """Sharpe-style ratio: (return - risk free rate) / volatility.
    Uses the 3-year CAGR by convention as the "return" input from the
    caller, but accepts whatever CAGR is passed in."""
    if cagr is None or volatility is None or volatility == 0:
        return None
    return (cagr - risk_free_rate) / volatility


# ---------------------------------------------------------------------------
# Downside deviation / Sortino ratio
# ---------------------------------------------------------------------------

def calculate_downside_deviation(monthly_returns: pd.Series, mar: float = 0.0) -> float | None:
    """Annualized downside deviation: like volatility, but only penalizes
    returns that fall below the minimum acceptable return (mar, default 0),
    ignoring upside swings entirely. sqrt(mean(min(r - mar, 0)^2)) * sqrt(12)."""
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
    Returns a Series of CAGR values indexed by the window's end date."""
    monthly_nav = df.set_index("date")["nav"].resample("ME").last().dropna()
    window_days = int(window_years * 365.25)

    values = {}
    for end_date, end_nav in monthly_nav.items():
        start_date = end_date - pd.Timedelta(days=window_days)
        prior = monthly_nav[monthly_nav.index <= start_date]
        if prior.empty:
            continue
        # Require the available start point to be reasonably close to the
        # target start date so short-history funds don't get spurious windows.
        if start_date - prior.index[-1] > pd.Timedelta(days=45):
            continue
        start_nav = prior.iloc[-1]
        if start_nav <= 0:
            continue
        cagr = (end_nav / start_nav) ** (1 / window_years) - 1
        values[end_date] = cagr

    return pd.Series(values, dtype=float)


def rolling_return_stats(df: pd.DataFrame, window_years: float = 3.0) -> dict:
    """Summarizes rolling returns into consistency metrics. Requires at
    least 12 rolling windows (roughly 1 extra year beyond window_years of
    history) to produce a meaningful stat, otherwise returns all None."""
    rolling = calculate_rolling_returns(df, window_years)
    if len(rolling) < 12:
        return {"rolling_avg": None, "rolling_min": None,
                "rolling_positive_pct": None, "rolling_std": None}

    return {
        "rolling_avg": float(rolling.mean()),
        "rolling_min": float(rolling.min()),
        "rolling_positive_pct": float((rolling > 0).mean()),
        "rolling_std": float(rolling.std()),
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
    total_units = 0.0
    cashflows = []
    for d in sip_dates:
        avail = nav_indexed[nav_indexed.index >= d]
        if avail.empty:
            continue
        nav_on_date = avail.iloc[0]
        actual_date = avail.index[0]
        units = monthly_amount / nav_on_date
        total_units += units
        cashflows.append((actual_date, -monthly_amount))

    if total_units == 0 or len(cashflows) < 6:
        return None

    final_nav = float(df.iloc[-1]["nav"])
    final_value = total_units * final_nav
    cashflows.append((end_date, final_value))

    return _xirr(cashflows)


def compute_all_metrics(df: pd.DataFrame, risk_free_rate: float,
                         sip_years: float = 3.0, sip_monthly_amount: float = 1000.0,
                         rolling_window_years: float = 3.0) -> dict:
    """Computes the full metrics dict for one fund's NAV history."""
    cagr_1y = calculate_cagr(df, 1)
    cagr_3y = calculate_cagr(df, 3)
    cagr_5y = calculate_cagr(df, 5)
    volatility = calculate_volatility(df)
    max_dd = calculate_max_drawdown(df)

    # Use 3-year CAGR (falling back to 5y, then 1y) as the "return" leg of
    # the risk-adjusted ratios, since it best balances recency and stability.
    return_for_ratio = cagr_3y if cagr_3y is not None else (cagr_5y if cagr_5y is not None else cagr_1y)
    risk_return_ratio = calculate_risk_return_ratio(return_for_ratio, volatility, risk_free_rate)

    monthly_returns = calculate_monthly_returns(df)
    downside_dev = calculate_downside_deviation(monthly_returns)
    sortino_ratio = calculate_sortino_ratio(return_for_ratio, downside_dev, risk_free_rate)

    rolling_stats = rolling_return_stats(df, window_years=rolling_window_years)
    sip_xirr = calculate_sip_xirr(df, years=sip_years, monthly_amount=sip_monthly_amount)

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
        "rolling_std": rolling_stats["rolling_std"],
        "sip_xirr": sip_xirr,
        "history_years": years_of_history(df),
    }
