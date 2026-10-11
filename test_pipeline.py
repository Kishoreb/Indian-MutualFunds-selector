"""
test_pipeline.py
----------------
Offline smoke + unit tests using synthetic NAV data (no network needed).

    python test_pipeline.py          # or:  pytest test_pipeline.py
"""

import os
import tempfile

import numpy as np
import pandas as pd

import benchmark
import config
import fund_universe
import metrics
import shortlist

END = pd.Timestamp("2026-10-09")


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def make_nav(daily_returns: np.ndarray, end=END, start_nav=100.0) -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=len(daily_returns) + 1)
    nav = start_nav * np.concatenate([[1.0], np.cumprod(1 + daily_returns)])
    return pd.DataFrame({"date": dates, "nav": nav})


def bench_returns(n_days, seed=1):
    rng = np.random.default_rng(seed)
    return rng.normal(0.0004, 0.010, n_days)


def fund_returns(bench, beta, alpha_daily, idio, seed):
    rng = np.random.default_rng(seed)
    return beta * bench + alpha_daily + rng.normal(0, idio, len(bench))


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_name_and_category_matching():
    nm = fund_universe.name_matches_category
    assert nm("mid cap", "Axis Midcap Fund - Direct Plan - Growth")
    assert nm("mid cap", "Kotak Emerging Equity Mid Cap Fund - Direct - Growth")
    assert not nm("mid cap", "HDFC Large & Mid Cap Fund - Direct Plan - Growth")
    assert nm("large & mid cap", "HDFC Large & Mid Cap Fund - Direct Plan - Growth")
    assert nm("large cap", "ICICI Prudential Bluechip Fund - Direct Plan - Growth")
    assert not nm("large cap", "Canara Robeco Large and Mid Cap Fund - Direct - Growth")

    cm = fund_universe.category_matches
    assert cm("mid cap", "Equity Scheme - Mid Cap Fund") is True
    assert cm("mid cap", "Equity Scheme - Large & Mid Cap Fund") is False
    assert cm("small cap", "Equity Scheme - Mid Cap Fund") is False
    assert cm("elss", "Equity Scheme - ELSS") is True
    assert cm("mid cap", "") is None and cm("mid cap", None) is None


def test_plan_filtering():
    ok = fund_universe._is_preferred_plan
    assert ok("Axis Midcap Fund - Direct Plan - Growth")
    assert not ok("Axis Midcap Fund - Regular Plan - Growth")
    assert not ok("Axis Midcap Fund - Direct Plan - IDCW")
    assert not ok("Nifty Midcap 150 Index Fund - Direct Plan - Growth")
    assert not ok("Motilal Oswal Midcap 100 ETF Direct Growth")
    assert not ok("Axis Nifty Midcap 50 Momentum Direct Growth")
    # Dividend Yield is a CATEGORY and must not be mistaken for a payout option
    assert ok("Templeton India Equity Income / Dividend Yield Fund - Direct Plan - Growth")
    assert not ok("Templeton Dividend Yield Fund - Direct Plan - Dividend Payout")


def test_drawdown_sign_and_ranking_direction():
    # V-shaped NAV: 100 -> 60 -> 100: drawdown is -40%
    dates = pd.bdate_range(end=END, periods=7 * 260)
    nav = np.concatenate([np.linspace(100, 120, 3 * 260), np.linspace(120, 72, 260), np.linspace(72, 130, 3 * 260 - 0)])
    nav = nav[:len(dates)]
    df = pd.DataFrame({"date": dates[:len(nav)], "nav": nav})
    dd = metrics.calculate_max_drawdown(df)
    assert dd is not None and dd < 0 and abs(dd - (-0.4)) < 0.01

    # With ONLY max_drawdown weighted, the shallower-drawdown fund must rank first.
    saved = dict(config.SCORE_WEIGHTS)
    try:
        config.SCORE_WEIGHTS = {"max_drawdown": 1.0}
        universe = pd.DataFrame({
            "scheme_code": list("abcdefghij"),
            "max_drawdown": [-0.10, -0.15, -0.20, -0.25, -0.30, -0.35, -0.40, -0.45, -0.50, -0.55],
        })
        ranked = shortlist.score_and_rank(universe, universe)
        assert ranked.loc[0, "scheme_code"] == "a", ranked[["scheme_code", "max_drawdown"]]
        assert ranked.loc[ranked.index[-1], "scheme_code"] == "j"
    finally:
        config.SCORE_WEIGHTS = saved


