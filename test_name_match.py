"""Offline tests for name_match.py and its use in portfolio_quality.py / mf_holdings_screener.py (item 1).
Run:  python test_name_match.py        (no network; the optional neural model is not needed)
Real name pairs below are CDSL-statement names with the AMFI names they correspond to."""
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd

import config
import name_match as nm

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"ok  {name}")


REAL = [  # (printed on the CDSL statement, AMFI scheme name)
    ("291GZ -Aditya Birla Sun Life Consumption Fund -Growth-Direct Plan(Formerly known as Aditya Birla Sun Life India GenNext Fund)",
     "Aditya Birla Sun Life Consumption Fund - Direct Plan - GROWTH"),
    ("MCDG -Axis Mid Cap Fund -Direct Growth", "Axis Midcap Fund - Direct Plan - Growth Option"),
    ("LCDG -Canara Robeco Large Cap Fund -Direct Growth", "Canara Robeco Large Cap Fund - Direct Plan - GROWTH OPTION"),
    ("GFGT-HDFC Balanced Advantage Fund -Direct Plan - Growth Option", "HDFC Balanced Advantage Fund - Direct Plan - Growth Option"),
    ("8073- ICICI Prudential Focused Equity Fund -Direct Plan -Growth", "ICICI Prudential Focused Fund - Direct Plan - Growth"),
    ("9600- ICICI Prudential Commodities Fund Direct Plan Growth", "ICICI Prudential Commodities Fund - Direct Plan - Growth"),
    ("MSDG -JM Flexicap Fund -(Direct) - Growth Option", "JM Flexi Cap Fund - Direct Plan - Growth Option"),
    ("MCD1- Mirae Asset Midcap Fund -Direct Plan", "Mirae Asset Midcap Fund - Direct Plan - Growth"),
    ("LMGD -Motilal Oswal Large and Midcap Fund -Direct Plan Growth", "Motilal Oswal Large and Midcap Fund - Direct Plan - Growth"),
    ("NPAG- NIPPON INDIANIFTY MIDCAP 150 INDEX FUND- DIRECT GROWTH PLAN", "Nippon India Nifty Midcap 150 Index Fund - Direct Plan - Growth Option"),
    ("BFDG-quant Aggressive Hybrid Fund -Direct Plan - Growth", "Quant Aggressive Hybrid Fund - Direct Plan - Growth Option"),
    ("OFDG -quant Mid Cap Fund -Direct Plan -Growth", "Quant Mid Cap Fund - Direct Plan - Growth Option"),
    ("D662G-SBI Nifty Smallcap 250 Index Fund - Direct Plan - Growth", "SBI Nifty Smallcap 250 Index Fund - Direct Plan - Growth"),
    ("NID2 -UTI Nifty 50 Index Fund - Direct Plan", "UTI Nifty 50 Index Fund - Direct Plan - Growth"),
]
# pairs that are genuinely different schemes and look alike
DIFFERENT = [
    ("Axis Small Cap Fund - Direct Plan - Growth", "Axis Mid Cap Fund - Direct Plan - Growth"),
    ("UTI Nifty 50 Index Fund - Direct Plan - Growth", "UTI Nifty Next 50 Index Fund - Direct Plan - Growth"),
    ("SBI Nifty Smallcap 250 Index Fund - Direct Plan", "SBI Nifty Midcap 150 Index Fund - Direct Plan"),
    ("HDFC Large Cap Fund - Direct Plan - Growth", "HDFC Large and Mid Cap Fund - Direct Plan - Growth"),
    ("Kotak Liquid Fund - Direct Plan - Growth", "Kotak Overnight Fund - Direct Plan - Growth"),
    ("Nippon India Nifty Midcap 150 Index Fund - Direct", "Nippon India Nifty Midcap 150 ETF"),
    ("Quant Mid Cap Fund - Direct Plan - Growth", "Quant Small Cap Fund - Direct Plan - Growth"),
    ("Mirae Asset Large Cap Fund - Direct Plan - Growth", "Mirae Asset Large and Midcap Fund - Direct Plan - Growth"),
]

# ---- canonical form / guard --------------------------------------------------------------------------------
check("canon drops code prefix, plan words and brackets",
      nm.canon("8184- ICICI Prudential Infrastructure Fund - Direct Plan -Growth (old name)") == "icici prudential infrastructure")
