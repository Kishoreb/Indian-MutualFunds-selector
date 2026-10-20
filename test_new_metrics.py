"""Tests: 3-year drawdown window, alpha/beta, and the 3y/5y rolling-return option. Run: python test_new_metrics.py"""
import sys

import numpy as np
import pandas as pd

import config
import extra_metrics
import metrics
import shortlist

FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def frame(values, end="2026-09-30", freq="D"):
    idx = pd.date_range(end=end, periods=len(values), freq=freq)
    return pd.DataFrame({"date": idx, "nav": values})


# ---- drawdown window -------------------------------------------------------------------------
# 6 years daily: crash of 50% early (years 1-2), then a 10% dip in the last 3 years
n = int(6 * 365.25)
vals = np.ones(n) * 100.0
vals[300:400] = np.linspace(100, 50, 100)
vals[400:] = np.linspace(50, 100, n - 400)
late = n - 400
vals[n - 500:n - 450] = vals[n - 500] * np.linspace(1, 0.9, 50)
vals[n - 450:] = vals[n - 450] * np.linspace(1, 1.2, 450)
df = frame(vals)
whole = metrics.calculate_max_drawdown(df)
w3 = metrics.calculate_max_drawdown(df, window_years=3)
check("whole-history drawdown sees the early crash", whole < -0.45, str(whole))
check("3-year window ignores the early crash", w3 > -0.15 and w3 < -0.05, str(w3))
check("fund younger than the window -> None, not a guess", metrics.calculate_max_drawdown(frame(vals[-700:]), 3) is None)
m = metrics.compute_all_metrics(df, 0.065, drawdown_window_years=3)
check("compute_all_metrics uses the window", abs(m["max_drawdown"] - w3) < 1e-12)
check("whole-history figure kept as max_drawdown_all", abs(m["max_drawdown_all"] - whole) < 1e-12)
check("config default is 3 years", config.DRAWDOWN_WINDOW_YEARS == 3.0)

# ---- alpha / beta against a known regression ------------------------------------------------------
rng = np.random.default_rng(7)
months = pd.date_range("2020-01-31", periods=60, freq="ME")
rb = rng.normal(0.01, 0.04, 60)
rf_m = (1.065) ** (1 / 12) - 1
true_beta, true_alpha_m = 1.3, 0.002
rf_ = (rb - rf_m) * true_beta + true_alpha_m + rf_m          # exact linear relation, no noise
bnav = 100 * np.cumprod(1 + rb)
fnav = 100 * np.cumprod(1 + rf_)
bdf = pd.DataFrame({"date": months, "nav": bnav})
fdf = pd.DataFrame({"date": months, "nav": fnav})
r = extra_metrics.alpha_beta(fdf, bdf, 0.065)
check("beta recovered", abs(r["beta"] - true_beta) < 1e-6, str(r))
check("alpha annualised (x12)", abs(r["jensen_alpha"] - true_alpha_m * 12) < 1e-6, str(r))
check("uses the last 36 months", r["alpha_beta_months"] == 36)
short = extra_metrics.alpha_beta(fdf.tail(20), bdf.tail(20), 0.065)
check("under 24 common months -> missing", short["beta"] is None and short["jensen_alpha"] is None)
stale_b = bdf[bdf["date"] <= months[-3]]
check("benchmark lagging the fund -> missing", extra_metrics.alpha_beta(fdf, stale_b, 0.065)["beta"] is None)
check("no benchmark -> missing", extra_metrics.alpha_beta(fdf, None, 0.065)["beta"] is None)
flat = bdf.assign(nav=100.0)
check("flat benchmark (zero variance) -> missing", extra_metrics.alpha_beta(fdf, flat, 0.065)["beta"] is None)
import scoring
check("beta scored lower-is-better", "beta" in scoring.LOWER_IS_BETTER)
import weights_loader
check("alpha and beta are known metrics", {"jensen_alpha", "beta"} <= set(weights_loader.KNOWN_METRICS))
check("alpha and beta default to weight 0", config.SCORE_WEIGHTS["jensen_alpha"] == 0 and config.SCORE_WEIGHTS["beta"] == 0)

# ---- rolling window option -------------------------------------------------------------------------------
check("default rolling window is 3 years", config.ROLLING_WINDOW_YEARS == 3.0)
check("--rolling-years 5 accepted", shortlist.set_rolling_years(5) is None and config.ROLLING_WINDOW_YEARS == 5.0)
check("--rolling-years out of range rejected", "between 1 and 10" in shortlist.set_rolling_years(0.5))
check("--rolling-years None leaves it", shortlist.set_rolling_years(None) is None and config.ROLLING_WINDOW_YEARS == 5.0)
config.ROLLING_WINDOW_YEARS = 3.0
g = np.exp(np.cumsum(np.random.default_rng(1).normal(0.0004, 0.01, int(7 * 365.25))))
d7 = frame(100 * g)
s3 = metrics.rolling_return_stats(d7, 3.0)
s5 = metrics.rolling_return_stats(d7, 5.0)
check("3y windows measurable on 7 years", s3["rolling_positive_pct"] is not None)
check("5y windows measurable on 7 years", s5["rolling_positive_pct"] is not None)
d5 = frame(100 * g[-int(5.5 * 365.25):])
check("5y windows NOT measured with 5.5 years (needs 12 windows)", metrics.rolling_return_stats(d5, 5.0)["rolling_positive_pct"] is None)
m5 = metrics.compute_all_metrics(d7, 0.065, rolling_window_years=5.0)
check("compute_all_metrics honours the 5y window", m5["rolling_positive_pct"] == s5["rolling_positive_pct"])

print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
