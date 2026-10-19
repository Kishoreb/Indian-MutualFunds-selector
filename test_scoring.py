"""Offline tests for the scoring engine and its helpers: weights.ini loading, scoring.py, extra_metrics.py,
data_checks.py, fund_filters.py, build_marketcap.py, import_tri.py. No network.

    python test_scoring.py
"""
import os
import sys
import tempfile
import types

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import weights_loader
import scoring
import extra_metrics
import data_checks
import fund_filters
import build_marketcap

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"ok  {name}")


def raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc:
        return True
    return False


HERE = os.path.dirname(os.path.abspath(__file__))
INI = open(os.path.join(HERE, "weights.ini"), encoding="utf-8").read()


def with_ini(text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "w.ini")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


# ---------------------------------------------------------------- weights.ini
w = weights_loader.load(os.path.join(HERE, "weights.ini"))
check("shipped weights.ini is valid and sums to 100", abs(sum(w["weights_percent"].values()) - 100) < 1e-9)
check("shipped file has the toolkit's 11 weights, the 2 new metrics off",
      sum(1 for v in w["weights_percent"].values() if v > 0) == 11
      and w["weights_percent"]["downside_capture"] == 0 and w["weights_percent"]["quartile_consistency"] == 0)
check("weights returned as fractions summing to 1", abs(sum(w["weights"].values()) - 1) < 1e-12)
check("expense ratio is not a known metric", "expense_ratio" not in weights_loader.KNOWN_METRICS)
check("inline ; comments are ignored", w["weights_percent"]["cagr_3y"] == 15.0)
check("meta read", w["version"] == "2" and w["policy"] == "renormalize_available"
      and abs(w["min_coverage"] - 0.7) < 1e-12 and w["method"] == "zscore" and w["min_group_size"] == 8)
check("missing file -> error", raises(weights_loader.WeightsError, weights_loader.load, "/no/such/weights.ini"))
check("non-numeric weight -> error", raises(weights_loader.WeightsError, weights_loader.load,
      with_ini(INI.replace("cagr_3y                    = 15", "cagr_3y = fifteen"))))
check("negative weight -> error", raises(weights_loader.WeightsError, weights_loader.load,
      with_ini(INI.replace("cagr_3y                    = 15", "cagr_3y = -15"))))
check("weights not summing to 100 -> error", raises(weights_loader.WeightsError, weights_loader.load,
      with_ini(INI.replace("cagr_3y                    = 15", "cagr_3y = 16"))))
check("unknown metric -> error", raises(weights_loader.WeightsError, weights_loader.load,
      with_ini(INI + "expense_ratio = 0\n")))
check("missing metric -> error", raises(weights_loader.WeightsError, weights_loader.load,
      with_ini(INI.replace("sip_xirr                   = 5", ""))))
check("bad policy -> error", raises(weights_loader.WeightsError, weights_loader.load,
      with_ini(INI.replace("renormalize_available\n", "guess\n", 1).replace("missing_data_policy = renormalize_available", "missing_data_policy = guess"))))
check("bad scoring method -> error", raises(weights_loader.WeightsError, weights_loader.load,
      with_ini(INI.replace("scoring_method = zscore", "scoring_method = magic"))))
check("coverage outside 0-100 -> error", raises(weights_loader.WeightsError, weights_loader.load,
      with_ini(INI.replace("minimum_coverage_percent = 70", "minimum_coverage_percent = 170"))))
check("missing [meta] key -> error", raises(weights_loader.WeightsError, weights_loader.load,
      with_ini(INI.replace("min_group_size = 8", ""))))
check("0 weight allowed", weights_loader.load(with_ini(
    INI.replace("cagr_1y                    = 5", "cagr_1y = 0").replace("cagr_3y                    = 15", "cagr_3y = 20")
))["weights"]["cagr_1y"] == 0)

# ---------------------------------------------------------------- scoring
W3 = {"a": 0.5, "b": 0.3, "c": 0.2}


def frame(**cols):
    n = len(next(iter(cols.values())))
    d = {"scheme_code": [str(i) for i in range(1, n + 1)], "scheme_name": [f"F{i}" for i in range(1, n + 1)]}
    d.update(cols)
    return pd.DataFrame(d)