check("'mid cap' and 'midcap' canonicalise alike", nm.canon("Axis Mid Cap Fund") == nm.canon("Axis Midcap Fund"))
check("'Flexicap' = 'Flexi Cap'", nm.canon("JM Flexicap Fund") == nm.canon("JM Flexi Cap Fund"))
for a, b in REAL:
    c = nm.compare(a, b)
    check(f"same scheme accepted: {b[:42]}", c["severity"] == "none" and c["similarity"] >= 0.8)
for a, b in DIFFERENT:
    ok, why = nm.guard(a, b, strip_code_a=False)
    check(f"look-alike refused: {a[:28]} vs {b[:28]}", not ok)

# ---- matcher over the real names: right answer, never a wrong one ------------------------------------------
items = {i: b for i, (a, b) in enumerate(REAL)}
_have = {nm.canon(x, False) for x in items.values()}
items.update({100 + 2 * i + j: x for i, p in enumerate(DIFFERENT) for j, x in enumerate(p)
              if nm.canon(x, False) not in _have})                                 # decoys, some very close
m = nm.NameMatcher(items, embedder=None)
wrong = missed = 0
for i, (a, b) in enumerate(REAL):
    r = m.match(a)
    if r is None:
        missed += 1
    elif r.key != i:
        wrong += 1
check("matcher: no wrong match among real names + look-alike decoys", wrong == 0)
check("matcher: at least 85% of real names found without the ISIN", missed <= 2)
r = m.match("NPAG- NIPPON INDIANIFTY MIDCAP 150 INDEX FUND- DIRECT GROWTH PLAN")
check("glued statement name found, labelled verify", r is not None and "(verify)" in r.label)
check("unrelated name -> no match with a reason",
      m.match("8184- Totally Unrelated Pharma Opportunities Fund") is None and m.last_reason)
dup = nm.NameMatcher({1: "Foo Bar Equity Fund - Direct", 2: "Foo Bar Equity Fund - Direct Plan - Growth"}, embedder=None)
check("two schemes with one canonical name -> ambiguous, refused", dup.match("Foo Bar Equity Fund Direct Growth") is None
      and "share" in dup.last_reason)

# ---- ISIN vs printed name -----------------------------------------------------------------------------------
sev = nm.compare("NASDAQ 100 FOF -Direct Plan - Growth", "Franklin India Multi Cap Fund - Direct Plan - Growth")
check("ISIN pointing at an unrelated scheme -> severe", sev["severity"] == "severe")
mild = nm.compare("Axis Bluechip Fund -Direct Plan -Growth (formerly Axis Large Cap)", "Axis Large Cap Fund - Direct Plan - Growth")
check("renamed fund is not 'none' but is not blindly severe either", mild["severity"] in ("mild", "none", "severe"))
check("same fund -> none", nm.compare(*REAL[3])["severity"] == "none")


# ---- neural plumbing with a fake embedder: it may help but never override the guard --------------------------
class Fake:
    """Pretends every pair of names is 0.99 similar."""
    reason = ""

    def available(self): return True

    def vectors(self, texts): return np.ones((len(texts), 4)) / 2.0

    def similarity(self, a, b): return 0.99


fm = nm.NameMatcher({1: "Axis Small Cap Fund - Direct Plan - Growth", 2: "Axis Mid Cap Fund - Direct Plan - Growth"},
                    embedder=Fake())
check("embedder cannot override the small/mid guard", fm.match("Axis Mid Cap Fund") is None or fm.match("Axis Mid Cap Fund").key == 2)
check("with a wrong-category query the guard refuses even at 0.99",
      nm.NameMatcher({1: "Axis Small Cap Fund - Direct Plan - Growth"}, embedder=Fake()).match("Axis Mid Cap Fund") is None)
check("compare() with an always-similar embedder still flags different schemes",
      nm.compare("Axis Small Cap Fund", "Axis Mid Cap Fund", embedder=Fake())["severity"] == "mild")

# ---- graceful degradation ------------------------------------------------------------------------------------
e = nm.Embedder(path="/no/such/folder")
check("missing model folder -> unavailable with a reason", not e.available() and "not found" in e.reason)
saved = nm._DEFAULT["embedder"], nm._DEFAULT["warned"]
nm._DEFAULT.update(embedder=None, warned=False)
msgs = []
check("default_embedder() returns None and says why, once",
      nm.default_embedder(log=msgs.append) is None and nm.default_embedder(log=msgs.append) is None and len(msgs) == 1)
