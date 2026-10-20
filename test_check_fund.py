"""Offline tests for check_fund.py (synthetic NAV data, synthetic AMFI file). Run: python test_check_fund.py"""
import contextlib
import io
import os
import sys
import tempfile
from datetime import date, timedelta

import numpy as np
import pandas as pd

import check_fund
import config
import mf_holdings_screener as mfs
import shortlist

TODAY = date.today()
CAT = "Equity Scheme - Small Cap Fund"
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def make_nav(drift, vol=0.04, years=7.0, end_age_days=1, seed=0):
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(TODAY - timedelta(days=end_age_days))
    idx = pd.bdate_range(end=end, periods=int(years * 252))
    nav = 100 * np.exp(np.cumsum(rng.normal(drift / 252, vol / np.sqrt(252), len(idx))))
    return pd.DataFrame({"date": idx, "nav": nav})


def navall(rows):
    lines = ["Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date", ""]
    last = None
    for code, isins, name, cat, d in rows:
        if cat != last:
            lines += [f"Open Ended Schemes({cat})", "", "Test Mutual Fund", ""]
            last = cat
        a, _, b = isins.partition(" ")
        lines.append(f"{code};{a};{b or '-'};{name};123.45;{d.strftime('%d-%b-%Y')}")
    return "\n".join(lines)


D = TODAY - timedelta(days=1)
OLD = TODAY - timedelta(days=400)
rows = [(str(100 + i), f"INF{i:03d}A01011", f"Peer{i} Small Cap Fund - Direct Plan - Growth", CAT, D) for i in range(12)]
rows += [
    ("200", "INF900A01011", "Zeta Small Cap Fund - Direct Plan - Growth", CAT, D),
    ("201", "INF901A01011", "Zeta Small Cap Fund - Direct Plan - Growth Option", CAT, OLD),   # stale twin
    ("300", "INF902A01011", "Omega Mid Cap Fund - Direct Plan - Growth", "Equity Scheme - Mid Cap Fund", D),
    ("301", "INF903A01011 INF903A01029", "Omega Mid Cap Fund - Direct Plan - Growth", "Equity Scheme - Mid Cap Fund", D),  # 2 ISINs
    ("400", "INF904A01011", "Sigma Flexi Cap Fund - Direct Plan - Growth", "Equity Scheme - Flexi Cap Fund", D),
    ("401", "INF905A01011", "Sigma Focus Fund - Direct Plan - Growth", "Equity Scheme - Focused Fund", D),
    ("402", "INF906A01011", "Sigma Focus Fund - Direct Plan - Growth", "Equity Scheme - Focused Fund", D),
    ("500", "INF907A01011", "Nifty 50 Index Fund - Direct Plan - Growth", "Other Scheme - Index Funds", D),
    ("600", "INF908A01011", "Alpha Large Cap Fund - Regular Plan - Growth", "Equity Scheme - Large Cap Fund", D),
]
TEXT = navall(rows)
# two ISINs in one field are separated the way parse_navall expects; rebuild through the real parser
INDEX = mfs.AmfiIndex(mfs.parse_navall(TEXT))

NAVS = {}
for i in range(12):
    NAVS[str(100 + i)] = make_nav(0.06 + 0.012 * i, seed=i)
NAVS["200"] = make_nav(0.20, seed=50)          # strong fund
NAVS["201"] = make_nav(0.10, seed=51, end_age_days=400)
NAVS["300"] = make_nav(0.12, seed=52)
NAVS["301"] = make_nav(0.12, seed=53)
NAVS["400"] = make_nav(0.01, seed=54)
NAVS["500"] = make_nav(0.12, seed=55)
NAVS["600"] = make_nav(0.1, seed=56)
BROKEN = {"401"}

# ---- stub the data layer --------------------------------------------------------------
def fake_nav(code, force_refresh=False):
    code = str(code)
    if code in BROKEN or code not in NAVS:
        raise RuntimeError("no data")
    return NAVS[code].copy()