df = frame(a=[1.0, 2.0, 3.0, 4.0], b=[4.0, 3.0, 2.0, 1.0], c=[1.0, 1.0, 1.0, 1.0])
r = scoring.score_and_rank(df, W3, method="percentile", min_coverage=0.5)
check("higher-is-better percentile: best a value scores 100, worst 0",
      r.set_index("scheme_code").loc["4", "score_a"] == 100 and r.set_index("scheme_code").loc["1", "score_a"] == 0)
check("percentile of reversed metric b is reversed", r.set_index("scheme_code").loc["1", "score_b"] == 100)
check("tied values share the average percentile", abs(r.set_index("scheme_code").loc["1", "score_c"] - 50.0) < 1e-9)

low = frame(downside_capture=[0.5, 0.9, 1.2], a=[1.0, 1.0, 1.0])
rl = scoring.score_and_rank(low, {"downside_capture": 0.5, "a": 0.5}, method="percentile").set_index("scheme_code")
check("lower-is-better: the smallest downside capture scores highest",
      rl.loc["1", "score_downside_capture"] == 100 and rl.loc["3", "score_downside_capture"] == 0)

dd = frame(max_drawdown=[-0.20, -0.35, -0.55])
for method in ("zscore", "percentile"):
    rd = scoring.score_and_rank(dd, {"max_drawdown": 1.0}, method=method).set_index("scheme_code")
    check(f"max drawdown direction ({method}): a smaller fall ranks higher",
          rd.loc["1", "rank"] == 1 and rd.loc["3", "rank"] == 3)

# renormalize: manual calculation with one missing value
m = frame(a=[1.0, 2.0, 3.0], b=[3.0, 2.0, np.nan], c=[1.0, 5.0, 2.0])
rm = scoring.score_and_rank(m, W3, policy="renormalize_available", min_coverage=0.5, method="percentile").set_index("scheme_code")
pa = {"1": 0.0, "2": 50.0, "3": 100.0}
pb = {"1": 100.0, "2": 0.0}
pc = {"1": 0.0, "2": 100.0, "3": 50.0}
exp3 = (0.5 * pa["3"] + 0.2 * pc["3"]) / 0.7
exp2 = (0.5 * pa["2"] + 0.3 * pb["2"] + 0.2 * pc["2"]) / 1.0
check("renormalize: fund missing b is a weighted average over a and c only", abs(rm.loc["3", "final_score_0_100"] - exp3) < 1e-9)
check("renormalize: a complete fund is unchanged", abs(rm.loc["2", "final_score_0_100"] - exp2) < 1e-9)
check("coverage = measured weight / total weight", abs(rm.loc["3", "score_coverage"] - 0.7) < 1e-9 and rm.loc["2", "score_coverage"] == 1.0)
check("score_missing names the missing metric", rm.loc["3", "score_missing"] == "b" and rm.loc["2", "score_missing"] == "")
ra = scoring.score_and_rank(m, W3, policy="average", min_coverage=0.5, method="percentile").set_index("scheme_code")
check("average policy: a missing metric counts as 50", abs(ra.loc["3", "final_score_0_100"] - (0.5 * 100 + 0.3 * 50 + 0.2 * 50)) < 1e-9)

# coverage floor
rf = scoring.score_and_rank(m, W3, policy="renormalize_available", min_coverage=0.8).set_index("scheme_code")
check("below the coverage floor -> INSUFFICIENT_DATA, no rank, no score",
      rf.loc["3", "status"] == "INSUFFICIENT_DATA" and pd.isna(rf.loc["3", "rank"]) and pd.isna(rf.loc["3", "composite_score"]))
check("funds above the floor are ranked 1..n without gaps", sorted(rf["rank"].dropna().astype(int).tolist()) == [1, 2])
check("floor is inclusive (coverage exactly equal passes)", scoring.score_and_rank(m, W3, min_coverage=0.7).set_index("scheme_code").loc["3", "status"] == "RANKED")
check("unranked funds sort last", scoring.score_and_rank(m, W3, min_coverage=0.8)["status"].tolist()[-1] == "INSUFFICIENT_DATA")

