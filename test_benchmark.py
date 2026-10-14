"""Offline tests for benchmark.py and its wiring into shortlist.py (synthetic NAVs, no network)."""
import math
import os
import sys
import tempfile
import types

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import benchmark as bm


def make_bench(start="2018-10-01", end="2026-10-09", seed=1):
    dates = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    nav = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, len(dates))))
    return pd.DataFrame({"date": dates, "nav": nav})


def derived(bench, drift_per_day, start=None):
    df = bench.copy()
    if start is not None:
        df = df[df["date"] >= start].reset_index(drop=True)
    df["nav"] = df["nav"] * np.exp(drift_per_day * np.arange(len(df)))
    return df


BENCH = make_bench()
OUT = derived(BENCH, +0.0002)     # beats benchmark everywhere
UNDER = derived(BENCH, -0.0002)   # lags benchmark everywhere
passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"ok  {name}")


# 1. category inference ------------------------------------------------------
check("large&mid before large/mid", bm.category_key("Equity Scheme - Large & Mid Cap Fund") == "large & mid cap")
check("small cap", bm.category_key("Equity Scheme - Small Cap Fund") == "small cap")
check("mid cap", bm.category_key("Equity Scheme - Mid Cap Fund") == "mid cap")
check("large cap", bm.category_key("Equity Scheme - Large Cap Fund") == "large cap")
check("elss", bm.category_key("Equity Scheme - ELSS") == "elss")
check("blank falls back to CLI category", bm.category_key("", "mid cap") == "mid cap")
check("blank, no fallback -> None", bm.category_key(None) is None)

# 2. excess return + rolling beat --------------------------------------------
res_out = bm.compute_benchmark_metrics(OUT, BENCH, 3.0, 3.0)
res_under = bm.compute_benchmark_metrics(UNDER, BENCH, 3.0, 3.0)
check("outperformer excess > 0", res_out["benchmark_excess_return"] > 0)
check("underperformer excess < 0", res_under["benchmark_excess_return"] < 0)
check("outperformer beats in 100% of windows", res_out["rolling_beat_benchmark_pct"] == 1.0)
check("underperformer beats in 0% of windows", res_under["rolling_beat_benchmark_pct"] == 0.0)
check("enough windows", res_out["benchmark_windows"] >= 12)

# exact value: fund = bench * exp(k*i) over the matched 3y window
f3, b3 = bm.matched_cagrs(OUT, BENCH, 3.0)
ratio = (1 + f3) / (1 + b3)
n_days = (OUT["date"] == OUT["date"].max()).values.nonzero()[0][0] - \
    (OUT["date"] <= OUT["date"].max() - pd.Timedelta(days=int(3 * 365.25))).values.nonzero()[0][-1]
expected_ratio = math.exp(0.0002 * n_days) ** (1 / 3.0)
check("excess matches analytic ratio", abs(ratio - expected_ratio) < 1e-9)
check("same fund vs itself -> excess 0", abs(bm.compute_benchmark_metrics(BENCH, BENCH, 3.0, 3.0)["benchmark_excess_return"]) < 1e-12)

# 3. insufficient history -> None, never a guess ------------------------------
short_fund = derived(BENCH, 0.0001, start="2025-01-01")
r = bm.compute_benchmark_metrics(short_fund, BENCH, 3.0, 3.0)
check("short fund: excess None", r["benchmark_excess_return"] is None)
check("short fund: rolling beat None", r["rolling_beat_benchmark_pct"] is None)
check("zero is not missing (underperformer pct == 0.0)", res_under["rolling_beat_benchmark_pct"] is not None)

# 4. stale benchmark -> None ---------------------------------------------------
stale = BENCH[BENCH["date"] <= "2026-08-01"]
r = bm.compute_benchmark_metrics(OUT, stale, 3.0, 3.0, max_staleness_days=10)
check("stale benchmark: excess None", r["benchmark_excess_return"] is None)
r2 = bm.compute_benchmark_metrics(OUT, stale, 3.0, 3.0, max_staleness_days=100000)
check("stale allowed when tolerance huge", r2["benchmark_excess_return"] is not None)

# 5. provider: CSV override ----------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    config.BENCHMARK_DIR = td
    csv = BENCH.assign(date=BENCH["date"].dt.strftime("%Y-%m-%d")).rename(columns={"nav": "tri"})
    csv.to_csv(os.path.join(td, "small_cap.csv"), index=False)
    csv.to_csv(os.path.join(td, "large_and_mid_cap.csv"), index=False)
    p = bm.BenchmarkProvider()
    b = p.get("small cap")
    check("csv override used", b is not None and b["source"] == "local TRI csv")
    check("csv rows loaded", len(b["df"]) == len(BENCH))
    check("large & mid csv filename", p.get("large & mid cap")["source"] == "local TRI csv")
    out = bm.metrics_for_fund(OUT, p, "Equity Scheme - Small Cap Fund", None)
    check("metrics_for_fund end-to-end", out["benchmark_excess_return"] > 0 and out["benchmark_name"] == "Nifty Smallcap 250 TRI")
    check("sectoral has no benchmark", bm.metrics_for_fund(OUT, p, "Equity Scheme - Sectoral/Thematic", None)["benchmark_excess_return"] is None)
    check("provider None -> full key set", set(bm.metrics_for_fund(OUT, None, "x", None)) == set(bm.EMPTY_BENCHMARK_METRICS))

