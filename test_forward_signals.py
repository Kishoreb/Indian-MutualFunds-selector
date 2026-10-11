"""
test_forward_signals.py
-----------------------
Offline tests for forward_signals.py, the --forward / --make-template CLI
paths and backtest.py, on synthetic NAV data.

    python test_forward_signals.py          # or:  pytest test_forward_signals.py
"""

import contextlib
import json
import logging
import os
import tempfile

import numpy as np
import pandas as pd

import backtest
import config
import forward_signals as fs
import metrics
from test_pipeline import END, _run_end_to_end, bench_returns, fund_returns, make_nav


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _Collect(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def messages(self, level=logging.WARNING):
        return [r.getMessage() for r in self.records if r.levelno >= level]


@contextlib.contextmanager
def capture_logs():
    lg = logging.getLogger("mfshortlister")
    h, old = _Collect(), lg.level
    lg.addHandler(h)
    lg.setLevel(logging.DEBUG)
    try:
        yield h
    finally:
        lg.removeHandler(h)
        lg.setLevel(old)


@contextlib.contextmanager
def patched(**overrides):
    saved = {k: getattr(config, k) for k in overrides}
    for k, v in overrides.items():
        setattr(config, k, v)
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(config, k, v)


@contextlib.contextmanager
def tmp_cwd():
    saved = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield tmp
        finally:
            os.chdir(saved)


def block_returns(means, sds, days_per_block, seed):
    rng = np.random.default_rng(seed)
    return np.concatenate([rng.normal(m, sd, days_per_block) for m, sd in zip(means, sds)])


# ---------------------------------------------------------------------------
# 1. NAV-derived signals
# ---------------------------------------------------------------------------

def test_sharpe_stability_penalizes_one_half_wonders():
    # Low-noise series so the comparison is about the persistence pattern, not luck.
    n = 260 * 7
    steady = make_nav(np.random.default_rng(1).normal(0.0006, 0.002, n))
    # same overall average drift, but all of it earned in the first half
    one_half = make_nav(np.concatenate([np.random.default_rng(2).normal(0.0012, 0.002, n // 2),
                                        np.random.default_rng(3).normal(0.0000, 0.002, n - n // 2)]))
    a = fs.calculate_sharpe_stability(steady, 0.065, 5.0)
    b = fs.calculate_sharpe_stability(one_half, 0.065, 5.0)
    assert a is not None and b is not None
    assert a > 1.0 and b < 0.0, (a, b)        # steady: good in BOTH halves; one-half wonder: its worse half is negative
    # a fund must have at least min_months in each half
    assert fs.calculate_sharpe_stability(make_nav(np.full(260 * 5, 0.0004)), 0.065, 5.0, min_months=40) is None


def test_rolling_p10_and_dispersion():
    n_year = 260
    smooth = make_nav(np.full(9 * n_year, 0.0004))
    regime = make_nav(np.concatenate([np.full(n_year, 0.0012 if i % 2 == 0 else -0.0004) for i in range(9)]))
    p10_s, disp_s = fs.calculate_rolling_p10_dispersion(smooth, 3.0, 5.0, 24)
    p10_r, disp_r = fs.calculate_rolling_p10_dispersion(regime, 3.0, 5.0, 24)
    assert disp_s < 0.01 and disp_r > disp_s * 5, (disp_s, disp_r)
    assert p10_s > p10_r, (p10_s, p10_r)


def test_beta_and_capture_drift():
    n = 260 * 9
    b = bench_returns(n, seed=7)
    rng = np.random.default_rng(8)
    stable = make_nav(1.0 * b + rng.normal(0, 0.002, n))
    betas = np.where(np.arange(n) < n - 260 * 5 // 2 * 1, 0.6, 1.5)   # style change inside the 5y window
    drifting = make_nav(betas * b + np.random.default_rng(9).normal(0, 0.002, n))
    bench = make_nav(b)

    out_s = fs.compute_nav_signals(stable, bench, 0.065, 5.0)
    out_d = fs.compute_nav_signals(drifting, bench, 0.065, 5.0)
    assert out_s["beta_drift"] is not None and out_d["beta_drift"] is not None
    assert out_d["beta_drift"] > 3 * out_s["beta_drift"], (out_s["beta_drift"], out_d["beta_drift"])
    assert out_d["down_capture_drift"] > out_s["down_capture_drift"]


def test_signals_are_none_not_errors_when_data_is_insufficient():
    short = make_nav(bench_returns(260 * 3, seed=3))
    out = fs.compute_nav_signals(short, make_nav(bench_returns(260 * 3, seed=3)), 0.065, 5.0)
    assert all(v is None for v in out.values()), out

    long_ = make_nav(bench_returns(260 * 9, seed=4))
    no_bench = fs.compute_nav_signals(long_, None, 0.065, 5.0)
    assert no_bench["sharpe_stability"] is not None and no_bench["rolling_p10"] is not None
    assert no_bench["beta_drift"] is None and no_bench["down_capture_drift"] is None

    constant = pd.DataFrame({"date": pd.bdate_range(end=END, periods=2000), "nav": 100.0})
    fs.compute_nav_signals(constant, constant, 0.065, 5.0)        # zero variance must not raise
    fs.compute_nav_signals(constant.iloc[0:0], None, 0.065, 5.0)  # empty must not raise


# ---------------------------------------------------------------------------
# 2. fund_attributes.csv: load / validate / stale / derive / template
# ---------------------------------------------------------------------------

def _write(path, text):
    with open(path, "w") as f:
        f.write(text)


def test_attribute_loading_and_validation():
    with tmp_cwd():
        assert fs.load_fund_attributes("nope.csv") is None
        _write("a.csv", "scheme_code,expense_ratio,aum_cr,aum_cr_12m_ago,manager_tenure_years,as_of\n"
                        "1,0.8,1000,800,5,2026-10-01\n"
                        "2,12,-5,100,-1,2026-10-01\n"          # 12% expense (entry error), negative AUM, negative tenure
                        "3,1.1,500,abc,3,not-a-date\n"
                        "3,1.2,600,500,4,2026-10-02\n")        # duplicate code -> keep last
        with capture_logs() as h:
            df = fs.load_fund_attributes("a.csv", today="2026-10-10").set_index("scheme_code")
        msgs = " ".join(h.messages())
        assert "expense_ratio" in msgs and "aum_cr" in msgs and "duplicate" in msgs
        assert df.loc["1", "expense_ratio"] == 0.8
        assert pd.isna(df.loc["2", "expense_ratio"]) and pd.isna(df.loc["2", "aum_cr"]) and pd.isna(df.loc["2", "manager_tenure_years"])
        assert df.loc["3", "expense_ratio"] == 1.2          # last duplicate wins

        _write("bad.csv", "code,expense_ratio\n1,0.5\n")
        try:
            fs.load_fund_attributes("bad.csv")
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "scheme_code" in str(exc)


def test_stale_rows_warn_and_can_be_ignored():
    attrs = pd.DataFrame({"scheme_code": ["1", "2", "3"], "expense_ratio": [0.8, 0.9, 1.0],
                          "aum_cr": [1.0, 1.0, 1.0], "aum_cr_12m_ago": [1.0, 1.0, 1.0],
                          "manager_tenure_years": [3.0, 3.0, 3.0], "turnover_pct": [np.nan] * 3,
                          "as_of": pd.to_datetime(["2026-10-01", "2026-03-01", None])})
    with capture_logs() as h:
        stale = fs.check_staleness(attrs.copy(), today="2026-10-10")
    msgs = " ".join(h.messages())
    assert stale == ["2"] and "older than" in msgs and "no valid 'as_of'" in msgs

    with patched(FORWARD_IGNORE_STALE=True):
        a2 = attrs.copy()
        fs.check_staleness(a2, today="2026-10-10")
        assert pd.isna(a2.loc[1, "expense_ratio"]) and a2.loc[0, "expense_ratio"] == 0.8


def test_merge_derives_aum_strain_and_capacity_flag():
    df = pd.DataFrame({"scheme_code": ["a", "b", "c", "d", "e"]})
    attrs = pd.DataFrame({
        "scheme_code": ["a", "b", "c", "d"], "expense_ratio": [0.7, 1.0, 0.9, 1.2],
        "aum_cr": [1000.0, 2000.0, 6000.0, 1000.0], "aum_cr_12m_ago": [1000.0, 1000.0, 3000.0, 2000.0],
        "manager_tenure_years": [5.0, 3.0, 8.0, 2.0], "turnover_pct": [np.nan] * 4, "as_of": pd.NaT})
    out = fs.merge_attributes(df, attrs, "mid cap").set_index("scheme_code")
    # median AUM of the four funds that have data = (1000+2000)/2 ... values: 1000,1000,2000,6000 -> 1500
    assert abs(out.loc["c", "aum_vs_median"] - 6000 / 1500) < 1e-9
    assert abs(out.loc["c", "aum_growth_12m"] - 1.0) < 1e-9
    assert abs(out.loc["c", "aum_strain"] - (6000 / 1500) * 2.0) < 1e-9
    assert abs(out.loc["d", "aum_strain"] - (1000 / 1500) * 1.0) < 1e-9     # shrinking AUM: growth floored at 0
    assert out.loc["c", "capacity_flag"]                                    # 4.0x the median (>= CAPACITY_RATIO_FLAG)
    assert not out.loc["b", "capacity_flag"] and not out.loc["a", "capacity_flag"]   # 1.33x and 0.67x: below the flag
    assert pd.isna(out.loc["e", "aum_strain"]) and not out.loc["e", "capacity_flag"]       # no data -> NaN, no flag
    assert not fs.merge_attributes(df, attrs, "large cap")["capacity_flag"].any()          # only small/mid are capacity-sensitive
    no_file = fs.merge_attributes(df, None, "mid cap")
    assert no_file["expense_ratio"].isna().all() and "aum_strain" in no_file.columns


def test_template_never_overwrites_user_data():
    with tmp_cwd():
        funds = pd.DataFrame({"scheme_code": ["1", "2", "3"], "scheme_name_hint": ["A", "B", "C"]})
        assert fs.write_template("t.csv", funds) == (0, 3)
        t = pd.read_csv("t.csv", dtype=str, keep_default_na=False)
        assert list(t["scheme_code"]) == ["1", "2", "3"] and {"expense_ratio", "as_of", "aum_cr"} <= set(t.columns)

        # the user fills one row and adds their own column
        t.loc[t["scheme_code"] == "2", ["expense_ratio", "as_of"]] = ["0.70", "2026-10-01"]
        t["my_notes"] = ["", "keep", ""]
        t.to_csv("t.csv", index=False)

        funds2 = pd.concat([funds, pd.DataFrame({"scheme_code": ["4", "5"], "scheme_name_hint": ["D", "E"]})])
        kept, added = fs.write_template("t.csv", funds2)
        assert (kept, added) == (3, 2)
        t2 = pd.read_csv("t.csv", dtype=str, keep_default_na=False).set_index("scheme_code")
        assert t2.loc["2", "expense_ratio"] == "0.70" and t2.loc["2", "my_notes"] == "keep"      # byte-for-byte preserved
        assert set(t2.index) == {"1", "2", "3", "4", "5"}

        _write("weird.csv", "foo,bar\n1,2\n")
        try:
            fs.write_template("weird.csv", funds)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        assert open("weird.csv").read() == "foo,bar\n1,2\n"


def test_category_valuation_note():
    with tmp_cwd():
        _write("v.csv", "category,pe_percentile,as_of\nMid Cap,87,2026-10-01\nsmall cap,10,2026-01-01\nlarge cap,abc,2026-10-01\n")
        mid = fs.category_valuation_note("mid cap", "v.csv", today="2026-10-10")
        assert mid["band"] == "rich" and mid["pe_percentile"] == 87.0 and "87th percentile" in mid["text"]
        small = fs.category_valuation_note("small cap", "v.csv", today="2026-10-10")
        assert small["band"] == "cheap" and "days old" in small["text"]
        with capture_logs() as h:
            assert fs.category_valuation_note("large cap", "v.csv") is None
        assert any("invalid pe_percentile" in m for m in h.messages())
        assert fs.category_valuation_note("flexi cap", "v.csv") is None
        assert fs.category_valuation_note("mid cap", "missing.csv") is None


# ---------------------------------------------------------------------------
# 3. The tilt
# ---------------------------------------------------------------------------

def _universe(n=10, **cols):
    df = pd.DataFrame({"scheme_code": [f"f{i}" for i in range(n)]})
    for k, v in cols.items():
        df[k] = v
    return df


def test_tilt_direction_and_missing_is_neutral():
    exp = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, np.nan]
    u = _universe(expense_ratio=exp)
    with patched(FORWARD_WEIGHTS={"expense_ratio": 1.0}):
        tilt, weights = fs.compute_forward_tilt(u, u)
    assert weights == {"expense_ratio": 1.0}
    assert tilt.iloc[0] == tilt.max() and tilt.iloc[8] == tilt.min()      # cheaper fund -> higher tilt
    assert tilt.iloc[9] == 0.0                                            # missing -> neutral, not penalized


def test_sparse_signal_is_ignored_with_warning():
    u = _universe(expense_ratio=[0.5, 0.7, 0.9] + [np.nan] * 7)
    with patched(FORWARD_WEIGHTS={"expense_ratio": 1.0}):
        with capture_logs() as h:
            tilt, weights = fs.compute_forward_tilt(u, u)
    assert weights == {} and tilt.isna().all()
    assert any("coverage" in m for m in h.messages())

    ranked = u.assign(rank=range(1, 11), composite_score=np.linspace(1, 0, 10))
    with patched(FORWARD_WEIGHTS={"expense_ratio": 1.0}):
        with capture_logs() as h:
            out, info = fs.apply_forward_tilt(ranked, u, enabled=True)
    assert not info["reranked"] and list(out["rank"]) == list(range(1, 11)) and "combined_score" not in out
    assert any("no signal has usable data" in m for m in h.messages())


def test_blend_is_capped():
    with capture_logs() as h:
        assert fs.effective_blend(0.9) == config.FORWARD_MAX_BLEND
    assert any("FORWARD_MAX_BLEND" in m for m in h.messages())
    assert fs.effective_blend(0.1) == 0.1 and fs.effective_blend(-1) == 0.0


def test_apply_tilt_reranks_and_reports_rank_change():
    u = _universe(4, expense_ratio=[2.0, 1.5, 1.0, 0.5])
    ranked = u.assign(rank=[1, 2, 3, 4], composite_score=[1.0, 0.9, 0.8, 0.7])
    big_universe = _universe(12, expense_ratio=[2.0, 1.5, 1.0, 0.5] + [1.0] * 8)

    with patched(FORWARD_WEIGHTS={"expense_ratio": 1.0}):
        off, info_off = fs.apply_forward_tilt(ranked, big_universe, enabled=False)
        assert list(off["rank"]) == [1, 2, 3, 4] and "forward_tilt" in off and "combined_score" not in off

        on, info = fs.apply_forward_tilt(ranked, big_universe, enabled=True, blend=0.25)
    assert info["reranked"] and info["blend"] == 0.25
    expected = 0.75 * ranked["composite_score"].values + 0.25 * on.sort_values("rank")["forward_tilt"].reindex(on.index).values
    assert on["combined_score"].is_monotonic_decreasing
    assert (on["rank_change"] == on["rank_backward"] - on["rank"]).all()
    # expensive fund f0 (rank 1) falls, cheapest fund f3 (rank 4) rises
    assert on.set_index("scheme_code").loc["f3", "rank_change"] > 0
    assert on.set_index("scheme_code").loc["f0", "rank_change"] < 0


# ---------------------------------------------------------------------------
# 4. CLI end-to-end: --make-template, default (off) and --forward (on)
# ---------------------------------------------------------------------------

def test_end_to_end_template_off_and_on():
    with tmp_cwd():
        # --make-template: writes candidates, downloads no NAV, leaves a manifest
        _run_end_to_end(extra_args=["--make-template"])
        t = pd.read_csv(config.FUND_ATTRIBUTES_CSV, dtype=str, keep_default_na=False)
        assert {"M00", "M13"} <= set(t["scheme_code"])
        assert json.load(open(config.MANIFEST_JSON))["status"] == "template written"
        assert not os.path.exists(config.OUTPUT_CSV)

        # tilt OFF (default): signal columns present, ranking untouched
        os.remove(config.FUND_ATTRIBUTES_CSV)
        _run_end_to_end(benchmark_arg="category")
        off = pd.read_csv(config.OUTPUT_CSV)
        assert {"sharpe_stability", "rolling_p10", "forward_tilt", "expense_ratio", "aum_strain"} <= set(off.columns)
        assert "combined_score" not in off.columns and off["composite_score"].is_monotonic_decreasing
        assert off["sharpe_stability"].notna().any() and off["expense_ratio"].isna().all()
        top, second = off.loc[0, "scheme_code"], off.loc[1, "scheme_code"]

        # fill attributes: the backward-ranked #1 is by far the most expensive fund, #2 the cheapest
        def expense(code, i):
            return 2.5 if code == top else 0.30 if code == second else 0.6 + 0.03 * i
        today = pd.Timestamp.now().strftime("%Y-%m-%d")
        rows = [{"scheme_code": f"M{i:02d}", "expense_ratio": expense(f"M{i:02d}", i),
                 "aum_cr": 1000 + 100 * i, "aum_cr_12m_ago": 900 + 100 * i, "manager_tenure_years": 3 + i % 5,
                 "as_of": today} for i in range(14)]
        pd.DataFrame(rows).to_csv(config.FUND_ATTRIBUTES_CSV, index=False)

        with patched(FORWARD_WEIGHTS={"expense_ratio": 1.0}):
            _run_end_to_end(benchmark_arg="category", extra_args=["--forward", "--forward-blend", "0.25"])
        on = pd.read_csv(config.OUTPUT_CSV)
        assert {"combined_score", "rank_backward", "rank_change", "forward_tilt"} <= set(on.columns)
        assert on["combined_score"].is_monotonic_decreasing
        assert (on["rank_change"] == on["rank_backward"] - on["rank"]).all()
        assert on.set_index("scheme_code").loc[top, "rank_backward"] == 1
        assert on.set_index("scheme_code").loc[top, "rank"] > 1, "expensive #1 should be demoted by the tilt"
        assert on.loc[0, "scheme_code"] == second and on.loc[0, "rank_change"] == 1
        manifest = json.load(open(config.MANIFEST_JSON))
        assert manifest["forward_signals"]["reranked"] is True and manifest["forward_signals"]["blend"] == 0.25

        # --no-forward beats config / earlier runs: back to pure backward ranking
        _run_end_to_end(benchmark_arg="category", extra_args=["--no-forward"])
        again = pd.read_csv(config.OUTPUT_CSV)
        assert "combined_score" not in again.columns and again.loc[0, "scheme_code"] == top


# ---------------------------------------------------------------------------
# 5. Back-test
# ---------------------------------------------------------------------------

def test_forward_return_and_grid_have_no_lookahead():
    dates = pd.date_range("2014-01-01", "2026-10-09", freq="D")
    nav = 100 * 1.10 ** ((dates - dates[0]).days / 365.25)
    df = pd.DataFrame({"date": dates, "nav": nav})
    asof = pd.Timestamp("2022-06-30")
    assert abs(backtest.forward_return(df, asof, 1.0) - 0.10) < 1e-3
    assert abs(backtest.forward_return(df, asof, 3.0) - 0.10) < 1e-3
    assert backtest.forward_return(df, pd.Timestamp("2026-06-30"), 3.0) is None          # outcome not observable yet

    grid = backtest.asof_grid({"x": df}, window_years=3.0, horizon_years=3.0, step_months=6)
    assert grid and max(grid) <= df["date"].max() - pd.Timedelta(days=int(3 * 365.25)) + pd.offsets.MonthEnd(0)
    assert min(grid) - pd.Timedelta(days=int(6 * 365.25)) >= df["date"].min()


def _persistent_world(n_funds=16, years=13, alpha_step=0.00006, idio=0.004, seed=0):
    n = 260 * years
    b = bench_returns(n, seed=500 + seed)
    funds = {}
    for i in range(n_funds):
        funds[f"F{i:02d}"] = make_nav(fund_returns(b, 1.0, (i - n_funds / 2) * alpha_step, idio, 600 + seed * 100 + i))
    return funds, make_nav(b)


def test_backtest_finds_persistent_skill():
    funds, bench = _persistent_world()
    detail, summary = backtest.run_backtest(funds, bench, window_years=3.0, horizons=[1.0], step_months=6, min_funds=8)
    s = summary.set_index("signal")
    assert s.loc["rolling_p10", "n_dates"] >= backtest.config.BACKTEST_MIN_DATES
    for q in ("rolling_p10", "cagr_3y", "sharpe_stability"):
        assert s.loc[q, "mean_ic"] > 0.3, (q, s.loc[q, "mean_ic"])
    assert s.loc["rolling_p10", "verdict"] == "supported"
    assert (summary["kind"] == "forward signal").sum() == len(backtest.TESTED_SIGNALS)


def test_backtest_does_not_invent_skill_in_a_random_world():
    funds, bench = _persistent_world(alpha_step=0.0, seed=3)      # identical expected returns: only luck differs
    detail, summary = backtest.run_backtest(funds, bench, window_years=3.0, horizons=[1.0], step_months=6, min_funds=8)
    s = summary.set_index("signal")
    for q in backtest.TESTED_SIGNALS:
        assert s.loc[q, "verdict"] != "supported", (q, s.loc[q].to_dict())
    assert abs(s.loc["rolling_p10", "mean_ic"]) < 0.4


def test_verdicts_and_weight_suggestions():
    mn, pos = config.BACKTEST_MIN_MEAN_IC, config.BACKTEST_MIN_POSITIVE_SHARE
    assert backtest.verdict(config.BACKTEST_MIN_DATES - 1, 0.9, 1.0) == "insufficient data"
    assert backtest.verdict(10, mn, pos) == "supported"
    assert backtest.verdict(10, mn + 0.1, pos - 0.2) == "not supported"       # mean fine, but not consistent
    assert backtest.verdict(10, -mn - 0.1, 0.1) == "inverted"

    summary = pd.DataFrame([
        {"signal": "rolling_p10", "verdict": "supported"},
        {"signal": "sharpe_stability", "verdict": "not supported"},
        {"signal": "beta_drift", "verdict": "inverted"},
        {"signal": "rolling_dispersion", "verdict": "insufficient data"},
    ])
    sug = backtest.suggest_weights(summary)
    assert sug["rolling_p10"] == config.FORWARD_WEIGHTS["rolling_p10"]
    assert sug["sharpe_stability"] == 0.0 and sug["beta_drift"] == 0.0
    assert sug["rolling_dispersion"] == config.FORWARD_WEIGHTS["rolling_dispersion"]     # no evidence either way
    assert sug["expense_ratio"] == config.FORWARD_WEIGHTS["expense_ratio"]               # CSV signals aren't testable here


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\nAll {len(tests)} forward-signal tests passed.")