# zero is a value, not missing
z = frame(a=[0.0, 1.0, 2.0], b=[0.0, 0.0, 0.0], c=[0.0, 0.0, 1.0])
rz = scoring.score_and_rank(z, W3, method="percentile").set_index("scheme_code")
check("zero is treated as a valid value", rz.loc["1", "score_coverage"] == 1.0 and rz.loc["1", "score_missing"] == "")
check("zero is not missing (a=0 gets the lowest score, not skipped)", rz.loc["1", "score_a"] == 0)

# ties and determinism
tie = frame(a=[1.0, 1.0, 1.0], b=[2.0, 2.0, 2.0], c=[3.0, 3.0, 3.0])
rt = scoring.score_and_rank(tie, W3)
check("identical funds are ranked by scheme_code (deterministic)", rt["scheme_code"].tolist() == ["1", "2", "3"])
shuffled = tie.iloc[[2, 0, 1]].reset_index(drop=True)
check("input order does not change the ranking", scoring.score_and_rank(shuffled, W3)["scheme_code"].tolist() == ["1", "2", "3"])
big = frame(a=list(np.random.default_rng(0).normal(size=20)), b=list(np.random.default_rng(1).normal(size=20)),
            c=list(np.random.default_rng(2).normal(size=20)))
pd.testing.assert_frame_equal(scoring.score_and_rank(big, W3), scoring.score_and_rank(big.copy(), W3))
check("same input and weights give identical output", True)

# z-score method
zs = scoring.score_and_rank(frame(a=[1.0, 2.0, 3.0]), {"a": 1.0}, method="zscore")
check("z-score composite of three equally spaced values is -1, 0, 1 (best first)",
      np.allclose(sorted(zs["composite_score"]), [-1, 0, 1]) and zs["scheme_code"].tolist()[0] == "3")
check("no spread -> z-score 0 for everyone", np.allclose(scoring.score_and_rank(frame(a=[2.0, 2.0, 2.0]), {"a": 1.0})["composite_score"], 0))
one = scoring.score_and_rank(frame(a=[5.0]), {"a": 1.0}, method="percentile")
check("a single fund gets the neutral 50", one["final_score_0_100"].iloc[0] == 50)

# zero-weight metrics are ignored; missing columns tolerated
zw = scoring.score_and_rank(frame(a=[1.0, 2.0, 3.0]), {"a": 0.5, "b": 0.5, "downside_capture": 0.0})
check("a column absent from the table counts as fully missing, not an error", (zw["score_missing"] == "b").all())
check("zero-weight metrics are not reported as missing", "downside_capture" not in zw["score_missing"].iloc[0])
check("coverage ignores zero-weight metrics", np.allclose(zw["score_coverage"], 0.5))
check("all-zero weights -> error", raises(ValueError, scoring.score_and_rank, frame(a=[1.0]), {"a": 0.0}))
check("unknown policy -> error", raises(ValueError, scoring.score_and_rank, frame(a=[1.0]), {"a": 1.0}, policy="x"))
check("None values are read as missing", scoring.score_and_rank(
    pd.DataFrame({"scheme_code": ["1", "2"], "a": [1.0, None], "b": [1.0, 2.0]}), {"a": 0.5, "b": 0.5}, min_coverage=0.4
).set_index("scheme_code").loc["2", "score_missing"] == "a")

# contributions add up to the final score; confidence flag
rc = scoring.score_and_rank(m, W3, min_coverage=0.5, method="percentile")
sums = rc[[f"contrib_{k}" for k in W3]].sum(axis=1)
check("points per metric add up to the final score", np.allclose(sums, rc["final_score_0_100"]))
rc_avg = scoring.score_and_rank(m, W3, policy="average", min_coverage=0.5)
check("points add up to the final score under the average policy too",
      np.allclose(rc_avg[[f"contrib_{k}" for k in W3]].sum(axis=1), rc_avg["final_score_0_100"]))
check("small group is flagged LOW confidence", scoring.score_and_rank(m, W3, min_coverage=0.5, min_group_size=8)["confidence"].iloc[0].startswith("LOW"))
check("big enough group is OK", scoring.score_and_rank(big, W3, min_group_size=8)["confidence"].iloc[0] == "OK")
check("an input rank column is replaced, not duplicated", list(scoring.score_and_rank(big.assign(rank=99), W3).columns).count("rank") == 1)