def test_sortino_mar_uses_risk_free():
    # Monthly returns positive but always BELOW the monthly risk-free rate.
    rf_m = metrics.monthly_rate(0.065)
    r = pd.Series([rf_m * 0.5] * 24)
    assert metrics.calculate_downside_deviation(r, mar=0.0) == 0.0     # old behaviour hid the shortfall
    assert metrics.calculate_downside_deviation(r, mar=rf_m) > 0       # new behaviour sees it


def test_xirr_known_answer():
    t0 = pd.Timestamp("2024-01-01")
    x = metrics._xirr([(t0, -100.0), (t0 + pd.Timedelta(days=365), 110.0)])
    assert abs(x - 0.10) < 1e-3


def test_common_window_and_short_history():
    b = bench_returns(260 * 3)  # 3y of history only
    short = make_nav(fund_returns(b, 1.0, 0.0002, 0.004, 5))
    assert metrics.calculate_volatility(short, window_years=5.0) is None      # not covered -> None, not "whatever we have"
    assert metrics.calculate_max_drawdown(short, window_years=5.0) is None
    assert metrics.calculate_volatility(short) is not None                    # full-history call still works

    long_ = make_nav(fund_returns(bench_returns(260 * 9), 1.0, 0.0002, 0.004, 6))
    v5 = metrics.calculate_volatility(long_, window_years=5.0)
    vall = metrics.calculate_volatility(long_)
    assert v5 is not None and vall is not None


def test_nav_anomaly_detection():
    r = bench_returns(1500)
    clean = make_nav(r)
    assert metrics.detect_nav_anomalies(clean, 0.20)[0] == 0
    r2 = r.copy()
    r2[700] = 0.45  # 45% one-day jump
    n, mx = metrics.detect_nav_anomalies(make_nav(r2), 0.20)
    assert n == 1 and mx > 0.4


def test_benchmark_stats_recover_known_beta():
    n = 260 * 9
    b = bench_returns(n, seed=11)
    bench = make_nav(b)
    levered = make_nav(fund_returns(b, 1.2, 0.0003, 0.002, 12))
    stats = metrics.calculate_benchmark_stats(levered, bench, 0.065, window_years=5.0)
    assert stats["beta"] is not None and 1.1 < stats["beta"] < 1.3, stats
    assert stats["alpha"] is not None and stats["alpha"] > 0, stats           # built-in positive alpha
    assert stats["information_ratio"] is not None
    assert stats["rolling_beat_pct"] is not None

    twin = metrics.calculate_benchmark_stats(make_nav(b), bench, 0.065, window_years=5.0)
    assert abs(twin["beta"] - 1.0) < 1e-6 and abs(twin["alpha"]) < 1e-6
    assert abs(twin["up_capture"] - 1.0) < 1e-6 and abs(twin["down_capture"] - 1.0) < 1e-6

    # a benchmark with too little overlap yields all-None
    tiny = make_nav(bench_returns(260 * 2, seed=3))
    s2 = metrics.calculate_benchmark_stats(levered, tiny, 0.065, window_years=5.0)
    assert s2["beta"] is None and s2["alpha"] is None


def test_category_average_benchmark():
    navs = {str(i): make_nav(fund_returns(bench_returns(260 * 8, 20), 1.0, 0.0001 * i, 0.003, 30 + i))
            for i in range(8)}
    avg = benchmark.build_category_average(navs)
    assert avg is not None and metrics.years_of_history(avg) > 7
    # the average fund should have beta ~1 against the average
    stats = metrics.calculate_benchmark_stats(navs["3"], avg, 0.065, window_years=5.0)
    assert 0.8 < stats["beta"] < 1.2


def test_percentile_scoring_is_robust_to_outlier():
    # one absurd outlier must not flatten everyone else (winsorized z / percentiles)
    saved = dict(config.SCORE_WEIGHTS)
    try:
        config.SCORE_WEIGHTS = {"cagr_5y": 1.0}
        vals = [0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18, 0.19, 0.20, 5.0]
        u = pd.DataFrame({"scheme_code": list("abcdefghij"), "cagr_5y": vals})
        ranked = shortlist.score_and_rank(u, u)
        assert ranked.loc[0, "scheme_code"] == "j"
        gap = ranked["composite_score"].iloc[1] - ranked["composite_score"].iloc[2]
        assert gap > 0.05, "winsorizing should keep the non-outliers distinguishable"
    finally:
        config.SCORE_WEIGHTS = saved


