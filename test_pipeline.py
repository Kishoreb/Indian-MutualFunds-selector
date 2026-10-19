"""Offline end-to-end tests for shortlist.py (CLI, multi-category runs, filters, outputs, exit codes) and
holdings_import.py, with a SIMULATED data layer (no network; the live mfapi.in / AMC sites were not used).

    python test_pipeline.py
"""
import os
import shutil
import sys
import tempfile
import types
import zipfile
from datetime import datetime, timedelta

import numpy as np
import openpyxl
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"ok  {name}")


TODAY = pd.Timestamp(datetime.now().date())
END = TODAY - pd.Timedelta(days=1)
DATES = pd.bdate_range(END - pd.Timedelta(days=8 * 365), END)

SMALL = list(range(101, 111))      # 101..110 ranked or flagged below
MID = list(range(201, 211))
STALE, FAILS, SPARSE, THIN = 111, 112, 109, 108


def nav_for(code):
    rng = np.random.default_rng(code)
    nav = pd.DataFrame({"date": DATES, "nav": 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, len(DATES))))})
    if code == STALE:
        nav = nav[nav["date"] <= END - pd.Timedelta(days=60)].reset_index(drop=True)
    nav["code"] = str(code)
    return nav


def fake_metrics(code):
    rng = np.random.default_rng(int(code) + 1000)
    m = {"cagr_1y": rng.uniform(.12, .35), "cagr_3y": rng.uniform(.12, .3), "cagr_5y": rng.uniform(.12, .3),
         "volatility": rng.uniform(.15, .25), "risk_return_ratio": rng.uniform(.6, 1.5),
         "sortino_ratio": rng.uniform(.8, 2.2), "downside_deviation": .1, "rolling_avg": .15, "rolling_min": .02,
         "rolling_positive_pct": rng.uniform(.7, 1), "rolling_std": .05, "sip_xirr": rng.uniform(.1, .3),
         "max_drawdown": -rng.uniform(.2, .5), "history_years": 8.0}
    if int(code) == FAILS:
        m["cagr_3y"] = 0.02
    if int(code) == SPARSE:
        m["sip_xirr"] = None
        m["rolling_positive_pct"] = None
    return m


# ---------------------------------------------------------------- simulated data layer
fu = types.ModuleType("fund_universe")
CATS = {"small cap": SMALL + [101, STALE, FAILS], "mid cap": MID}      # 101 listed twice


def find_candidates(cat, force_refresh=False):
    key = cat.strip().lower()
    if key == "nothing":
        return "large cap", []
    if key not in CATS:
        raise ValueError(f"Unrecognized category '{cat}'.")
    return key, [{"scheme_code": str(c), "scheme_name_hint": f"Fund {c} {key.title()} - Direct Plan - Growth"} for c in CATS[key]]


fu.find_candidates = find_candidates
fu.supported_categories = lambda: ["mid cap", "small cap"]
fn = types.ModuleType("fetch_nav_data")
fn.get_nav_history = lambda code, force_refresh=False: nav_for(int(code))
fn.get_scheme_meta = lambda code: {"scheme_name": f"Fund {code}", "fund_house": "Test Mutual Fund",
                                   "scheme_category": "Equity Scheme - Small Cap Fund" if int(code) < 200 else "Equity Scheme - Mid Cap Fund"}
mt = types.ModuleType("metrics")
mt.compute_all_metrics = lambda nav, *a, **k: fake_metrics(nav["code"].iloc[0])

bm = types.ModuleType("benchmark")
BENCH_NAV = pd.DataFrame({"date": DATES, "nav": 100 * np.exp(np.cumsum(np.random.default_rng(7).normal(0.0004, 0.01, len(DATES))))})


def _month_end_nav(df):
    return df.set_index("date")["nav"].sort_index().resample("ME").last().dropna()


def _rolling_cagr(monthly, window_years):
    window = pd.Timedelta(days=int(window_years * 365.25))
    idx, out = monthly.index, {}
    for end_date, end_nav in monthly.items():
        start_date = end_date - window
        pos = idx.searchsorted(start_date, side="right") - 1
        if pos < 0 or start_date - idx[pos] > pd.Timedelta(days=45):
            continue
        start_nav = monthly.iloc[pos]
        if start_nav <= 0:
            continue
        out[end_date] = (end_nav / start_nav) ** (1 / window_years) - 1
    return pd.Series(out, dtype=float)