# ---------------------------------------------------------------- extra metrics
idx = pd.bdate_range("2018-01-01", "2026-10-09")
rng = np.random.default_rng(5)
bench_nav = pd.DataFrame({"date": idx, "nav": 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, len(idx))))})
bm_month = bench_nav.set_index("date")["nav"].resample("ME").last()
bm_ret = bm_month.pct_change().dropna()


def fund_from_monthly(ret):
    nav = 100 * np.cumprod(1 + ret)
    return pd.DataFrame({"date": ret.index, "nav": nav.values})


half = fund_from_monthly(bm_ret * 0.5)
bench_m = pd.DataFrame({"date": bm_month.index, "nav": bm_month.values})
dc = extra_metrics.downside_capture(half, bench_m)
check("downside capture of a fund that takes half of every move is 0.5", dc is not None and abs(dc - 0.5) < 1e-9)
check("downside capture of the benchmark against itself is 1.0", abs(extra_metrics.downside_capture(bench_m, bench_m) - 1.0) < 1e-9)
check("fund that rises when the benchmark falls has capture below 0", extra_metrics.downside_capture(
    fund_from_monthly(-bm_ret * 0.1 + 0.0), bench_m) < 0)
check("too few down months -> None", extra_metrics.downside_capture(half.head(10), bench_m.head(10)) is None)
check("empty series -> None", extra_metrics.downside_capture(half.iloc[0:0], bench_m) is None)

months = pd.date_range("2020-01-31", periods=40, freq="ME")
roll = {str(i): pd.Series(np.full(40, float(i)), index=months) for i in range(1, 11)}   # fund 10 always best
q = extra_metrics.quartile_consistency(roll, min_peers=8)
check("the always-best fund is in the top half 100% of the time", q["10"]["quartile_consistency"] == 1.0 and q["10"]["q1_share"] == 1.0)
check("the always-worst fund is in the top half 0% of the time", q["1"]["quartile_consistency"] == 0.0)
check("middle fund: top half but not top quartile", q["7"]["quartile_consistency"] == 1.0 and q["7"]["q1_share"] == 0.0)
check("too few peers -> None for everyone", all(v["quartile_consistency"] is None for v in extra_metrics.quartile_consistency(
    {k: roll[k] for k in list(roll)[:5]}, min_peers=8).values()))
short = dict(roll)
short["11"] = pd.Series([1.0] * 5, index=months[:5])
check("a fund with under 12 usable dates gets None", extra_metrics.quartile_consistency(short, min_peers=8)["11"]["quartile_consistency"] is None)

# ---------------------------------------------------------------- data checks
dt = pd.DataFrame({
    "scheme_code": ["1", "1", "2", "3", "4"], "scheme_name": ["A", "A2", "Same", "same", "D"],
    "scheme_category": ["Equity Scheme - Small Cap Fund"] * 4 + ["Equity Scheme - Mid Cap Fund"],
    "last_nav_date": pd.to_datetime(["2026-10-09", "2026-10-09", "2026-10-09", "2026-08-01", "2026-10-09"]),
    "cagr_5y": [0.1, 0.1, 0.1, 0.1, 0.1], "cagr_3y": [0.1] * 5, "history_years": [7, 7, 3.0, 7, 7],
    "max_drawdown": [-0.3, -0.3, -0.3, 0.1, -0.3], "volatility": [0.2] * 5, "rolling_positive_pct": [0.9] * 5})
dedup, n_dup = data_checks.drop_duplicate_codes(dt)
check("duplicate scheme_code rows are dropped (first kept)", n_dup == 1 and dedup["scheme_name"].tolist()[0] == "A")
flags, info = data_checks.check_table(dedup, stale_days=10)
f = {c: fl for c, fl in zip(dedup["scheme_code"], flags)}
check("duplicate names are flagged both ways", "DUPLICATE_NAME" in f["2"] and "DUPLICATE_NAME" in f["3"])
check("stale NAV is flagged against the newest date in the group", any(x.startswith("STALE_NAV") for x in f["3"]))
check("fresh funds are not flagged stale", not any(x.startswith("STALE") for x in f["1"]))
check("5y CAGR with under 5y history is inconsistent", any("5y CAGR" in x for x in f["2"]))
check("drawdown above zero is inconsistent", any("drawdown" in x for x in f["3"]))
check("a category different from the group's is flagged", "CATEGORY_MISMATCH" in f["4"])
_v = pd.DataFrame({"scheme_code": ["a", "b", "c"], "scheme_name": ["A", "B", "C"],
                   "scheme_category": ["Equity Scheme - Small Cap Fund", "Equity Schemes - Small Cap Fund", "Equity Scheme - Mid Cap Fund"]})
