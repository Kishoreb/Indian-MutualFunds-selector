"""Offline tests for the aligned ratio window in metrics.compute_all_metrics.   python test_metrics_window.py"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"ok  {name}")


def series(years, crash_years_ago=None, seed=1):
    """Business-day NAV; calm drift of ~15%/yr with ~1% monthly noise, plus (optionally) a violent
    stretch of months starting `crash_years_ago` years before the end."""
    end = pd.Timestamp("2026-10-16")
    idx = pd.bdate_range(end=end, periods=int(years * 252))
    rng = np.random.default_rng(seed)
    r = rng.normal(0.15 / 252, 0.01 / np.sqrt(21), len(idx))
    if crash_years_ago is not None:
        start = end - pd.Timedelta(days=int(crash_years_ago * 365.25))
        sel = (idx >= start) & (idx < start + pd.Timedelta(days=120))
        r[sel] = rng.normal(-0.002, 0.05, sel.sum())
    return pd.DataFrame({"date": idx, "nav": 100 * np.exp(np.cumsum(r))})


old_fund = series(8, crash_years_ago=6)       # a crash 6 years ago, then calm
young = series(8, crash_years_ago=None)

a = metrics.compute_all_metrics(old_fund, 0.065)
b = metrics.compute_all_metrics(old_fund, 0.065, align_ratio_window=False)
check("aligned run records a 3-year ratio window", a["ratio_window_years"] == 3.0)
check("old behaviour records no window (whole history)", b["ratio_window_years"] is None)
check("volatility column stays whole-history either way", a["volatility"] == b["volatility"])
check("downside_deviation column stays whole-history either way", a["downside_deviation"] == b["downside_deviation"])
check("same return leg in both modes", a["cagr_3y"] == b["cagr_3y"])
check("the crash outside the 3y window no longer drags the Sharpe-style ratio", a["risk_return_ratio"] > b["risk_return_ratio"] * 1.5)
check("... nor the Sortino ratio", a["sortino_ratio"] > b["sortino_ratio"] * 1.5)

# the aligned ratio equals the textbook formula on exactly the last 36 monthly returns
mr = metrics.calculate_monthly_returns(old_fund).iloc[-36:]
expected = (a["cagr_3y"] - 0.065) / float(mr.std() * np.sqrt(12))
check("aligned ratio = (CAGR3y - rf) / vol of the last 36 months", abs(a["risk_return_ratio"] - expected) < 1e-12)
dd = float(np.sqrt(np.mean(np.minimum(mr, 0) ** 2)) * np.sqrt(12))
check("aligned Sortino uses downside deviation of the last 36 months", abs(a["sortino_ratio"] - (a["cagr_3y"] - 0.065) / dd) < 1e-12)

# a fund with no crash anywhere: both modes agree closely (same period, same data type)
y1 = metrics.compute_all_metrics(young, 0.065)
y2 = metrics.compute_all_metrics(young, 0.065, align_ratio_window=False)
check("no crash -> the two modes are close", abs(y1["risk_return_ratio"] - y2["risk_return_ratio"]) < 0.35)

# short history: only 4 years -> 3y return exists, window is 3y; 2.5 years -> falls back to the 1y leg
short = series(2.5)
s = metrics.compute_all_metrics(short, 0.065)
check("under 3y of history the ratio uses the 1y return and a 1-year window", s["cagr_3y"] is None and s["ratio_window_years"] == 1.0)
mr1 = metrics.calculate_monthly_returns(short).iloc[-12:]
check("1y fallback ratio = (CAGR1y - rf) / vol of the last 12 months",
      abs(s["risk_return_ratio"] - (s["cagr_1y"] - 0.065) / float(mr1.std() * np.sqrt(12))) < 1e-12)

# 5y leg only when 3y is unavailable (cannot happen with a normal NAV series, so check the order of preference)
five = metrics.compute_all_metrics(series(6), 0.065)
check("with 6y of history the 3y return leg is used", five["ratio_window_years"] == 3.0)

# very little data: no crash, ratios simply missing
tiny = metrics.compute_all_metrics(series(0.3), 0.065)
check("under a year of data: ratios missing, no exception", tiny["risk_return_ratio"] is None and tiny["sortino_ratio"] is None)
check("ratio_window_years key is always present", "ratio_window_years" in tiny)

import config
check("1y CAGR and risk-return filters are off by default", config.MIN_CAGR_1Y is None and config.MIN_RISK_RETURN_RATIO is None)
check("other hard filters are unchanged", config.MIN_CAGR_3Y == 0.10 and config.MIN_CAGR_5Y == 0.10
      and config.MAX_VOLATILITY == 0.35 and config.MIN_HISTORY_YEARS == 5.0)
check("ratio window alignment is on by default", config.RATIO_ALIGN_WINDOW is True)
print(f"\nAll {passed} checks passed")