# ---------------------------------------------------------------------------
# Edge cases, caching, retries, manifest
# ---------------------------------------------------------------------------

def test_edge_cases_never_raise():
    empty = pd.DataFrame({"date": pd.to_datetime([]), "nav": []})
    tiny = make_nav(np.array([0.01, -0.01, 0.02]))
    flat = make_nav(np.zeros(260 * 7))                       # zero volatility
    with_zero_nav = make_nav(bench_returns(260 * 7)); with_zero_nav.loc[5, "nav"] = 0.0
    for df in (empty, tiny, flat, with_zero_nav):
        if df.empty:
            assert metrics.calculate_cagr(df, 3) is None
            assert metrics.calculate_max_drawdown(df) is None
            assert metrics.calculate_sip_xirr(df, 3) is None
            continue
        out = metrics.compute_all_metrics(df, 0.065)
        assert "cagr_3y" in out and "last_nav_date" in out
    out = metrics.compute_all_metrics(flat, 0.065)
    assert out["risk_return_ratio"] is None                      # zero volatility -> undefined, not inf/NaN
    # a flat fund earns 0% < risk-free, so Sortino IS defined (and negative) because the hurdle is the risk-free rate
    assert out["sortino_ratio"] is not None and out["sortino_ratio"] < 0
    out_tiny = metrics.compute_all_metrics(tiny, 0.065)
    assert out_tiny["cagr_5y"] is None and out_tiny["volatility"] is None and out_tiny["rolling_avg"] is None


def test_unsorted_input_is_handled():
    df = make_nav(bench_returns(260 * 7, seed=9))
    shuffled = df.sample(frac=1.0, random_state=1).reset_index(drop=True)
    a = metrics.compute_all_metrics(df, 0.065)
    b = metrics.compute_all_metrics(shuffled, 0.065)
    for k in ("cagr_1y", "cagr_3y", "cagr_5y", "volatility", "max_drawdown", "sortino_ratio"):
        assert a[k] == b[k], k


def _reference_rolling(df, window_years=3.0):
    """The original O(n^2) loop, kept here to prove the vectorized version is equivalent."""
    monthly_nav = df.set_index("date")["nav"].resample("ME").last().dropna()
    window_days = int(window_years * 365.25)
    values = {}
    for end_date, end_nav in monthly_nav.items():
        start_date = end_date - pd.Timedelta(days=window_days)
        prior = monthly_nav[monthly_nav.index <= start_date]
        if prior.empty or start_date - prior.index[-1] > pd.Timedelta(days=45):
            continue
        start_nav = prior.iloc[-1]
        if start_nav <= 0:
            continue
        values[end_date] = (end_nav / start_nav) ** (1 / window_years) - 1
    return pd.Series(values, dtype=float)


def test_vectorized_rolling_matches_reference():
    for years, seed in ((9, 1), (4, 2), (3.2, 3)):
        df = make_nav(bench_returns(int(260 * years), seed=seed))
        ref, new = _reference_rolling(df), metrics.calculate_rolling_returns(df)
        assert ref.index.equals(new.index) and np.allclose(ref.values, new.values), years


def test_nav_on_or_before_binary_search():
    df = make_nav(bench_returns(500, seed=4))
    for d in pd.date_range(df["date"].min() - pd.Timedelta(days=10), df["date"].max() + pd.Timedelta(days=10), freq="13D"):
        sub = df[df["date"] <= d]
        exp = None if sub.empty else float(sub.iloc[-1]["nav"])
        got = metrics._nav_on_or_before(df, d)
        assert (exp is None and got is None) or exp == got


class _FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._p


def _payload(n=30, category="Equity Scheme - Mid Cap Fund"):
    dates = pd.bdate_range(end=END, periods=n)
    return {"meta": {"scheme_name": "Fake Fund", "fund_house": "FakeAMC", "scheme_category": category},
            "data": [{"date": d.strftime("%d-%m-%Y"), "nav": f"{100 + i:.4f}"} for i, d in enumerate(dates)]}