def category_key(cat, fallback=None):
    t = (cat or "").lower()
    return "small cap" if "small cap" in t else "mid cap" if "mid cap" in t else fallback


class Provider:
    def __init__(self, force_refresh=False): pass
    def get(self, key):
        return {"label": "Test TRI", "df": BENCH_NAV, "source": "test", "proxy_name": "proxy", "proxy_code": "0"} if key else None
    def describe(self):
        return ["  small cap: Test TRI via test [proxy] (8.0y history)"]


def metrics_for_fund(df, provider, cat, default):
    code = int(df["code"].iloc[0])
    rng = np.random.default_rng(code + 5)
    none = code in (THIN, SPARSE)
    return {"benchmark_name": "Test TRI", "benchmark_proxy": "proxy", "benchmark_cagr": 0.12,
            "benchmark_excess_return": None if none else rng.uniform(-.02, .05),
            "rolling_beat_benchmark_pct": None if none else rng.uniform(.3, .9), "benchmark_windows": 30}


bm._month_end_nav, bm._rolling_cagr, bm.category_key = _month_end_nav, _rolling_cagr, category_key
bm.BenchmarkProvider, bm.metrics_for_fund = Provider, metrics_for_fund
bm.EMPTY_BENCHMARK_METRICS = {}

pqm = types.ModuleType("portfolio_quality")
pqm.EXCEL_EXT = (".xls", ".xlsx", ".xlsm")
pqm.EMPTY_FIELDS = {"portfolio_quality": None, "pq_coverage": None, "pq_top10_pct": None, "pq_holdings": None,
                    "pq_top_sector_pct": None, "pq_largemid_pct": None, "pq_cash_pct": None,
                    "pq_as_of": "", "pq_source": "", "pq_note": "no holdings file matched this scheme"}


class PQIndex:
    files_read, entries, warnings, root = 0, [], [], "data/holdings"


pqm.PortfolioIndex = PQIndex
pqm.fields_for_fund = lambda idx, name: dict(pqm.EMPTY_FIELDS)

hf = types.ModuleType("holdings_fetch")
hf.fetch_all = lambda *a, **k: None
rp = types.ModuleType("report")


def fake_export(df, path):
    df.to_excel(path, index=False)
    return True


rp.export_to_excel = fake_export
reg = types.ModuleType("amc_registry")
reg.AMCS = [{"key": "axis", "aliases": ["axis"], "mode": "manual"}, {"key": "nippon_india", "aliases": ["nippon"], "mode": "auto"}]


def amc_for(text):
    t = (text or "").lower()
    best, n = None, 0
    for a in reg.AMCS:
        for al in a["aliases"]:
            if al in t and len(al) > n:
                best, n = a, len(al)
    return best


reg.amc_for_fund_house = amc_for
sys.modules.update(fund_universe=fu, fetch_nav_data=fn, metrics=mt, benchmark=bm, portfolio_quality=pqm,
                   holdings_fetch=hf, report=rp, amc_registry=reg)

import shortlist
import holdings_import

work = tempfile.mkdtemp()
config.FUND_ATTRIBUTES_CSV = os.path.join(work, "none.csv")
config.EXPORT_EXCEL = True


def run(argv):
    return shortlist.main(argv)


# ---------------------------------------------------------------- one category
out1 = os.path.join(work, "one")
code = run(["small cap", "--output-dir", out1])
check("single category run exits 0", code == 0)
for f in ("shortlisted_funds.csv", "shortlisted_funds.xlsx", "ranked_funds.md", "run_log.txt"):
    check(f"output written: {f}", os.path.exists(os.path.join(out1, f)))
r1 = pd.read_csv(os.path.join(out1, "shortlisted_funds.csv"), dtype={"scheme_code": str})
check("duplicate scheme code collapsed to one row", (r1["scheme_code"] == "101").sum() == 1)
check("stale fund excluded", "111" not in r1["scheme_code"].tolist())
check("fund failing the hard filter excluded", "112" not in r1["scheme_code"].tolist())
check("ranks run 1..n among the ranked funds", sorted(r1.loc[r1["status"] == "RANKED", "rank"].astype(int)) ==
      list(range(1, int((r1["status"] == "RANKED").sum()) + 1)))