# 6. provider: auto-discovery picks plain index fund with longest history -----
names = {
    100: "Aurora Nifty Midcap 150 Index Fund - Direct Plan - Growth",
    101: "Beta Nifty Midcap 150 Momentum 50 Index Fund - Direct Plan - Growth",
    102: "Gamma Nifty Midcap 150 Quality 50 Index Fund - Direct Plan - Growth",
    103: "Delta Nifty Midcap 150 Index Fund - Regular Plan - Growth",
    104: "Epsilon Nifty Midcap 150 Index Fund - Direct Plan - IDCW",
    105: "Zeta Nifty Mid Cap 150 Index Fund - Direct Plan - Growth Option",
    106: "Eta Nifty Midcap 150 ETF - Direct Plan - Growth",
}
fetched = []
fake_fund_universe = types.ModuleType("fund_universe")
fake_fund_universe.download_scheme_master = lambda force_refresh=False: [
    {"schemeCode": c, "schemeName": n} for c, n in names.items()]
fake_fund_universe.supported_categories = lambda: []
fake_fund_universe.find_candidates = lambda *a, **k: ("mid cap", [])
histories = {100: derived(BENCH, 0, start="2024-01-01"), 105: BENCH}


def fake_get_nav_history(code, force_refresh=False):
    fetched.append(int(code))
    return histories[int(code)]


fake_fetch = types.ModuleType("fetch_nav_data")
fake_fetch.get_nav_history = fake_get_nav_history
fake_fetch.get_scheme_meta = lambda code: {"scheme_name": "", "fund_house": "", "scheme_category": "Equity Scheme - Mid Cap Fund"}
sys.modules["fund_universe"] = fake_fund_universe
sys.modules["fetch_nav_data"] = fake_fetch

with tempfile.TemporaryDirectory() as td:
    config.BENCHMARK_DIR = td  # empty -> no csv override
    p = bm.BenchmarkProvider()
    b = p.get("mid cap")
    check("only plain direct-growth index funds considered", sorted(fetched) == [100, 105])
    check("longest-history proxy chosen", b["proxy_code"] == "105")
    check("describe() reports proxy", "Zeta" in p.describe()[0])
    check("provider caches", (p.get("mid cap") is b) and sorted(fetched) == [100, 105])
    config.BENCHMARKS_BACKUP = config.BENCHMARKS
    p2 = bm.BenchmarkProvider()
    check("category without keywords match -> None (no crash)", p2.get("small cap") is None)

# 7. shortlist wiring: scoring with benchmark columns + missing values --------
fake_metrics = types.ModuleType("metrics")
fake_metrics.compute_all_metrics = lambda *a, **k: {}
fake_report = types.ModuleType("report")
sys.modules["metrics"] = fake_metrics
import shortlist  # noqa: E402

rows = []
rng = np.random.default_rng(7)
for i in range(8):
    rows.append({
        "scheme_code": str(i), "scheme_name": f"F{i}",
        "cagr_1y": rng.uniform(.1, .3), "cagr_3y": rng.uniform(.1, .3), "cagr_5y": rng.uniform(.1, .3),
        "risk_return_ratio": rng.uniform(.5, 1.5), "sortino_ratio": rng.uniform(.5, 2),
        "rolling_positive_pct": rng.uniform(.6, 1), "sip_xirr": rng.uniform(.1, .3),
        "max_drawdown": -rng.uniform(.2, .4),
        "benchmark_excess_return": rng.uniform(-.03, .05), "rolling_beat_benchmark_pct": rng.uniform(0, 1),
    })
df = pd.DataFrame(rows)
df["portfolio_quality"] = np.nan  # no holdings files supplied: metric missing for every fund
df.loc[0,["benchmark_excess_return", "rolling_beat_benchmark_pct"]] = np.nan  # no benchmark for fund 0
ranked = shortlist.score_and_rank(df)
check("no NaN composite with missing benchmark", ranked["composite_score"].notna().all())
check("weights sum to 1", abs(sum(config.SCORE_WEIGHTS.values()) - 1.0) < 1e-9)

# a fund that is strictly better on benchmark metrics only should move up
base = df.copy()
base["benchmark_excess_return"] = 0.0
base["rolling_beat_benchmark_pct"] = 0.5
base.loc[3, "benchmark_excess_return"] = 0.2
base.loc[3, "rolling_beat_benchmark_pct"] = 1.0
base.loc[5, "benchmark_excess_return"] = -0.2
base.loc[5, "rolling_beat_benchmark_pct"] = 0.0
r2 = shortlist.score_and_rank(base)
pos = {row.scheme_code: row.rank for row in r2.itertuples()}
check("benchmark metrics influence rank (best up, worst down)", pos["3"] < pos["5"])

disp = shortlist.format_for_display(ranked)
check("display formats benchmark cols as %", str(disp.loc[0, "benchmark_excess_return"]).endswith("%") or disp.loc[0, "benchmark_excess_return"] == "N/A")

# excel formatting of new columns
import report as real_report  # noqa: E402  (the stub above is only in sys.modules for shortlist's import)