def fake_meta(code):
    r = INDEX.by_code.get(str(code))
    return {"scheme_name": r["name"], "fund_house": "Test MF", "scheme_category": r["category"]} if r else {}


shortlist.get_nav_history = fake_nav
shortlist.get_scheme_meta = fake_meta
mfs.fetch_nav_data.get_nav_history = fake_nav
config.BENCHMARK_ENABLED = False
config.PORTFOLIO_QUALITY_ENABLED = False


# ---- name matching ---------------------------------------------------------------------
rec, notes = check_fund.resolve_fund(INDEX, "Peer3 small cap")
check("unique name resolves", rec["code"] == "103")
try:
    check_fund.resolve_fund(INDEX, "99999")
    check("unknown code raises", False)
except check_fund.FundLookupError as e:
    check("unknown code raises", "99999" in str(e))
rec, notes = check_fund.resolve_fund(INDEX, "100")
check("scheme code lookup", rec["code"] == "100")
rec, notes = check_fund.resolve_fund(INDEX, "zeta smallcap")
check("stale twin ignored, spacing tolerant", rec["code"] == "200" and any("stopped updating" in n for n in notes), str(notes))
rec, notes = check_fund.resolve_fund(INDEX, "omega mid cap")
check("two-ISIN twin loses the tie", rec["code"] == "300" and any("two ISINs" in n for n in notes), str(notes))
try:
    check_fund.resolve_fund(INDEX, "sigma focus")
    check("true ambiguity raises", False)
except check_fund.FundLookupError as e:
    check("true ambiguity lists codes", "401" in str(e) and "402" in str(e))
try:
    check_fund.resolve_fund(INDEX, "small cap")
    check("broad name is ambiguous", False)
except check_fund.FundLookupError as e:
    check("broad name is ambiguous", "fits" in str(e))
try:
    check_fund.resolve_fund(INDEX, "alpha large cap")
    check("regular plan not matched silently", False)
except check_fund.FundLookupError as e:
    check("regular-only fund explained", "Regular" in str(e) and "600" in str(e), str(e))
try:
    check_fund.resolve_fund(INDEX, "peer3 smal cap fnd")
    check("typo not found", False)
except check_fund.FundLookupError as e:
    check("typo gets suggestions or clear message", "no Direct-Growth" in str(e))

# ---- peer pool ---------------------------------------------------------------------------
fund = INDEX.by_code["100"]
pool, skipped, capped = check_fund.peer_pool(INDEX, fund)
codes = [r["code"] for r in pool]
check("fund first in pool", codes[0] == "100")
check("peers are same-category Direct-Growth only", set(codes) == {str(100 + i) for i in range(12)} | {"200"}, str(codes))
check("stale twin skipped from pool", [r["code"] for r in skipped] == ["201"])
pool, _, capped = check_fund.peer_pool(INDEX, fund, cap=5)
check("cap keeps fund and counts the rest", len(pool) == 5 and codes[0] == pool[0]["code"] and capped == 8, f"{len(pool)} {capped}")

# ---- end to end -----------------------------------------------------------------------------
res = check_fund.evaluate(INDEX.by_code["200"], INDEX)
check("strong fund evaluated", not res["nav_error"] and res["peer"] is not None, str(res["nav_error"]))
check("strong fund ranks first of 14", res["peer"]["rank"] == 1 and res["peer"]["size"] == 13, str(res["peer"]))
check("verdict is not REVIEW for the best fund", res["decision"]["verdict"] in (mfs.V_CONTINUE, mfs.V_WATCH), res["decision"]["verdict"])
txt = check_fund.render(res)
check("report names the fund and code", "Zeta Small Cap" in txt and "200" in txt)
check("report says it is not advice", "not a recommendation" in txt)
check("report states expense ratio is not used", "expense ratio is deliberately not used" in txt)
check("report has metric table with weights", "| Metric |" in txt and "Weight %" in txt)
check("report shows peer rank", "Rank **1 of 13**" in txt, txt[:1500])