check("fund with most metrics missing is INSUFFICIENT_DATA with no rank",
      r1.set_index("scheme_code").loc["109", "status"] == "INSUFFICIENT_DATA" and pd.isna(r1.set_index("scheme_code").loc["109", "rank"]))
check("fund missing only benchmark metrics is still ranked on renormalised weights",
      r1.set_index("scheme_code").loc["108", "status"] == "RANKED" and abs(r1.set_index("scheme_code").loc["108", "score_coverage"] - 0.7) < 1e-6)
check("final scores are within 0..100", r1["final_score_0_100"].dropna().between(0, 100).all())
check("per-metric score and points columns are in the csv", "score_cagr_3y" in r1.columns and "contrib_max_drawdown" in r1.columns)
check("new metrics are computed and written", r1["downside_capture"].notna().any() and r1["quartile_consistency"].notna().any())
check("as-of / data flags columns exist", "last_nav_date" in r1.columns and "data_flags" in r1.columns)
log1 = open(os.path.join(out1, "run_log.txt")).read()
check("run log names the weights file and version", "weights.ini" in log1 and "version 2" in log1)
check("run log lists the stale-fund exclusion", "stale fund" in log1.lower())
check("run log lists hard-filter exclusions", "112" in log1)
md1 = open(os.path.join(out1, "ranked_funds.md"), encoding="utf-8").read()
check("markdown has method, weights, ranking and disclaimer", all(k in md1 for k in
      ("## Method", "### Weights", "## small cap", "not investment advice", "past returns do not guarantee")))
check("markdown shows raw value, score, weight and points for top funds",
      "| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |" in md1)
check("markdown states expense ratio is not scored", "Expense ratio is deliberately not scored" in md1)
check("markdown lists the not-ranked fund", "INSUFFICIENT_DATA" in md1)
check("low confidence is NOT flagged with 8+ ranked funds", "**LOW CONFIDENCE:**" not in md1)
check("single category -> no exploratory list", not os.path.exists(os.path.join(out1, "shortlisted_exploratory.csv")))

# ---------------------------------------------------------------- reproducibility
out1b = os.path.join(work, "one_b")
run(["small cap", "--output-dir", out1b])
a = pd.read_csv(os.path.join(out1, "shortlisted_funds.csv"))
b = pd.read_csv(os.path.join(out1b, "shortlisted_funds.csv"))
pd.testing.assert_frame_equal(a, b)
check("identical inputs give identical csv output", True)

# ---------------------------------------------------------------- several categories + exploratory
out2 = os.path.join(work, "two")
check("two --category options exit 0", run(["--category", "small cap", "--category", "mid cap", "--output-dir", out2]) == 0)
r2 = pd.read_csv(os.path.join(out2, "shortlisted_funds.csv"), dtype={"scheme_code": str})
check("both categories present with a group column", set(r2["group"]) == {"small cap", "mid cap"})
check("each category is ranked separately (rank 1 appears in both)",
      all((r2[(r2["group"] == g) & (r2["rank"] == 1)].shape[0] == 1) for g in ("small cap", "mid cap")))
check("exploratory cross-category csv written", os.path.exists(os.path.join(out2, "shortlisted_exploratory.csv")))
md2 = open(os.path.join(out2, "ranked_funds.md"), encoding="utf-8").read()
check("exploratory list is labelled exploratory in the report", "EXPLORATORY cross-category list" in md2 and "Exploratory only" in md2)
ex = pd.read_csv(os.path.join(out2, "shortlisted_exploratory.csv"))
check("exploratory list ranks funds from both categories together", ex["group"].iloc[0] == "EXPLORATORY cross-category" and len(ex) > len(r2[r2["group"] == "mid cap"]))
out3 = os.path.join(work, "all")
check("--all-categories exits 0", run(["--all-categories", "--output-dir", out3]) == 0)

# ---------------------------------------------------------------- weights file option and low confidence
alt = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights.ini")).read() \
    .replace("min_group_size = 8", "min_group_size = 50").replace("scoring_method = zscore", "scoring_method = percentile") \
    .replace("cagr_1y                    = 5", "cagr_1y = 0").replace("downside_capture           = 0", "downside_capture = 5")