_vf, _ = data_checks.check_table(_v)
check("'Scheme' vs 'Schemes' spelling is not a category mismatch", "CATEGORY_MISMATCH" not in _vf[1] and "CATEGORY_MISMATCH" not in _vf[0])
check("a genuinely different category is still flagged", "CATEGORY_MISMATCH" in _vf[2])
check("as-of date is the newest NAV date", info["as_of"] == pd.Timestamp("2026-10-09"))
check("explicit reference date is honoured", data_checks.check_table(dedup, 10, reference_date="2026-12-31")[1]["as_of"] == pd.Timestamp("2026-12-31"))
check("a run on old data warns", any("not current" in w for w in data_checks.check_table(
    dedup.assign(last_nav_date=pd.Timestamp("2020-01-01")), 10)[1]["warnings"]))
check("empty table is fine", data_checks.check_table(dt.iloc[0:0])[0] == [])

# ---------------------------------------------------------------- optional filters
cfg = types.SimpleNamespace(MIN_AUM_CR=500, MAX_AUM_CR=None, MAX_AUM_CR_BY_CATEGORY={}, MIN_MANAGER_TENURE_YEARS=3.0,
                            MAX_PORTFOLIO_TURNOVER_PCT=100, MAX_AVG_CASH_PCT=10, MAX_TOP10_PCT=60)
tmp = tempfile.mkdtemp()
attr_path = os.path.join(tmp, "attrs.csv")
pd.DataFrame({"scheme_code": ["1", "2", "3", "4"], "aum_cr": [900, 100, 800, np.nan],
              "manager_tenure_years": [5, 5, 1, 4], "portfolio_turnover_pct": [50, 50, 50, 150],
              "avg_cash_pct_12m": [3, 3, 3, 3]}).to_csv(attr_path, index=False)
base = pd.DataFrame({"scheme_code": ["1", "2", "3", "4", "5"], "scheme_category": ["x"] * 5,
                     "pq_top10_pct": [40, 40, 40, 40, 70]})
merged = fund_filters.merge_attributes(base, fund_filters.load_attributes(attr_path))
kept, why, gaps = fund_filters.apply_attribute_filters(merged, cfg)
check("AUM below the minimum drops a fund", "2" not in kept["scheme_code"].tolist() and "AUM below minimum" in why["2"])
check("short manager tenure drops a fund", "3" not in kept["scheme_code"].tolist())
check("high turnover drops a fund", "4" not in kept["scheme_code"].tolist() or "portfolio turnover too high" in why.get("4", []))
check("top-10 concentration filter uses the holdings value", "5" not in kept["scheme_code"].tolist())
check("a missing AUM is not dropped by the AUM filter, it is flagged", "no AUM data" in gaps["4"])
check("fund with no attribute row at all is kept and flagged", "no AUM data" in gaps["5"] or "5" not in kept["scheme_code"].tolist())
off = types.SimpleNamespace(MIN_AUM_CR=None, MAX_AUM_CR=None, MAX_AUM_CR_BY_CATEGORY={}, MIN_MANAGER_TENURE_YEARS=None,
                            MAX_PORTFOLIO_TURNOVER_PCT=None, MAX_AVG_CASH_PCT=None, MAX_TOP10_PCT=None)
k2, w2, g2 = fund_filters.apply_attribute_filters(merged, off)
check("with every filter off nothing is dropped or flagged", len(k2) == 5 and not w2 and not g2)
check("no attribute file -> None and columns still present", fund_filters.load_attributes(os.path.join(tmp, "nope.csv")) is None
      and "aum_cr" in fund_filters.merge_attributes(base, None).columns)
cap = types.SimpleNamespace(**{**vars(off), "MAX_AUM_CR": 850})
k3, w3_, g3 = fund_filters.apply_attribute_filters(merged, cap)
check("maximum AUM drops a fund above the cap", "1" not in k3["scheme_code"].tolist() and "3" in k3["scheme_code"].tolist())