weak = check_fund.evaluate(INDEX.by_code["400"], INDEX)
check("flexi cap fund is a peer-eligible category", weak["peer_mode"] == "too_few")
check("alone in its category -> no ranking, no crash", weak["peer"] is None and weak["decision"]["verdict"] in (mfs.V_WATCH, mfs.V_CONTINUE, mfs.V_REVIEW, mfs.V_NODATA))

idxf = check_fund.evaluate(INDEX.by_code["500"], INDEX)
check("index fund -> not eligible for peers", idxf["peer_mode"] == "not_eligible" and idxf["pool_size"] == 1)
check("index fund report explains it", "No like-for-like peer group" in check_fund.render(idxf))

broken = check_fund.evaluate(INDEX.by_code["401"], INDEX)
check("failed NAV fetch -> INSUFFICIENT DATA with message", broken["nav_error"] and broken["decision"]["verdict"] == mfs.V_NODATA)
check("failed fetch still renders", "NAV data problem" in check_fund.render(broken))

np_res = check_fund.evaluate(INDEX.by_code["200"], INDEX, with_peers=False)
check("--no-peers skips the group", np_res["peer_mode"] == "skipped" and np_res["pool_size"] == 1)

# 5-year rolling option flows into the report
config.ROLLING_WINDOW_YEARS = 5.0
r5 = check_fund.evaluate(INDEX.by_code["200"], INDEX)
check("rolling-years 5 labelled in report", "Rolling 5y windows positive" in check_fund.render(r5))
config.ROLLING_WINDOW_YEARS = 3.0


# ---- command line ------------------------------------------------------------------------------
def cli(*args):
    d = tempfile.mkdtemp()
    nav = os.path.join(d, "NAVAll.txt")
    with open(nav, "w", encoding="utf-8") as fh:
        fh.write(TEXT)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = check_fund.main(["--navall", nav, "--output-dir", os.path.join(d, "o"), *args])
    return rc, out.getvalue(), err.getvalue(), d


rc, out, err, d = cli("Zeta", "Small", "Cap")
check("CLI: words joined, exit 0", rc == 0, err[-300:])
docx_path = os.path.join(d, "o", "fund_check_200.docx")
check("CLI: report file written (.docx by default)", os.path.exists(docx_path))
check("CLI: no .md file by default", not os.path.exists(os.path.join(d, "o", "fund_check_200.md")))
try:
    import docx as _docx
except ImportError:
    print("SKIP docx content checks (python-docx not installed)")
else:
    _doc = _docx.Document(docx_path)
    _text = "\n".join(p.text for p in _doc.paragraphs)
    check("docx: title and screen result present", "Fund check: Zeta Small Cap" in _text and "Screen result" in _text)
    check("docx: metrics table present", len(_doc.tables) >= 1 and _doc.tables[0].cell(0, 0).text == "Metric")
    check("docx: no raw markdown markers", "**" not in _text)
rc, out, err, d = cli("Zeta Small Cap", "--format", "md")
check("CLI: --format md still writes Markdown", rc == 0 and os.path.exists(os.path.join(d, "o", "fund_check_200.md")))
rc, out, err, d = cli("small cap")
check("CLI: ambiguous -> exit 2", rc == 2 and "fits" in err)
rc, out, err, d = cli("Zeta Small Cap", "--rolling-years", "20")
check("CLI: bad --rolling-years -> exit 2", rc == 2)
rc, out, err, d = cli("401")
check("CLI: NAV failure -> exit 1", rc == 1, err[-200:])
rc, out, err, d = cli("Zeta Small Cap", "--weights", "nope.ini")
check("CLI: bad weights -> exit 2", rc == 2)
rc, out, err, d = cli("Zeta Small Cap", "--no-file", "--no-peers")
check("CLI: --no-file writes nothing", rc == 0 and not os.path.exists(os.path.join(d, "o")))

print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
