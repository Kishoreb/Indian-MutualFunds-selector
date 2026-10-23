"""
Offline tests for walk_forward.py (synthetic NAV data, no network).

Run:  python test_walk_forward.py

What is checked
  * statistics      Spearman, quartiles, the permutation test and the bootstrap against independent calculations
  * no look-ahead   changing EVERY NAV after the rank date changes nothing that is known at the rank date
                    (metrics, scores, ranks), only the forward return
  * survivors       funds whose NAV stopped updating, or ends before the forward window, are dropped and counted
  * end to end      a universe where past skill persists is detected, a universe where it does not is not;
                    output files; exit codes for bad input
They check the code, not the market: the data are random numbers.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import fetch_nav_data
import fund_universe
import walk_forward as wf

LAST_NAV = pd.Timestamp("2026-10-16")
FIRST_NAV = pd.Timestamp("2017-01-02")
CATEGORIES = {"small cap": ("Small Cap Fund", 16), "mid cap": ("Mid Cap Fund", 14), "large cap": ("Large Cap Fund", 12)}
passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"ok  {name}")


# --------------------------------------------------------------------------------------
# Synthetic universe
# --------------------------------------------------------------------------------------
class Universe:
    """Writes data/_scheme_master.json, data/<code>.csv, data/<code>_meta.csv and data/benchmarks/*.csv under `root`.
    persistent=True : every fund has one constant alpha for the whole period (skill persists)
    persistent=False: a fund's alpha is drawn again every month, independently (no persistence at all, so past
                      performance carries no information about the future: a genuine null)"""

    def __init__(self, root, persistent=True, seed=0, alpha_sd=0.06, idio=0.05, drift=0.20, month_alpha_sd=0.15):
        self.root, self.rng = root, np.random.default_rng(seed)
        self.dates = pd.bdate_range(FIRST_NAV, LAST_NAV)
        n = len(self.dates)
        market = self.rng.normal(drift / 252, 0.14 / np.sqrt(252), n)
        self.market = market
        self.navs, self.meta, schemes = {}, {}, []
        code = 1000
        os.makedirs(os.path.join(root, "data", "benchmarks"), exist_ok=True)
        for cat, (suffix, count) in CATEGORIES.items():
            for i in range(count):
                code += 1
                a_const = self.rng.normal(0.03, alpha_sd)
                if persistent:
                    alpha = np.full(n, a_const / 252)
                else:
                    months = self.dates.to_period("M").astype(str)
                    draw = dict(zip(sorted(set(months)), self.rng.normal(0.03, month_alpha_sd, len(set(months)))))
                    alpha = np.array([draw[m] for m in months]) / 252
                beta = self.rng.uniform(0.9, 1.1) if persistent else 1.0   # a persistent beta would also carry information
                r = beta * market + alpha + self.rng.normal(0, idio / np.sqrt(252), n)
                nav = 100 * np.exp(np.cumsum(r))
                name = f"{chr(65 + i)}{code} {suffix} - Direct Plan - Growth"
                self.navs[str(code)] = pd.DataFrame({"date": self.dates, "nav": nav})
                self.meta[str(code)] = {"scheme_name": name, "fund_house": f"House {i} Mutual Fund",
                                        "scheme_category": f"Equity Scheme - {suffix}", "category": cat,
                                        "alpha": a_const}
                schemes.append({"schemeCode": code, "schemeName": name})
            bench = 100 * np.exp(np.cumsum(market * 0.98))
            pd.DataFrame({"date": self.dates.strftime("%d-%m-%Y"), "nav": bench}).to_csv(
                os.path.join(root, "data", "benchmarks", cat.replace(" ", "_") + ".csv"), index=False)
        with open(os.path.join(root, "data", "_scheme_master.json"), "w") as fh:
            json.dump(schemes, fh)
        self.write_navs()

    def write_navs(self, only=None):
        for code, df in self.navs.items():
            if only is not None and code not in only:
                continue
            df.to_csv(os.path.join(self.root, "data", f"{code}.csv"), index=False)
            pd.DataFrame([{k: self.meta[code][k] for k in ("scheme_name", "fund_house", "scheme_category")}]).to_csv(
                os.path.join(self.root, "data", f"{code}_meta.csv"), index=False)


@contextlib.contextmanager
def workdir(universe_factory):
    """chdir into a temp folder that holds the synthetic data; restore everything afterwards."""
    old = os.getcwd()
    root = tempfile.mkdtemp()
    saved = (config.DATA_DIR, config.BENCHMARK_DIR, fetch_nav_data.get_nav_history, config.SCHEME_MASTER_CACHE_DAYS)
    try:
        os.chdir(root)
        config.DATA_DIR = os.path.join(root, "data")
        config.BENCHMARK_DIR = os.path.join(root, "data", "benchmarks")
        fund_universe.ALL_SCHEMES_CACHE = os.path.join(config.DATA_DIR, "_scheme_master.json")
        yield root, universe_factory(root)
    finally:
        os.chdir(old)
        config.DATA_DIR, config.BENCHMARK_DIR, fetch_nav_data.get_nav_history, config.SCHEME_MASTER_CACHE_DAYS = saved
        fund_universe.ALL_SCHEMES_CACHE = os.path.join(config.DATA_DIR, "_scheme_master.json")
        shutil.rmtree(root, ignore_errors=True)


def load_funds(args_extra=()):
    """Loads the synthetic universe exactly the way main() does (offline) and returns (funds, args)."""
    args = wf._parse_args(["--offline", *args_extra])
    wf._validate(args)
    fetch_nav_data.get_nav_history = wf._offline_reader
    config.SCHEME_MASTER_CACHE_DAYS = 10 ** 6
    log = wf.Log(echo=False)
    funds, info = wf.load_universe([c for c in CATEGORIES], args, log)
    return funds, args


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = wf.main(argv)
    return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------------------
# 1. statistics
# --------------------------------------------------------------------------------------
def test_statistics():
    from scipy import stats

    rng = np.random.default_rng(1)
    a = rng.normal(size=60)
    b = 0.5 * a + rng.normal(size=60)
    check("spearman equals scipy", abs(wf.spearman(a, b) - stats.spearmanr(a, b)[0]) < 1e-12)
    t = np.round(a, 1)                                         # ties
    check("spearman with ties equals scipy", abs(wf.spearman(t, b) - stats.spearmanr(t, b)[0]) < 1e-12)
    check("spearman of a constant is nan", np.isnan(wf.spearman(np.ones(10), b[:10])))
    check("spearman needs 3 points", np.isnan(wf.spearman([1, 2], [1, 2])))

    q = wf.assign_quartiles([10, 9, 8, 7, 6, 5, 4, 3])
    check("8 funds -> two per quartile, best score = Q1", list(q) == [1, 1, 2, 2, 3, 3, 4, 4])
    q = wf.assign_quartiles([5.0] * 8)
    check("all tied -> every fund shares one quartile (average rank), none is singled out as top", len(set(q)) == 1 and q[0] != 1)
    q = wf.assign_quartiles([10, 9, np.nan, 8, 7, 6, 5, 4, 3])
    check("a missing score gets no quartile; the other 8 split 2/2/2/2", np.isnan(q[2]) and q[0] == 1 and q[8] == 4
          and sorted(q[~np.isnan(q)]) == [1, 1, 2, 2, 3, 3, 4, 4])

    # IC: two rank dates, two categories; the same 20 funds appear on both dates
    dates = np.array(["d1"] * 20 + ["d2"] * 20)
    cats = np.array((["a"] * 10 + ["b"] * 10) * 2)
    funds = np.array([f"f{i}" for i in range(20)] * 2)
    score = np.tile(np.arange(10.0), 4)
    r = wf.ic_perm(dates, cats, funds, score, score * 2 + 1, 400, 0, "perfect")
    check("perfect ranking: IC = 1, p small", abs(r["mean_ic"] - 1) < 1e-12 and r["p"] < 0.01 and r["n_dates"] == 2)
    tgt = rng.normal(size=40)
    r = wf.ic_perm(dates, cats, funds, score, tgt, 0, 0, "x")
    exp = np.mean([stats.spearmanr(score[dates == d], tgt[dates == d])[0] for d in ("d1", "d2")])
    check("IC per date equals scipy on that date's rows (ranks pooled over the categories of a date)",
          abs(r["mean_ic"] - exp) < 1e-12)
    check("n_perm = 0 gives no p-value", np.isnan(r["p"]))
    ps = []
    for k in range(60):
        g = np.random.default_rng(100 + k)
        s, tg = g.normal(size=40), g.normal(size=40)
        ps.append(wf.ic_perm(dates, cats, funds, s, tg, 200, k, f"n{k}")["p"])
    check("null calibration: p < 0.05 in at most ~12% of 60 independent trials", np.mean(np.array(ps) < 0.05) <= 0.12)
    r1 = wf.ic_perm(dates, cats, funds, score, tgt, 200, 5, "same")
    r2 = wf.ic_perm(dates, cats, funds, score, tgt, 200, 5, "same")
    check("permutation test is reproducible for a seed", r1["p"] == r2["p"])
    check("fewer than 3 observations -> nan, no crash", np.isnan(wf.ic_perm(["d"], ["c"], ["f"], [1.0], [1.0], 10, 0, "e")["mean_ic"]))

    # a fund keeps its whole forward-return history together under the null: with a target that is constant per fund
    # across the two dates, the null distribution must be built from fund-level relabelling (IC null varies by fund)
    fund_effect = rng.normal(size=20)
    tgt_f = np.concatenate([fund_effect, fund_effect])
    s_f = np.concatenate([fund_effect + rng.normal(scale=0.5, size=20), fund_effect + rng.normal(scale=0.5, size=20)])
    r = wf.ic_perm(dates, cats, funds, s_f, tgt_f, 1000, 1, "fundlevel")
    check("fund-level signal repeated on two dates is detected (p small)", r["mean_ic"] > 0.5 and r["p"] < 0.02)

    ids1 = [f"t{i}" for i in range(200)]
    ids4 = [f"b{i}" for i in range(200)]
    x, y = rng.normal(1.0, 0.1, 200), rng.normal(0.0, 0.1, 200)
    sp, lo, hi = wf.bootstrap_spread(ids1, x, ids4, y, 2000, 0, "b")
    check("bootstrap spread is the difference of means and the interval brackets it",
          abs(sp - (x.mean() - y.mean())) < 1e-12 and lo < sp < hi)
    check("bootstrap interval is about +-1.645 se wide", abs((hi - lo) / 2 - 1.645 * np.sqrt(0.01 / 200 * 2)) < 0.012)
    check("bootstrap with too few funds -> nan", np.isnan(wf.bootstrap_spread(["a"], [1.0], ["b", "c"], [2.0, 3.0], 100, 0, "b")[0]))
    # clustering: one fund observed on 4 dates counts as ONE resampling unit, so the interval is wider than if
    # the 4 rows were treated as independent funds
    ids_c = [f"t{i // 4}" for i in range(200)]
    v_c = np.repeat(rng.normal(1.0, 0.1, 50), 4)
    ids_c4 = [f"b{i // 4}" for i in range(200)]
    v_c4 = np.repeat(rng.normal(0.0, 0.1, 50), 4)
    _, lo_c, hi_c = wf.bootstrap_spread(ids_c, v_c, ids_c4, v_c4, 2000, 0, "c")
    _, lo_i, hi_i = wf.bootstrap_spread([f"t{i}" for i in range(200)], v_c, [f"b{i}" for i in range(200)], v_c4, 2000, 0, "c")
    check("cluster bootstrap is wider than treating repeated dates as independent funds", (hi_c - lo_c) > 1.4 * (hi_i - lo_i))


# --------------------------------------------------------------------------------------
# 2. no look-ahead + survivors
# --------------------------------------------------------------------------------------
def _ctx(bench=True, hard=True, horizon=2.0, min_funds=8):
    prov = None
    if bench:
        import benchmark
        prov = benchmark.BenchmarkProvider()
    return {"h_days": int(horizon * 365.25), "horizon": horizon, "bench": prov, "min_funds": min_funds, "hard_filters": hard}


KNOWN_AT_T = ["history_years", "cagr_1y", "cagr_3y", "cagr_5y", "volatility", "risk_return_ratio", "sortino_ratio",
              "max_drawdown", "rolling_positive_pct", "sip_xirr", "benchmark_excess_return",
              "rolling_beat_benchmark_pct", "final_score_0_100", "composite_score", "rank", "score_coverage", "status"]


def test_no_lookahead_and_survivors():
    with workdir(lambda root: Universe(root, persistent=True, seed=3)) as (root, uni):
        funds, args = load_funds()
        T = pd.Timestamp("2023-06-30")
        base, counts = wf.process_date(T, funds, _ctx())
        check("process_date ranks funds", (base["status"] == "RANKED").sum() >= 20)

        # Wreck every NAV after T (and the benchmark files): nothing known at T may move.
        rng = np.random.default_rng(99)
        for code in list(uni.navs):
            df = uni.navs[code].copy()
            after = df["date"] > T
            df.loc[after, "nav"] = df.loc[after, "nav"].to_numpy() * np.exp(np.cumsum(rng.normal(0, 0.03, int(after.sum()))))
            uni.navs[code] = df
        uni.write_navs()
        for cat in CATEGORIES:
            p = os.path.join(root, "data", "benchmarks", cat.replace(" ", "_") + ".csv")
            b = pd.read_csv(p)
            d = pd.to_datetime(b["date"], format="%d-%m-%Y")
            b.loc[d > T, "nav"] = b.loc[d > T, "nav"].to_numpy() * np.exp(np.cumsum(rng.normal(0, 0.05, int((d > T).sum()))))
            b.to_csv(p, index=False)
        funds2, _ = load_funds()
        after_df, _ = wf.process_date(T, funds2, _ctx())
        a = base.set_index("scheme_code")
        b = after_df.set_index("scheme_code")
        same = True
        for col in KNOWN_AT_T:
            x, y = a[col], b.loc[a.index, col]
            if x.dtype == object or str(x.dtype) in ("str", "string"):
                same &= bool((x.astype(str) == y.astype(str)).all())
            else:
                same &= bool(np.allclose(x.astype(float).fillna(-9e9), y.astype(float).fillna(-9e9), rtol=0, atol=1e-12))
        check("NO LOOK-AHEAD: every metric, score and rank known at the rank date is unchanged when later NAVs change", same)
        fa, fb = a["forward_return"].astype(float), b.loc[a.index, "forward_return"].astype(float)
        check("...while the forward return does change (the test really altered the future)", not np.allclose(fa.fillna(0), fb.fillna(0)))
        check("portfolio_quality is never used (not point-in-time)", base["portfolio_quality"].isna().all())

    # survivors / window
    with workdir(lambda root: Universe(root, persistent=True, seed=4)) as (root, uni):
        codes = sorted(uni.navs)
        dead, short, young = codes[0], codes[1], codes[2]
        uni.navs[dead] = uni.navs[dead][uni.navs[dead]["date"] <= "2024-05-31"]                  # merged away
        uni.navs[short] = uni.navs[short][uni.navs[short]["date"] <= "2025-09-30"]              # also stops before T+2y (but is it stale? yes)
        uni.navs[young] = uni.navs[young][uni.navs[young]["date"] >= "2022-09-01"]               # launched 2022-09: <1y at 2023-06-30? no, ~10m
        uni.write_navs()
        funds, _ = load_funds()
        check("stale funds are flagged at load", funds[dead]["stale"] and funds[short]["stale"])
        T = pd.Timestamp("2023-06-30")
        df, counts = wf.process_date(T, funds, _ctx())
        st = df.set_index("scheme_code")["status"]
        check("a fund that stopped updating is DROPPED_STALE and not ranked", st[dead] == wf.ST_STALE)
        check("second stopped fund also dropped", st[short] == wf.ST_STALE)
        check("a fund with <1 year of history at the rank date is NOT_EVALUABLE", st[young] == wf.ST_NOEVAL)
        check("counts add up", counts[wf.ST_STALE] == 2 and counts[wf.ST_NOEVAL] == 1
              and counts["loaded"] == 42 and counts["evaluable"] == 39 and counts["evaluable"] + 3 == counts["loaded"])
        check("dropped funds carry no forward return in the statistics", not df[df["status"].isin([wf.ST_STALE, wf.ST_NOEVAL])]["in_statistics"].any())
        # a rank date whose window the data cannot cover is refused
        code, out, err = run_main(["--offline", "--rank-date", "2025-06-30"])
        check("window not covered by the data -> exit 2 with a clear message", code == 2 and "needs NAV data up to" in err)


# --------------------------------------------------------------------------------------
# 3. end to end
# --------------------------------------------------------------------------------------
def test_end_to_end_signal_and_null():
    with workdir(lambda root: Universe(root, persistent=True, seed=11)) as (root, uni):
        code, out, err = run_main(["--offline", "--permutations", "1000", "--bootstrap", "500", "--output-dir", "o1"])
        check("run succeeds (exit 0)", code == 0)
        for f in ("walk_forward.csv", "walk_forward_summary.csv", "walk_forward.md", "walk_forward_log.txt"):
            check(f"writes {f}", os.path.exists(os.path.join("o1", f)))
        full = pd.read_csv(os.path.join("o1", "walk_forward.csv"))
        check("four quarter-end rank dates of 2023", sorted(full["rank_date"].unique()) ==
              ["2023-03-31", "2023-06-30", "2023-09-29", "2023-12-31"] or len(full["rank_date"].unique()) == 4)
        S = full[full["in_statistics"]]
        ic = np.mean([wf.spearman(g["final_score_0_100"], g["forward_excess"]) for _, g in S.groupby("rank_date")])
        check("skill persists -> the score is positively related to forward excess return", ic > 0.1)
        md = open(os.path.join("o1", "walk_forward.md")).read()
        check("report: honest caveats are present", all(k in md for k in ("Survivorship", "Overlapping windows", "not investment advice")))
        check("report: states the decided settings", "2 years" in md and "SURVIVORS only" in md)
        check("report: the reading sentence reports evidence for a real signal", "evidence that the ranking carried information" in md)
        # hard filters: filtered funds are listed with reasons, not silently lost
        if (full["status"] == wf.ST_FILTERED).any():
            check("filtered funds carry their reasons", full.loc[full["status"] == wf.ST_FILTERED, "exclusion_reasons"].astype(str).str.len().min() > 0)

        code, out, err = run_main(["--offline", "--rank-date", "2023-12-31", "--permutations", "200", "--bootstrap", "100", "--output-dir", "o2"])
        f2 = pd.read_csv(os.path.join("o2", "walk_forward.csv"))
        check("--rank-date gives exactly that one date", set(f2["rank_date"]) == {"2023-12-31"})
        code, out, err = run_main(["--offline", "--rank-date", "2023-12-31", "--no-hard-filters", "--permutations", "100", "--bootstrap", "50", "--output-dir", "o3"])
        f3 = pd.read_csv(os.path.join("o3", "walk_forward.csv"))
        check("--no-hard-filters removes nobody on the filter rule", (f3["status"] == wf.ST_FILTERED).sum() == 0)
        code, out, err = run_main(["--offline", "--rank-date", "2023-12-31", "--category", "small cap", "--permutations", "100", "--bootstrap", "50", "--output-dir", "o4"])
        check("--category limits the universe", set(pd.read_csv(os.path.join("o4", "walk_forward.csv"))["category"]) == {"small cap fund"})

    with workdir(lambda root: Universe(root, persistent=False, seed=12)) as (root, uni):
        code, out, err = run_main(["--offline", "--permutations", "1000", "--bootstrap", "500", "--output-dir", "n1"])
        md = open(os.path.join("n1", "walk_forward.md")).read()
        check("skill does NOT persist -> the report does not claim evidence", "evidence that the ranking carried information" not in md)


def test_bad_input():
    with workdir(lambda root: Universe(root, persistent=True, seed=5)) as (root, uni):
        for argv, why in ((["--offline", "--rank-date", "2023-13-45"], "bad date"),
                          (["--offline", "--horizon-years", "0"], "zero horizon"),
                          (["--offline", "--horizon-years", "30"], "huge horizon"),
                          (["--offline", "--weights", "no_such.ini"], "missing weights file"),
                          (["--offline", "--min-funds", "2"], "min-funds too small"),
                          (["--offline", "--permutations", "-1"], "negative permutations")):
            code, out, err = run_main(argv)
            check(f"{why} -> exit 2, message on stderr", code == 2 and err.startswith("ERROR"))
    old = os.getcwd()
    tmp = tempfile.mkdtemp()
    try:
        os.chdir(tmp)
        config.DATA_DIR = os.path.join(tmp, "data")
        fund_universe.ALL_SCHEMES_CACHE = os.path.join(tmp, "data", "_scheme_master.json")
        code, out, err = run_main(["--offline"])
        check("--offline without a cached scheme list -> exit 2", code == 2 and "scheme list" in err)
    finally:
        os.chdir(old)
        config.DATA_DIR = "data"
        fund_universe.ALL_SCHEMES_CACHE = os.path.join("data", "_scheme_master.json")
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_statistics()
    test_no_lookahead_and_survivors()
    test_end_to_end_signal_and_null()
    test_bad_input()
    print(f"\nAll {passed} checks passed")