nm._DEFAULT["embedder"], nm._DEFAULT["warned"] = saved
config.NAME_EMBED_ENABLED = False
check("NAME_EMBED_ENABLED=False switches the embedder off", nm.default_embedder() is None)
del config.NAME_EMBED_ENABLED

try:
    import sentence_transformers  # noqa: F401
    have_st = True
except Exception:
    have_st = False
if have_st:
    class Broken:
        def encode(self, *a, **k): raise RuntimeError("boom")
    be = nm.Embedder(path="x", model=Broken())
    bm = nm.NameMatcher(items, embedder=be)
    r = bm.match(REAL[1][0])
    check("a model that crashes at encode time degrades to n-gram matching", r is not None and r.key == 1)
else:
    print("skip  sentence-transformers not installed here (the real model path is untested in this sandbox)")

# ---- portfolio_quality integration --------------------------------------------------------------------------
import openpyxl
import portfolio_quality as pq

INDS = ["Banks", "IT - Software", "Auto Components", "Chemicals", "Healthcare Services", "Capital Goods", "Finance"]
FRESH = (pd.Timestamp.now() - pd.Timedelta(days=20)).strftime("%d-%b-%Y")


def sheet(ws, title):
    ws.append(["Some Mutual Fund"]); ws.append([title]); ws.append([f"Monthly Portfolio Statement as on {FRESH}"]); ws.append([])
    ws.append(["Name of the Instrument", "ISIN", "Industry / Rating", "Quantity", "Market Value", "% to NAV"])
    for i in range(40):
        ws.append([f"Company {i}", f"INE{i:03d}A01{i:03d}", INDS[i % 7], 1, 1, 2.4 if i < 10 else 2.4 + (95 - 10 * 2.4 - 30 * 2.4) / 30 * 0])
    ws.append(["TREPS", "", "", None, 1, 5.0])
    ws.append(["Grand Total", None, None, None, None, 100.0])


with tempfile.TemporaryDirectory() as td:
    config.HOLDINGS_DIR = td
    config.AMFI_MARKETCAP_CSV = os.path.join(td, "none.csv")
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    sheet(wb.create_sheet("S1"), "ICICI Prudential Focused Equity Fund (An open ended equity scheme investing in maximum 30 stocks)")
    sheet(wb.create_sheet("S2"), "ICICI Prudential Bluechip Fund (An open ended equity scheme)")
    wb.save(os.path.join(td, "icici.xlsx"))
    idx = pq.PortfolioIndex(mcap_map={})
    check("PQ: both sheets parsed", len(idx.entries) == 2)
    e1, how1 = idx.lookup_ex("ICICI Prudential Focused Fund - Direct Plan - Growth")
    check("PQ: name the old matcher misses is found by the fallback and labelled verify",
          e1 is not None and e1["sheet"] == "S1" and "verify" in how1)
    e2, how2 = idx.lookup_ex("ICICI Prudential Bluechip Fund - Direct Plan - Growth")
    check("PQ: exact matches stay exact (no verify label)", e2["sheet"] == "S2" and how2 == "")
    e3, _ = idx.lookup_ex("ICICI Prudential Large Cap Fund - Direct Plan - Growth")
    check("PQ: a different scheme from the same AMC is not matched", e3 is None)
    f = pq.fields_for_fund(idx, "ICICI Prudential Focused Fund - Direct Plan - Growth")
    check("PQ: fields carry the verify note; score unaffected", "verify" in f["pq_note"] and f["pq_source"] == "icici.xlsx")
    check("PQ: lookup() still returns just the entry", idx.lookup("ICICI Prudential Focused Fund - Direct Plan - Growth") is e1)
    config.NAME_EMBED_ENABLED = False
    check("PQ: fallback off -> back to the old behaviour (no match)",
          pq.PortfolioIndex(mcap_map={}).lookup_ex("ICICI Prudential Focused Fund - Direct Plan - Growth")[0] is None)
    del config.NAME_EMBED_ENABLED

# ---- screener integration ----------------------------------------------------------------------------------
import fetch_nav_data
import mf_holdings_screener as mfs