def test_fetch_retries_and_cache_robustness():
    import requests
    import fetch_nav_data as fnd
    saved = (config.DATA_DIR, config.FETCH_BACKOFF_SECONDS, config.FETCH_RETRIES, requests.get)
    with tempfile.TemporaryDirectory() as tmp:
        config.DATA_DIR, config.FETCH_BACKOFF_SECONDS, config.FETCH_RETRIES = tmp, 0.0, 3
        calls = {"n": 0}

        def flaky(url, timeout=20):
            calls["n"] += 1
            if calls["n"] < 3:
                raise requests.ConnectionError("boom")
            return _FakeResp(_payload())
        try:
            requests.get = flaky
            df = fnd.get_nav_history("111", force_refresh=True)
            assert calls["n"] == 3 and len(df) == 30                       # two failures, third attempt succeeded
            assert fnd.get_scheme_meta("111")["scheme_category"] == "Equity Scheme - Mid Cap Fund"

            # fresh cache is used without any network call
            requests.get = lambda *a, **k: (_ for _ in ()).throw(AssertionError("network should not be hit"))
            assert len(fnd.get_nav_history("111")) == 30

            # corrupt cache -> transparently re-downloaded
            with open(os.path.join(tmp, "111.csv"), "w") as f:
                f.write("this,is\nnot,a,nav,file\n\x00\x00")
            requests.get = lambda url, timeout=20: _FakeResp(_payload())
            assert len(fnd.get_nav_history("111")) == 30

            # missing meta file -> re-downloaded (category verification needs it)
            os.remove(os.path.join(tmp, "111_meta.csv"))
            hits = {"n": 0}
            def counting(url, timeout=20):
                hits["n"] += 1
                return _FakeResp(_payload())
            requests.get = counting
            fnd.get_nav_history("111")
            assert hits["n"] == 1 and os.path.exists(os.path.join(tmp, "111_meta.csv"))

            # parallel fetch: one good, one hard failure -> failure skipped, not fatal
            def sometimes(url, timeout=20):
                if url.endswith("/222"):
                    return _FakeResp({}, status=404)
                return _FakeResp(_payload())
            requests.get = sometimes
            res = fnd.fetch_many(["333", "222"], force_refresh=True, workers=2)
            assert list(res) == ["333"]
        finally:
            config.DATA_DIR, config.FETCH_BACKOFF_SECONDS, config.FETCH_RETRIES, requests.get = saved


def test_manifest_written_with_config_snapshot():
    import json
    import manifest
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "m.json")
        m = manifest.write_manifest(path, {"started_utc": "2026-10-10T00:00:00+00:00", "status": "ok",
                                           "query": "mid cap", "benchmark": "X", "counts": {"candidates": 3}})
        on_disk = json.load(open(path))
        assert on_disk["config"]["RISK_WINDOW_YEARS"] == config.RISK_WINDOW_YEARS
        assert on_disk["config_hash"] == m["config_hash"] and len(m["config_hash"]) == 12
        assert on_disk["environment"]["pandas"] == pd.__version__ and on_disk["status"] == "ok"


# ---------------------------------------------------------------------------
# End-to-end (everything patched offline)
# ---------------------------------------------------------------------------

def _run_end_to_end(benchmark_arg=None, extra_args=()):
    n = 260 * 9
    b = bench_returns(n, seed=101)

    funds = {}   # code -> (name, category, df)

    def add(code, name, cat, df):
        funds[code] = (name, cat, df)

    # 14 healthy mid cap funds with varying alpha/beta/noise
    for i in range(14):
        add(f"M{i:02d}", f"AMC{i:02d} Midcap Fund - Direct Plan - Growth", "Equity Scheme - Mid Cap Fund",
            make_nav(fund_returns(b, 0.9 + 0.03 * i, 0.00005 * (i - 5), 0.003 + 0.0003 * (i % 4), 200 + i)))
    # defects the pipeline must catch
    add("STALE", "Stale Midcap Fund - Direct Plan - Growth", "Equity Scheme - Mid Cap Fund",
        make_nav(fund_returns(b, 1.0, 0.0002, 0.003, 301), end=END - pd.Timedelta(days=90)))
    r_jump = fund_returns(b, 1.0, 0.0002, 0.003, 302)
    r_jump[1200] = 0.40
    add("JUMP", "Jumpy Midcap Fund - Direct Plan - Growth", "Equity Scheme - Mid Cap Fund", make_nav(r_jump))
    add("WRONG", "Wrong Midcap Fund - Direct Plan - Growth", "Equity Scheme - Large & Mid Cap Fund",
        make_nav(fund_returns(b, 1.0, 0.0002, 0.003, 303)))
    add("SHORT", "Short Midcap Fund - Direct Plan - Growth", "Equity Scheme - Mid Cap Fund",
        make_nav(fund_returns(b[-260 * 3:], 1.0, 0.0002, 0.003, 304)))
    # index proxies: one too short (4y) and one long enough
    add("IDXSHORT", "Test Nifty Midcap 150 Index Fund - Direct Plan - Growth", "Other Scheme - Index Funds",
        make_nav(b[-260 * 4:]))
    add("IDXLONG", "Test Nifty 500 Index Fund - Direct Plan - Growth", "Other Scheme - Index Funds",
        make_nav(b))

    scheme_master = [{"schemeCode": c, "schemeName": v[0]} for c, v in funds.items()]
    # noise entries that must be filtered out by name rules
    scheme_master += [
        {"schemeCode": "X1", "schemeName": "Regular Midcap Fund - Regular Plan - Growth"},
        {"schemeCode": "X2", "schemeName": "AMC Midcap Fund - Direct Plan - IDCW"},
    ]

    meta = {c: {"scheme_name": v[0], "fund_house": "TestAMC", "scheme_category": v[1]} for c, v in funds.items()}

    # --- patch the network-facing pieces ---
    fund_universe.download_scheme_master = lambda force_refresh=False: scheme_master
    nav_lookup = lambda code, force_refresh=False: funds[str(code)][2]
    shortlist.fetch_many = lambda codes, force_refresh=False, workers=None: {
        c: funds[c][2] for c in codes if c in funds}
    shortlist.get_scheme_meta = lambda code: meta.get(str(code), {"scheme_name": "", "fund_house": "", "scheme_category": ""})
    benchmark.get_nav_history = nav_lookup
    benchmark.get_scheme_meta = shortlist.get_scheme_meta

    argv = ["mid cap"] + (["--benchmark", benchmark_arg] if benchmark_arg else []) + list(extra_args)
    shortlist.main(argv)