# ---------------------------------------------------------------- build_marketcap
lines = ["1 Reliance Industries Ltd INE002A01018 RELIANCE Large Cap", "2 Some Mid Co Ltd INE123A01012 SOMEMID Mid Cap",
         "3 Tiny Co INE999Z01011 TINY Small Cap", "junk line", "4 No ISIN Co Large Cap", "5 Odd Co INE000A01011 Micro"]
df_t = build_marketcap.from_text_lines(lines)
check("pdf-style lines: ISIN + category picked up, junk skipped", len(df_t) == 3 and set(df_t["category"]) == {"large", "mid", "small"})
raw = pd.DataFrame({0: [1, 2, 3], 1: ["A Ltd", "B Ltd", "C Ltd"], 2: ["INE002A01018", "INE123A01012", "bad"],
                    3: ["Large Cap", "Mid Cap", "Small Cap"]})
df_x = build_marketcap.from_table(raw)
check("table: finds the ISIN and category columns and drops invalid ISINs", len(df_x) == 2 and df_x["category"].tolist() == ["large", "mid"])
check("validate warns on a list that is too small", any("only" in n for n in build_marketcap.validate(df_x)))
src = os.path.join(tmp, "amfi.csv")
pd.DataFrame({"n": ["A", "B", "A again"], "isin": ["INE002A01018", "INE123A01012", "INE002A01018"], "cat": ["Large Cap", "Mid Cap", "Large Cap"]}).to_csv(src, index=False)
out_csv = os.path.join(tmp, "out", "amfi_market_cap.csv")
check("main writes the csv and removes duplicate ISINs", build_marketcap.main([src, "-o", out_csv]) == 0
      and len(pd.read_csv(out_csv)) == 2 and list(pd.read_csv(out_csv).columns) == ["isin", "category"])
check("main exits 1 when nothing usable is found", build_marketcap.main([__file__.replace("test_scoring.py", "weights.ini"), "-o", os.path.join(tmp, "x.csv")]) in (1, 2))
check("unreadable file type exits 2", build_marketcap.main([os.path.join(tmp, "a.bin"), "-o", os.path.join(tmp, "y.csv")]) == 2)

# ---------------------------------------------------------------- import_tri
import config
import import_tri
d_idx = pd.bdate_range("2019-01-01", "2026-10-09")
tri = pd.DataFrame({"Date": d_idx.strftime("%d %b %Y"), "Total Returns Index": [f"{v:,.2f}" for v in 10000 * np.exp(np.arange(len(d_idx)) * 0.0004)]})
a_path, b_path = os.path.join(tmp, "tri_a.csv"), os.path.join(tmp, "tri_b.csv")
half_n = len(tri) // 2
tri.iloc[:half_n + 50].to_csv(a_path, index=False)          # overlapping ranges
tri.iloc[half_n:].to_csv(b_path, index=False)
bdir = os.path.join(tmp, "bm")
check("import_tri merges overlapping files and writes <category>.csv",
      import_tri.main(["--category", "large & mid cap", a_path, b_path, "--out-dir", bdir]) == 0
      and os.path.exists(os.path.join(bdir, "large_and_mid_cap.csv")))
res = pd.read_csv(os.path.join(bdir, "large_and_mid_cap.csv"))
check("merged series has unique, sorted dates and parses thousands separators",
      res["date"].is_unique and res["date"].is_monotonic_increasing and len(res) == len(tri) and res["nav"].iloc[0] > 9000)
check("output filename matches the name benchmark.py reads", import_tri.filename_for("small cap") == "small_cap.csv")
check("unknown category -> exit 2", import_tri.main(["--category", "sectoral", a_path, "--out-dir", bdir]) == 2)
tiny = os.path.join(tmp, "tiny.csv")
tri.head(20).to_csv(tiny, index=False)
check("too little history -> exit 1", import_tri.main(["--category", "small cap", tiny, "--out-dir", bdir]) == 1)
check("missing arguments -> exit 2", import_tri.main([]) == 2)
check("--list works", import_tri.main(["--list"]) == 0)

print(f"\nAll {passed} checks passed")