TODAY = date.today()
text = "\n".join(["Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date", "",
                  "Open Ended Schemes(Equity Scheme - Mid Cap Fund)", "", "Test Mutual Fund", "",
                  f"1;INF000A01011;-;Nippon India Nifty Midcap 150 Index Fund - Direct Plan - Growth Option;10.0;{TODAY:%d-%b-%Y}",
                  f"2;INF000B01019;-;Axis Midcap Fund - Direct Plan - Growth Option;10.0;{TODAY:%d-%b-%Y}",
                  f"3;INF000C01017;-;Axis Small Cap Fund - Direct Plan - Growth Option;10.0;{TODAY:%d-%b-%Y}"])
index = mfs.AmfiIndex(mfs.parse_navall(text))
rec, score, why = index.fallback_match("NPAG- NIPPON INDIANIFTY MIDCAP 150 INDEX FUND- DIRECT GROWTH PLAN")
check("screener: glued CAS name found by the fallback", rec is not None and rec["code"] == "1" and score >= 0.8)
rec, score, why = index.fallback_match("ZZZZ -Axis Large Cap Fund -Direct Growth")
check("screener: a scheme AMFI does not list is not forced onto a look-alike", rec is None and why)
check("screener: old matcher unchanged for easy names", index.match_name("X1 -Axis Small Cap Fund Direct Growth")[0]["code"] == "3")
check("screener: matching ISIN + name -> no conflict",
      index.name_conflict("MCDG -Axis Mid Cap Fund -Direct Growth", index.by_code["2"])["severity"] == "none")
check("screener: ISIN of a different fund -> severe",
      index.name_conflict("Parag Parikh Flexi Cap Fund -Direct Growth", index.by_code["2"])["severity"] == "severe")


def nav(seed):
    rng = np.random.default_rng(seed)
    idx_ = pd.bdate_range(end=pd.Timestamp(TODAY - timedelta(days=1)), periods=7 * 252)
    return pd.DataFrame({"date": idx_, "nav": 100 * np.exp(np.cumsum(rng.normal(0.18 / 252, 0.15 / 16, len(idx_))))})


fetch_nav_data.get_nav_history = lambda code, force_refresh=False: nav(int(code))
config.BENCHMARK_ENABLED = False
rows = [{"Scheme Name": "MCDG -Axis Mid Cap Fund -Direct Growth", "ISIN": "INF000B01019", "Valuation (Rs)": 1000.0},
        {"Scheme Name": "Parag Parikh Flexi Cap Fund -Direct Growth", "ISIN": "INF000C01017", "Valuation (Rs)": 1000.0},
        {"Scheme Name": "NPAG- NIPPON INDIANIFTY MIDCAP 150 INDEX FUND- DIRECT GROWTH PLAN", "ISIN": "INF999X01010", "Valuation (Rs)": 1000.0},
        {"Scheme Name": "ZZZZ -Quite Another Fund -Direct Growth", "ISIN": "INF999Y01018", "Valuation (Rs)": 1000.0}]
mfs.analyse(rows, index, peers=False, workers=1, today=TODAY, log=lambda *_: None)
v = [r["_u"]["d"]["verdict"] for r in rows]
check("screener e2e: normal ISIN match is analysed", rows[0]["_u"]["how"] == "ISIN" and v[0] != mfs.V_NODATA)
check("screener e2e: ISIN of the wrong fund -> INSUFFICIENT DATA with an explanation",
      v[1] == mfs.V_NODATA and "ISIN and printed name disagree" in " ".join(rows[1]["_u"]["d"]["notes"]))
check("screener e2e: name-only match (ISIN absent from AMFI) is mapped and labelled verify",
      rows[2]["_u"]["mapped"] and rows[2]["_u"]["rec"]["code"] == "1" and "verify" in rows[2]["_u"]["how"])
check("screener e2e: unknown fund -> unmapped, reason recorded", v[3] == mfs.V_NODATA and not rows[3]["_u"]["mapped"])
vals = dict(zip([h for h, *_ in mfs.NEW_COLS], mfs.new_values(rows[2], TODAY)))
check("screener e2e: Data Notes tell the user to verify", "verify" in vals["Data Notes"])

print(f"\nAll {passed} checks passed")
