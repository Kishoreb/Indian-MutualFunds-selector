"""Offline tests for isin_verify.py (item 2) and its hook in cdsl_holdings_to_xls.py. Synthetic data only.
Run:  python test_isin_verify.py"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isin_verify as iv

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"ok  {name}")


rng = random.Random(7)
AL = iv.ALPHABET
HOUSES = ["Alpha", "Beta", "Gamma", "Delta", "Sigma", "Omega", "Zenith", "Orion", "Kappa", "Lambda"]
KINDS = ["Small Cap", "Mid Cap", "Large Cap", "Flexi Cap", "Value", "Focused", "Contra", "Index Nifty 50"]
funds = []                                       # (isin, printed name, AMFI name)
uni = {}
for h in HOUSES:
    for k in KINDS:
        isin = iv.make_valid("INF" + "".join(rng.choice(AL) for _ in range(8)))
        amfi = f"{h} {k} Fund - Direct Plan - Growth Option"
        uni[isin] = amfi
        funds.append((isin, f"AB1C -{h} {k} Fund -Direct Plan -Growth", amfi))
for k in range(4000):                            # background ISINs of other schemes
    uni[iv.make_valid("INF" + "".join(rng.choice(AL) for _ in range(8)))] = f"Filler{k} Fund - Direct Plan - Growth"

# ---- check digit and universe ---------------------------------------------------------------------------------
check("check digit: known valid ISIN (Infosys INE009A01021)", iv.checksum_ok("INE009A01021"))
check("check digit: one wrong character fails", not iv.checksum_ok("INE009A01022"))
check("make_valid produces a valid ISIN", all(iv.checksum_ok(i) for i in uni))
text = "\n".join(["Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date",
             "", "Open Ended Schemes(Equity Scheme - Small Cap Fund)", "", "Axis Mutual Fund", "",
             "1;INF846K01WO1;INF846K01WP9;Axis Small Cap Fund;Direct Plan;Growth Option;29.3;16-Oct-2026",
             "2;INF209K01XX1;-;Old Layout Fund - Direct Plan - Growth;11.0;16-Oct-2026"])
p = iv.parse_universe(text)
check("parse_universe: plan/option appended to the name, both ISIN columns read",
      p.get("INF846K01WO1") == "Axis Small Cap Fund - Direct Plan - Growth Option" and len(p) >= 1)

V = iv.IsinVerifier(uni, embedder=None)

# ---- clean reads ---------------------------------------------------------------------------------------------
check("clean reads of every fund are 'ok'", all(V.verify_mf(i, n).status == "ok" for i, n, _ in funds))

# ---- OCR corruptions: repaired to the right ISIN, never to a wrong one ------------------------------------------
conf = {"0": "O", "O": "0", "1": "I", "I": "1", "5": "S", "S": "5", "8": "B", "B": "8", "2": "Z", "Z": "2"}
wrong = fixed = other = 0
for isin, name, _ in funds:
    for _ in range(25):
        s = list(isin)
        pos = [i for i in range(2, 12) if s[i] in conf]
        k = rng.choice([1, 2])
        if len(pos) < k:
            continue
        for i in rng.sample(pos, k):
            s[i] = conf[s[i]]
        bad = "".join(s)
        if bad in uni:
            continue
        r = V.verify_mf(bad, name)
        if r.status == "repaired":
            fixed, wrong = fixed + (r.isin == isin), wrong + (r.isin != isin)
        else:
            other += 1
check("look-alike corruptions: no repair ever lands on a wrong ISIN", wrong == 0)
check("look-alike corruptions: at least 90% repaired", fixed >= 0.9 * (fixed + other))
wrong = fixed = 0
for isin, name, _ in funds:
    for _ in range(10):
        s = list(isin)
        s[rng.randrange(3, 11)] = rng.choice(AL)
        bad = "".join(s)
        if bad in uni or bad == isin:
            continue
        r = V.verify_mf(bad, name)
        if r.status == "repaired":
            fixed, wrong = fixed + (r.isin == isin), wrong + (r.isin != isin)
check("one arbitrary wrong character: never repaired wrongly, mostly repaired", wrong == 0 and fixed > 100)
i0, n0, a0 = funds[3]
r = V.verify_mf(i0 + "X", n0)
check("a stray 13th character is dropped and repaired", r.status == "repaired" and r.isin == i0)
r = V.verify_mf(i0[:7] + i0[8:], n0)
check("a dropped character is restored and repaired", r.status == "repaired" and r.isin == i0)
check("repair note says what happened", "not in AMFI" in r.note and "Verify" in r.note)

# ---- the name is the tie-breaker (this is what the check digit alone cannot do) --------------------------------
base = iv.make_valid("INF123456AB")
twin = None
for ch in AL:                                    # a second valid ISIN one character away
    t = base[:5] + ch + base[6:]
    if t != base and iv.checksum_ok(t):
        twin = t
        break
u2 = {base: "Orion Value Fund - Direct Plan - Growth Option", twin: "Orion Small Cap Fund - Direct Plan - Growth Option"}
V2 = iv.IsinVerifier(u2, embedder=None)
bad = base[:5] + "#" + base[6:]
r = V2.verify_mf(base[:5] + "Q" + base[6:], "XX -Orion Value Fund -Direct Plan -Growth")
check("two real ISINs equally near: the printed name picks the right one", r.status == "repaired" and r.isin == base)
r = V2.verify_mf(base[:5] + "Q" + base[6:], "XX -Orion Small Cap Fund -Direct Plan -Growth")
check("... and the other name picks the other one", r.status == "repaired" and r.isin == twin)

# ---- conflicts, suggestions, unknowns -------------------------------------------------------------------------
r = V.verify_mf(funds[0][0], funds[5][1])
check("valid ISIN but a different fund's name -> conflict, ISIN NOT changed",
      r.status == "conflict" and r.isin == funds[0][0] and "belongs to" in r.note)
check("conflict names the fund the statement text looks like", funds[5][0] in r.note and r.suggestion == funds[5][0])
r = V.verify_mf("INF000000009", funds[7][1])
check("ISIN not in the list and nothing near it: suggested by name, NOT applied",
      r.status == "suggested" and r.isin == "INF000000009" and r.suggestion == funds[7][0] and "NOT applied" in r.note)
r = V.verify_mf("INF000000009", "ZZ -Totally Different Pharma Fund -Direct Growth")
check("nothing fits at all -> unknown", r.status == "unknown")
check("renamed fund (mild name difference) stays ok with a note",
      V.verify_mf(funds[1][0], "AB -Alpha Mid Cap Opportunities Fund -Direct Plan -Growth").status in ("ok", "conflict"))

# ---- shares ----------------------------------------------------------------------------------------------------
stocks = {"INE009A01021", "INE002A01018", "INE467B01029"}
VS = iv.IsinVerifier({}, stocks, embedder=None)
check("share ISIN in the list: ok", VS.verify_stock("INE009A01021").status == "ok")
r = VS.verify_stock("INE0O9A01021")
check("damaged share ISIN with one look-alike repaired against the list", r.status == "repaired" and r.isin == "INE009A01021")
check("without a share list the old check-digit behaviour is untouched",
      iv.IsinVerifier({}, None).verify_stock("INE009A01021").status == "ok"
      and iv.IsinVerifier({}, None).verify_stock("INE009A01022").status == "unknown")
check("an unrelated bad share ISIN is not guessed", VS.verify_stock("INE777Z01029").status in ("ok", "unknown"))

# ---- row application -------------------------------------------------------------------------------------------
rows = [{"Scheme Name": funds[2][1], "ISIN": funds[2][0], "Check": "OK"},
        {"Scheme Name": funds[3][1], "ISIN": funds[3][0].replace(funds[3][0][5], "?" if False else funds[3][0][5]), "Check": "OK"},
        {"Scheme Name": funds[4][1], "ISIN": funds[9][0], "Check": "OK"}]
s = list(funds[3][0]); pos = [i for i in range(2, 12) if s[i] in conf][0]; s[pos] = conf[s[pos]]
rows[1]["ISIN"] = "".join(s)
V3 = iv.IsinVerifier(uni, embedder=None)
iv.apply_to_mf_rows(rows, V3)
check("apply: clean row untouched", rows[0]["Check"] == "OK" and rows[0]["ISIN"] == funds[2][0])
check("apply: repaired row corrected and flagged", rows[1]["ISIN"] == funds[3][0] and rows[1]["Check"].startswith("ISIN repaired"))
check("apply: conflicting row flagged, ISIN kept", rows[2]["ISIN"] == funds[9][0] and "CONFLICT" in rows[2]["Check"])
rows2 = [{"Scheme Name": funds[3][1], "ISIN": "".join(s), "Check": "CHECK: units x NAV does not equal valuation"}]
iv.apply_to_mf_rows(rows2, V3)
check("apply: existing Check notes are kept", rows2[0]["Check"].startswith("CHECK: units") and "repaired" in rows2[0]["Check"])
check("summary line", "repaired" in iv.summarize(V3) and "conflict" in iv.summarize(V3))

# ---- stand-alone command on a holdings workbook --------------------------------------------------------------------
import openpyxl
with tempfile.TemporaryDirectory() as td:
    navall = os.path.join(td, "NAVAll.txt")
    lines = ["Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date", "",
             "Open Ended Schemes(Equity Scheme - Mid Cap Fund)", "", "Test Mutual Fund", ""]
    for n, (isin, _, amfi) in enumerate(funds[:20]):
        lines.append(f"{n + 1};{isin};-;{amfi};10.0;16-Oct-2026")
    open(navall, "w").write("\n".join(lines))
    hold = os.path.join(td, "x-MF.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Scheme Name", "ISIN", "Folio No.", "Valuation (Rs)"])
    s = list(funds[0][0]); pos = [i for i in range(2, 12) if s[i] in conf][0]; s[pos] = conf[s[pos]]
    ws.append([funds[0][1], "".join(s), "1", 100.0])
    ws.append([funds[1][1], funds[1][0], "2", 100.0])
    ws.append([funds[2][1], funds[8][0], "3", 100.0])
    ws.append(["TOTAL", None, None, 300.0])
    wb.save(hold)
    out = os.path.join(td, "o.xlsx")
    iv.main([hold, "--navall", navall, "-o", out])
    w = openpyxl.load_workbook(out).active
    rows_ = [[c.value for c in r] for r in w.iter_rows()]
    check("CLI: repaired row corrected, status column written", rows_[1][1] == funds[0][0] and rows_[1][4] == "repaired")
    check("CLI: ok row and conflict row labelled", rows_[2][4] == "ok" and rows_[3][4] == "conflict")
    out2 = os.path.join(td, "o2.xlsx")
    iv.main([hold, "--navall", navall, "-o", out2, "--no-repair"])
    w2 = openpyxl.load_workbook(out2).active
    check("CLI --no-repair keeps the read ISIN", w2.cell(row=2, column=2).value != funds[0][0])

    # the hook in cdsl_holdings_to_xls.py (needs pdfplumber, which that script needs anyway)
    try:
        import cdsl_holdings_to_xls as cdsl
    except ImportError as exc:
        print("skip  cdsl hook (", exc, ")")
    else:
        v = cdsl.load_verifier(navall)
        check("cdsl hook: verifier built from NAVAll.txt", v is not None and funds[0][0] in v.universe)
        check("cdsl hook: --no-verify path / missing file -> None, extraction unchanged",
              cdsl.load_verifier(os.path.join(td, "missing.txt")) is None)
        check("cdsl hook: still has its own check-digit repair", cdsl.choose_isin([funds[0][0]])[0] == funds[0][0])

print(f"\nAll {passed} checks passed")