def test_end_to_end_auto_benchmark():
    saved_cwd = os.getcwd()
    saved_hints = dict(config.BENCHMARK_NAME_HINTS)
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            # point "mid cap" at the two synthetic proxies: short midcap150 first, then nifty 500
            config.BENCHMARK_NAME_HINTS["mid cap"] = [["nifty midcap 150 index"], ["nifty 500 index"]]
            _run_end_to_end()

            ranked = pd.read_csv(config.OUTPUT_CSV)
            excluded = pd.read_csv(config.EXCLUDED_CSV)
            exmap = dict(zip(excluded["scheme_code"], excluded["reasons"]))

            assert "STALE" in exmap and "stale NAV" in exmap["STALE"]
            assert "JUMP" in exmap and "suspicious NAV jump" in exmap["JUMP"]
            assert "WRONG" in exmap and "AMFI category" in exmap["WRONG"]
            assert "SHORT" in exmap  # insufficient history
            assert not set(ranked["scheme_code"]) & {"STALE", "JUMP", "WRONG", "SHORT", "IDXSHORT", "IDXLONG", "X1", "X2"}
            assert len(ranked) >= 3
            # benchmark metrics populated (4y midcap150 rejected -> long Nifty 500 proxy was NOT tried
            # for this hint list order, so it falls to the second hint set)
            assert ranked["alpha"].notna().all() and ranked["information_ratio"].notna().all()
            assert ranked["composite_score"].is_monotonic_decreasing
            # the 4y Midcap-150 proxy is too short, so the walk must continue to the Nifty 500 proxy
            label, bdf, note = benchmark.resolve_benchmark("mid cap", {})
            assert note == "index proxy" and "Nifty 500" in label, (label, note)
            assert os.path.exists(config.OUTPUT_XLSX)
            import json
            mf = json.load(open(config.MANIFEST_JSON))
            assert mf["status"] == "ok" and mf["category"] == "mid cap"
            assert mf["counts"]["candidates"] == 18 and mf["counts"]["passed_data_quality"] == 15
            assert "Nifty 500" in mf["benchmark"] and mf["latest_nav_date"] == "2026-10-09"
        finally:
            config.BENCHMARK_NAME_HINTS.clear()
            config.BENCHMARK_NAME_HINTS.update(saved_hints)
            os.chdir(saved_cwd)


def test_end_to_end_category_average_and_none():
    saved_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            _run_end_to_end("category")
            r1 = pd.read_csv(config.OUTPUT_CSV)
            assert r1["alpha"].notna().all()
            _run_end_to_end("none")
            r2 = pd.read_csv(config.OUTPUT_CSV)
            assert r2["alpha"].isna().all()       # benchmark skipped
            assert len(r2) >= 3                   # still ranks on the non-benchmark metrics
        finally:
            os.chdir(saved_cwd)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