alt_path = os.path.join(work, "alt.ini")
open(alt_path, "w").write(alt)
out4 = os.path.join(work, "alt")
check("--weights with another file works", run(["small cap", "--weights", alt_path, "--output-dir", out4]) == 0)
r4 = pd.read_csv(os.path.join(out4, "shortlisted_funds.csv"))
check("the new weights are used (downside capture now scored)", "score_downside_capture" in r4.columns and "score_cagr_1y" not in r4.columns)
check("small groups are flagged LOW CONFIDENCE", "**LOW CONFIDENCE:**" in open(os.path.join(out4, "ranked_funds.md"), encoding="utf-8").read())
config.apply_weights(os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights.ini"))

# ---------------------------------------------------------------- optional filters
config.FUND_ATTRIBUTES_CSV = os.path.join(work, "attrs.csv")
pd.DataFrame({"scheme_code": [str(c) for c in SMALL], "aum_cr": [900] * 5 + [100] * 5}).to_csv(config.FUND_ATTRIBUTES_CSV, index=False)
config.MIN_AUM_CR = 500
out5 = os.path.join(work, "attr")
run(["small cap", "--output-dir", out5])
r5 = pd.read_csv(os.path.join(out5, "shortlisted_funds.csv"), dtype={"scheme_code": str})
check("optional AUM filter drops funds below the minimum", not set(r5["scheme_code"]) & {"106", "107", "108", "109", "110"})
config.MIN_AUM_CR = None
config.FUND_ATTRIBUTES_CSV = os.path.join(work, "none.csv")

# ---------------------------------------------------------------- exit codes
check("no arguments -> exit 2", run([]) == 2)
bad = os.path.join(work, "bad.ini")
open(bad, "w").write(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights.ini")).read().replace("cagr_3y                    = 15", "cagr_3y = 99"))
check("invalid weights file -> exit 2", run(["small cap", "--weights", bad, "--output-dir", work]) == 2)
check("missing weights file -> exit 2", run(["small cap", "--weights", "/no/file.ini"]) == 2)
check("unknown category -> exit 2", run(["banana", "--output-dir", work]) == 2)
check("no candidate funds -> exit 1", run(["nothing", "--output-dir", os.path.join(work, "empty")]) == 1)
check("bad --as-of-date -> exit 2", run(["small cap", "--as-of-date", "nonsense"]) == 2)
check("missing csv input -> exit 2", run(["nope.csv"]) == 2)
csv_in = os.path.join(work, "mine.csv")
pd.DataFrame({"scheme_code": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110]}).to_csv(csv_in, index=False)
check("csv of scheme codes works", run([csv_in, "--output-dir", os.path.join(work, "csv")]) == 0)
check("the config weights are restored after --weights runs", config.WEIGHTS_VERSION == "2")

# ---------------------------------------------------------------- holdings_import
hdir = os.path.join(work, "dl")
os.makedirs(hdir)


def make_xlsx(path, title):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([title])
    ws.append(["Monthly Portfolio Statement as on 30-Sep-2026"])
    wb.save(path)


make_xlsx(os.path.join(hdir, "a.xlsx"), "Axis Mutual Fund")
make_xlsx(os.path.join(hdir, "b.xlsx"), "Mystery Fund House")
with zipfile.ZipFile(os.path.join(hdir, "nippon_portfolio.zip"), "w") as z:
    z.writestr("x.xls", "data")
open(os.path.join(hdir, "notes.txt"), "w").write("hi")
dest = os.path.join(work, "holdings")
logs = []
done = holdings_import.import_files([os.path.join(hdir, n) for n in sorted(os.listdir(hdir))], dest, log=logs.append)
check("an Axis workbook goes to data/holdings/axis", os.path.exists(os.path.join(dest, "axis", "a.xlsx")))
check("an unrecognised workbook goes to unsorted and says so", os.path.exists(os.path.join(dest, "unsorted", "b.xlsx"))
      and any("not recognised" in l for l in logs))
check("a zip is sorted by its name", os.path.exists(os.path.join(dest, "nippon_india", "nippon_portfolio.zip")))
check("a non-Excel file is skipped", any("notes.txt" in l and "skipped" in l for l in logs))
logs.clear()
holdings_import.import_files([os.path.join(hdir, "a.xlsx")], dest, log=logs.append)
check("importing the same file twice does not duplicate it", any("already imported" in l for l in logs))
check("no arguments -> exit 2", holdings_import.main([]) == 2)

shutil.rmtree(work, ignore_errors=True)
print(f"\nAll {passed} checks passed")
