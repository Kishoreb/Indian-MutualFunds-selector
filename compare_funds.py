#!/usr/bin/env python3
"""
compare_funds.py
----------------
Compare several mutual funds side by side (typically 2 to 12) and write the result to an Excel file.

    python compare_funds.py                       # reads the funds from input.xls (name or scheme code, one per row)
    python compare_funds.py -i my_funds.xlsx      # reads them from another file
    python compare_funds.py "Axis Small Cap" "Nippon India Small Cap" "Bank of India Small Cap" "ITI Small Cap"
    python compare_funds.py 125354 118778 "Quant Small Cap" -o my_comparison.xlsx
    python compare_funds.py "Axis Small Cap" "Quant Small Cap" --no-peers      # faster: only your funds are compared
    python compare_funds.py "Axis Small Cap" "SBI Small Cap" --navall NAVAll.txt --rolling-years 5

INPUT FILE: one fund per row in the fund column (headed Fund / Scheme / Name / Code / ISIN, else the first column);
a header row is optional. Each cell is a fund name or an AMFI scheme code; blanks and repeats are ignored. Works with
.xls (needs xlrd), .xlsx, .csv, or an HTML/text file saved as .xls. Funds on the command line override the file.

Give each fund as ONE argument: a name (quote it if it has spaces) or an AMFI scheme code. Names are matched the
way check_fund.py matches them (Direct-Growth schemes in AMFI's NAVAll file); an ambiguous or unknown name stops
the run and lists the candidates, so you can pass a scheme code instead.

WHAT YOU GET (one .xlsx, default output/compare_funds_<date>.xlsx)
  Comparison  one column per fund, one row per metric, with the weights.ini weight of each metric, the screen
              result, rank / percentile / score within the fund's FULL category (not just among your funds),
              category medians, red / amber / green notes, and whether the fund passes the shortlist hard filters.
              Best value in each row is shaded green and worst red, but only among funds of the SAME category.
  Funds       the same numbers as plain values, one row per fund (easy to sort and filter)
  Notes       method, weights file and version, benchmarks, peer groups, problems, risk disclaimer

DIFFERENCES FROM shortlist.py
  * No hard filter ever removes one of your funds; the filters are only reported.
  * Ranks come from the whole category (all Direct-Growth peers with 3+ years of history), so 5 or 6 funds are
    not scored only against each other. With --no-peers the ranking is among your funds only and says so.
  * Index, fund-of-funds, sectoral/thematic and debt funds have no fair peer group: they get no rank or score,
    just their metrics, benchmark comparison and screen result.

It is a screen of PAST NAV data, not advice: expense ratio is deliberately not used, and exit load, fund-manager
changes, tax and your own goals are not considered.

Exit status: 0 file written; 1 none of the funds had usable NAV data; 2 bad command line, weights file, fund not
found / ambiguous, AMFI file unavailable, or openpyxl missing.
"""

import argparse
import math
import os
import sys
from datetime import date

import pandas as pd

import benchmark
import check_fund
import config
import data_checks
import mf_holdings_screener as mfs
import report_md
import shortlist
import weights_loader

MIN_FUNDS = 2
HIGHLIGHT_BEST = "C6EFCE"
HIGHLIGHT_WORST = "FFC7CE"


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _clean(v):
    return check_fund._clean(v)


def metric_labels():
    labels = dict(report_md.LABELS)
    labels["rolling_positive_pct"] = f"Rolling {config.ROLLING_WINDOW_YEARS:g}y windows positive"
    labels["volatility"] = "Volatility (annualised, whole history)"
    dd = config.DRAWDOWN_WINDOW_YEARS
    labels["max_drawdown"] = (f"Maximum drawdown (worst fall, last {dd:g}y)" if dd else "Maximum drawdown (whole history)")
    return labels


def is_lower_better(metric):
    return metric in check_fund.LOWER_BETTER or report_md.DIRECTION.get(metric) == "lower"


def number_format(metric):
    if metric in ("benchmark_excess_return", "jensen_alpha"):
        return "+0.00%;-0.00%;0.00%"
    if metric in report_md.PCT or metric == "volatility":
        return "0.0%"
    if metric == "portfolio_quality":
        return "0"
    return "0.00"


def group_key(rec):
    return data_checks.norm_category(rec["category"])


def bullets(items):
    return "\n".join(f"• {x}" for x in items)


# --------------------------------------------------------------------------------------
# Resolving the funds
# --------------------------------------------------------------------------------------
def resolve_all(index, queries):
    """-> (records in the order given, notes, problems). A problem is a message for a query that did not resolve."""
    records, notes, problems, seen = [], [], [], {}
    for q in queries:
        try:
            rec, n = check_fund.resolve_fund(index, q)
        except check_fund.FundLookupError as exc:
            problems.append(f"'{q}': {exc}")
            continue
        if rec["code"] in seen:
            notes.append(f"'{q}' is the same scheme as '{seen[rec['code']]}' ({rec['code']}); counted once.")
            continue
        seen[rec["code"]] = q
        records.append(rec)
        notes += n
    return records, notes, problems


# --------------------------------------------------------------------------------------
# Evaluating the funds
# --------------------------------------------------------------------------------------
def evaluate_group(index, recs, with_peers, refresh, workers, today):
    """Metrics, peer ranking, score and screen result for the selected funds of ONE category.
    Returns (results {code: dict}, info {peers, skipped_stale, capped, failed, benchmarks, basis})."""
    first = recs[0]
    eligible = bool(mfs.peer_eligible(first["category"]))
    pool = list(recs)
    info = {"category": mfs.short_category(first["category"]), "peer_count": 0, "skipped_stale": 0, "capped": 0,
            "failed": 0, "benchmarks": [], "eligible": eligible,
            "basis": ("category" if (eligible and with_peers) else "your funds" if eligible else "none")}
    if eligible and with_peers:
        peers_pool, skipped, _ = check_fund.peer_pool(index, first, cap=10 ** 6)
        have = {r["code"] for r in pool}
        others = [r for r in peers_pool[1:] if r["code"] not in have]
        room = max(0, config.MAX_FUNDS_TO_SCAN - len(pool))
        info["capped"] = max(0, len(others) - room)
        info["skipped_stale"] = len(skipped)
        pool += others[:room]

    got = mfs.fetch_many([r["code"] for r in pool], refresh, workers, lambda *_: None)
    ok = [r for r in pool if not isinstance(got.get(r["code"]), Exception)]
    info["failed"] = len(pool) - len(ok)
    results = {}
    mdf = pd.DataFrame()
    if ok:
        fl = pd.DataFrame([{"scheme_code": r["code"], "scheme_name_hint": r["name"]} for r in ok])
        fl.attrs["category_key"] = benchmark.category_key(first["category"])
        mdf = shortlist.build_metrics_table(fl, force_refresh=False, log=lambda s: None)
        info["benchmarks"] = list(shortlist.build_metrics_table.benchmarks)
        mdf["scheme_code"] = mdf["scheme_code"].astype(str)
    info["peer_count"] = max(0, len(mdf) - len(recs)) if eligible and with_peers else 0

    ranking, scored = {}, None
    if eligible and len(mdf) > 1:
        ranking = mfs.rank_peers(mdf.to_dict("records"))
        old_enough = mdf[mdf["history_years"] >= mfs.REVIEW_RULES["min_peer_history_years"]].reset_index(drop=True)
        if len(old_enough):
            scored = shortlist.score_and_rank(old_enough)
            scored["scheme_code"] = scored["scheme_code"].astype(str)

    for rec in recs:
        code = rec["code"]
        facts = {"zero_value": False, "mapped": True, "nav_error": None,
                 "category_short": mfs.short_category(rec["category"]), "peer": None, "peer_unranked": False}
        res = {"rec": rec, "target": {}, "peer": None, "score": None, "coverage": None, "status": None,
               "fails": None, "nav_error": None, "basis": info["basis"], "group": group_key(rec)}
        err = got.get(code)
        trow = mdf[mdf["scheme_code"] == code] if len(mdf) else mdf
        if isinstance(err, Exception) or trow.empty:
            res["nav_error"] = str(err)[:100] if isinstance(err, Exception) else "metrics could not be computed from the NAV data"
            facts["nav_error"] = res["nav_error"]
            res["decision"] = mfs.decide(facts)
            results[code] = res
            continue
        target = trow.iloc[0].to_dict()
        last = _clean(target.get("last_nav_date"))
        target["nav_age_days"] = (today - pd.Timestamp(last).date()).days if last is not None else None
        res["target"] = target
        peer = ranking.get(code)
        res["peer"] = peer
        facts.update(peer=peer, peer_unranked=bool(ranking) and peer is None)
        for k in ("history_years", "nav_age_days", "last_nav_date", "cagr_3y", "cagr_5y", "max_drawdown",
                  "benchmark_excess_return", "rolling_beat_benchmark_pct", "benchmark_name"):
            facts[k] = _clean(target.get(k))
        res["decision"] = mfs.decide(facts)
        if scored is not None:
            srow = scored[scored["scheme_code"] == code]
            if len(srow):
                s0 = srow.iloc[0]
                res["score"] = _clean(s0["final_score_0_100"])
                res["coverage"] = _clean(s0["score_coverage"])
                res["status"] = s0["status"]
        _, reasons = shortlist.apply_hard_filters(trow.copy(), return_reasons=True, log=lambda s: None)
        res["fails"] = reasons.get(code, [])
        results[code] = res
    return results, info


# --------------------------------------------------------------------------------------
# Excel output
# --------------------------------------------------------------------------------------
def _best_worst(values, lower):
    """Indexes of the best and the worst numeric value (None, None when fewer than two numbers or all equal)."""
    nums = [(v, i) for i, v in enumerate(values) if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))]
    if len(nums) < 2:
        return None, None
    lo, hi = min(nums), max(nums)
    if lo[0] == hi[0]:
        return None, None
    return (lo[1], hi[1]) if lower else (hi[1], lo[1])


def write_excel(path, recs, results, groups_info, notes_lines):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    labels = metric_labels()
    weights = config.SCORE_WEIGHTS
    n = len(recs)
    codes = [r["code"] for r in recs]
    R = [results[c] for c in codes]
    groups = [r["group"] for r in R]
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="1F4E78")
    sect_fill = PatternFill("solid", fgColor="D9E2F3")
    mixed = len(set(groups)) > 1

    wb = Workbook()
    ws = wb.active
    ws.title = "Comparison"
    ws.append([f"Mutual fund comparison - {date.today():%d %b %Y}"])
    ws["A1"].font = Font(bold=True, size=14)
    sub = ("Past-data screen, not investment advice. Shading: best (green) and worst (red) value in each row among "
           "funds of the same category.")
    if mixed:
        sub += " These funds are from DIFFERENT categories, so they are not directly comparable."
    ws.append([sub])
    ws["A2"].alignment = Alignment(wrap_text=False)
    ws.append([])
    ws.append(["Metric", "Weight %"] + [r["name"] for r in recs])
    HR = 4
    for c in range(1, n + 3):
        cell = ws.cell(row=HR, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center" if c > 1 else "left")
        cell.border = border
    ws.row_dimensions[HR].height = 48

    def section(title):
        ws.append([title])
        r = ws.max_row
        for c in range(1, n + 3):
            ws.cell(row=r, column=c).fill = sect_fill
        ws.cell(row=r, column=1).font = Font(bold=True)

    def put(label, values, fmt=None, weight=None, wrap=False, highlight=None, fills=None):
        ws.append([label, weight] + [("n/a" if v is None else v) for v in values])
        r = ws.max_row
        ws.cell(row=r, column=1).font = Font(bold=False)
        for c in range(1, n + 3):
            cell = ws.cell(row=r, column=c)
            cell.border = border
            if c > 2:
                cell.alignment = Alignment(horizontal="left" if wrap else "center", vertical="top" if wrap else "center",
                                           wrap_text=wrap)
                if fmt and isinstance(cell.value, (int, float)):
                    cell.number_format = fmt
        if highlight is not None:
            for key in set(groups):
                idx = [i for i, g in enumerate(groups) if g == key]
                if len(idx) < 2:
                    continue
                best, worst = _best_worst([values[i] for i in idx], highlight)
                if best is not None:
                    ws.cell(row=r, column=3 + idx[best]).fill = PatternFill("solid", fgColor=HIGHLIGHT_BEST)
                    ws.cell(row=r, column=3 + idx[worst]).fill = PatternFill("solid", fgColor=HIGHLIGHT_WORST)
        if fills:
            for i, colour in enumerate(fills):
                if colour:
                    ws.cell(row=r, column=3 + i).fill = PatternFill("solid", fgColor=colour)
                    ws.cell(row=r, column=3 + i).font = Font(bold=True)
        return r

    def tgt(i, key):
        return _clean(R[i]["target"].get(key))

    section("Fund")
    put("AMFI scheme code", [r["code"] for r in recs])
    put("Fund house", [r.get("amc") or None for r in recs])
    put("AMFI category", [mfs.short_category(r["category"]) for r in recs])
    put("Last NAV date", [str(tgt(i, "last_nav_date") or recs[i].get("nav_date") or "")[:10] or None for i in range(n)])
    put("NAV history (years)", [tgt(i, "history_years") for i in range(n)], "0.0")
    plan = [("Not Direct-Growth" if ("direct" not in r["name"].lower() or any(w in r["name"].lower() for w in ("idcw", "dividend")))
             else None) for r in recs]
    if any(plan):
        put("Plan note", plan)

    section("Screen result and ranking")
    verdicts = [R[i]["decision"]["verdict"] for i in range(n)]
    put("Screen result", [check_fund.V_TEXT.get(v, v) for v in verdicts], wrap=True,
        fills=[mfs.VERDICT_COLOURS.get(v) for v in verdicts])
    put("Evidence used (confidence)",
        [(f"{R[i]['decision']['evidence']} ({R[i]['decision']['confidence']})"
          if R[i]["decision"]["confidence"] not in ("-", "n/a") else None) for i in range(n)], wrap=True)

    def rank_text(i):
        p = R[i]["peer"]
        if not p:
            return None
        where = "your funds" if R[i]["basis"] == "your funds" else "category"
        return f"{p['rank']} of {p['size']} ({where})"
    put("Rank", [rank_text(i) for i in range(n)])
    put("Percentile (100 = best)", [R[i]["peer"]["percentile"] if R[i]["peer"] else None for i in range(n)], "0")
    put("Score 0-100", [R[i]["score"] for i in range(n)], "0.0", highlight=False)
    put("Weight measured", [R[i]["coverage"] for i in range(n)], "0%")
    put("Passes shortlist hard filters",
        [(None if R[i]["fails"] is None else ("Yes" if not R[i]["fails"] else "No: " + ", ".join(R[i]["fails"])))
         for i in range(n)], wrap=True)

    section("Metrics (best green, worst red within a category)")
    for m in check_fund.METRIC_ROWS:
        vals = [tgt(i, m) for i in range(n)]
        if all(v is None for v in vals):
            continue
        w = round(weights.get(m, 0.0) * 100, 1)
        put(labels.get(m, m), vals, number_format(m), weight=(w if w else "not scored"), highlight=is_lower_better(m))

    peer_rows = [("Category median 3-year CAGR", "median_3y", "0.0%"), ("Category median 5-year CAGR", "median_5y", "0.0%"),
                 ("Category median max drawdown", "median_dd", "0.0%")]
    if any(R[i]["peer"] for i in range(n)):
        section("Category medians (the peer group each fund was ranked in)")
        for label, key, fmt in peer_rows:
            put(label, [R[i]["peer"].get(key) if R[i]["peer"] else None for i in range(n)], fmt)
        put("Funds in that ranking", [R[i]["peer"]["size"] if R[i]["peer"] else None for i in range(n)], "0")

    section("What stands out")
    for title, key in (("Red flags", "red"), ("Cautions", "amber"), ("In its favour", "green"), ("Notes", "notes")):
        texts = [bullets(R[i]["decision"][key]) or None for i in range(n)]
        if any(texts):
            r = put(title, texts, wrap=True)
            lines = 0
            for t in texts:
                if t:
                    lines = max(lines, sum(max(1, math.ceil(len(x) / 30)) for x in t.split("\n")))
            ws.row_dimensions[r].height = min(409, 14 * lines + 6)
    nav_err = [R[i]["nav_error"] for i in range(n)]
    if any(nav_err):
        put("NAV data problem", nav_err, wrap=True)

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 11
    for i in range(n):
        ws.column_dimensions[get_column_letter(3 + i)].width = 30
    ws.freeze_panes = ws.cell(row=HR + 1, column=3)

    # ---- flat sheet
    wf = wb.create_sheet("Funds")
    cols = ["Fund", "Scheme code", "Fund house", "Category", "Last NAV date", "History (yrs)"] + \
           [labels.get(m, m) for m in check_fund.METRIC_ROWS] + \
           ["Rank", "Funds ranked", "Percentile", "Score 0-100", "Weight measured", "Screen result"]
    wf.append(cols)
    for c in range(1, len(cols) + 1):
        cell = wf.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for i, rec in enumerate(recs):
        row = [rec["name"], rec["code"], rec.get("amc"), mfs.short_category(rec["category"]),
               str(tgt(i, "last_nav_date") or "")[:10] or None, tgt(i, "history_years")]
        row += [tgt(i, m) for m in check_fund.METRIC_ROWS]
        p = R[i]["peer"]
        row += [p["rank"] if p else None, p["size"] if p else None, p["percentile"] if p else None,
                R[i]["score"], R[i]["coverage"], check_fund.V_TEXT.get(verdicts[i], verdicts[i])]
        wf.append(row)
        r = wf.max_row
        for j, m in enumerate(check_fund.METRIC_ROWS):
            wf.cell(row=r, column=7 + j).number_format = number_format(m)
        k = 7 + len(check_fund.METRIC_ROWS)
        wf.cell(row=r, column=k + 2).number_format = "0"
        wf.cell(row=r, column=k + 3).number_format = "0.0"
        wf.cell(row=r, column=k + 4).number_format = "0%"
    wf.column_dimensions["A"].width = 52
    for c in range(2, len(cols) + 1):
        wf.column_dimensions[get_column_letter(c)].width = 15
    wf.column_dimensions[get_column_letter(len(cols))].width = 30
    wf.freeze_panes = "B2"
    wf.row_dimensions[1].height = 48

    # ---- notes
    wn = wb.create_sheet("Notes")
    for line in notes_lines:
        wn.append([line])
    wn.column_dimensions["A"].width = 150
    for row in wn.iter_rows():
        row[0].alignment = Alignment(wrap_text=True, vertical="top")
    wn["A1"].font = Font(bold=True, size=13)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)


def build_notes(recs, results, groups_info, resolve_notes, problems, with_peers):
    L = ["How to read this comparison", ""]
    L.append(f"Created {date.today():%d %b %Y}. Weights file: {os.path.basename(str(config.WEIGHTS_FILE))} "
             f"(version {config.WEIGHTS_VERSION}); missing-data policy {config.MISSING_DATA_POLICY}; scoring method "
             f"{config.SCORING_METHOD}; coverage floor {config.MIN_SCORE_COVERAGE:.0%}.")
    L.append("Weights %: " + ", ".join(f"{m}={w * 100:g}" for m, w in config.SCORE_WEIGHTS.items() if w > 0))
    L.append(f"Risk-free rate {config.RISK_FREE_RATE:.1%}; rolling window {config.ROLLING_WINDOW_YEARS:g} years; "
             f"drawdown window "
             f"{('%g years' % config.DRAWDOWN_WINDOW_YEARS) if config.DRAWDOWN_WINDOW_YEARS else 'whole history'}.")
    L.append("Returns are computed from Direct-Growth NAVs (mfapi.in / AMFI). Expense ratio is deliberately not scored.")
    L.append("")
    L.append("Ranking and score")
    for key, info in groups_info.items():
        if info["basis"] == "category":
            bits = [f"{info['peer_count']} category peers fetched"]
            if info["failed"]:
                bits.append(f"{info['failed']} NAV downloads failed")
            if info["skipped_stale"]:
                bits.append(f"{info['skipped_stale']} skipped (NAV stopped updating)")
            if info["capped"]:
                bits.append(f"{info['capped']} not scanned (config.MAX_FUNDS_TO_SCAN)")
            L.append(f"- {info['category']}: ranked against the whole category; " + ", ".join(bits) + ".")
        elif info["basis"] == "your funds":
            L.append(f"- {info['category']}: --no-peers was used, so rank and score are relative to YOUR funds only "
                     f"and exaggerate small differences; run without --no-peers for a category ranking.")
        else:
            L.append(f"- {info['category']}: no like-for-like peer group (index, fund-of-funds, sectoral/thematic or debt "
                     f"funds), so no rank or score; judged on benchmark and absolute returns only.")
    L.append("Funds with 'n/a' in a row could not be measured (too little history, no benchmark, ...); nothing is estimated.")
    L.append("Shading compares funds only within the same category; the colour does not mean good or bad in absolute terms.")
    L.append("")
    benches = sorted({b.strip() for info in groups_info.values() for b in info["benchmarks"]})
    if benches:
        L.append("Benchmarks used (an index-fund proxy trails the true Total Return Index by about its expense ratio, so "
                 "excess return is flattered a little):")
        L += [f"- {b}" for b in benches]
        L.append("")
    if resolve_notes or problems:
        L.append("Fund matching")
        L += [f"- {x}" for x in resolve_notes]
        L += [f"- PROBLEM: {x}" for x in problems]
        L.append("")
    L.append("Limits")
    L.append(report_md.DISCLAIMER)
    L.append("This comparison does not know your goal, time horizon, tax position or exit load, and it does not look at "
             "fund-manager changes or the funds' current portfolios.")
    return L


# --------------------------------------------------------------------------------------
# Input file
# --------------------------------------------------------------------------------------
_HEADER_WORDS = ("fund", "scheme", "name", "code", "isin")
DEFAULT_INPUT = "input.xls"


def _read_table(path):
    """Read an .xls/.xlsx/.csv (or an HTML/text file saved with an .xls name) as a header-less table of strings."""
    ext = os.path.splitext(path)[1].lower()
    attempts = []
    if ext == ".csv":
        attempts.append(lambda: pd.read_csv(path, header=None, dtype=str, keep_default_na=False))
    attempts.append(lambda: pd.read_excel(path, header=None, dtype=str, keep_default_na=False))
    attempts.append(lambda: pd.read_html(path, header=None)[0].astype(str))
    attempts.append(lambda: pd.read_csv(path, header=None, dtype=str, keep_default_na=False, sep=None, engine="python"))
    last = None
    for fn in attempts:
        try:
            return fn()
        except ImportError as exc:
            last = exc
            if "xlrd" in str(exc):
                raise SystemExit("reading .xls needs xlrd:  pip install xlrd   (or save the file as .xlsx)")
        except Exception as exc:  # noqa: BLE001 - try the next format
            last = exc
    raise SystemExit(f"could not read '{path}' as Excel, HTML or CSV ({last})")


def read_input_funds(path):
    """Fund names / AMFI scheme codes from the input file: every non-empty cell in the fund column.

    The fund column is the one headed fund / scheme / name / code / isin (first match), else the first column.
    A header row is skipped; blank cells and repeated entries are ignored. Codes read as 125354.0 become 125354.
    """
    if not os.path.isfile(path):
        raise SystemExit(f"input file not found: {path}")
    df = _read_table(path)
    if df.empty:
        raise SystemExit(f"input file '{path}' is empty")
    col, start = 0, 0
    first = [str(v).strip().lower() for v in df.iloc[0].tolist()]
    for i, v in enumerate(first):
        if any(w in v for w in _HEADER_WORDS) and not v.replace(".", "").isdigit():
            col, start = i, 1
            break
    else:
        if first and first[0] and not first[0].replace(".", "").isdigit() and len(df) > 1 \
                and any(w in first[0] for w in _HEADER_WORDS):
            start = 1
    out, seen = [], set()
    for v in df.iloc[start:, col].tolist():
        v = str(v).strip()
        if not v or v.lower() in ("nan", "none"):
            continue
        if v.endswith(".0") and v[:-2].isdigit():
            v = v[:-2]
        if v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    if not out:
        raise SystemExit(f"no fund names or codes found in '{path}'")
    return out


# Command line
# --------------------------------------------------------------------------------------
def _parse_args(argv):
    ap = argparse.ArgumentParser(prog="compare_funds.py",
                                 description="Compare several mutual funds side by side and write an Excel file.")
    ap.add_argument("funds", nargs="*", help="optional: funds on the command line (a quoted name or an AMFI scheme code); "
                                             "when none are given they are read from the input file")
    ap.add_argument("-i", "--input", default=None,
                    help=f"Excel/CSV file listing the funds, one per row (name or scheme code); default {DEFAULT_INPUT}")
    ap.add_argument("-o", "--output", help="output .xlsx (default: output/compare_funds_<date>.xlsx)")
    ap.add_argument("--navall", help="AMFI NAVAll.txt you saved yourself (when the download is blocked)")
    ap.add_argument("--no-peers", action="store_true", help="skip the category peers (faster; ranks among your funds only)")
    ap.add_argument("--refresh", action="store_true", help="re-download NAV data instead of using the cache")
    ap.add_argument("--weights", help="weights file (default: weights.ini next to config.py)")
    ap.add_argument("--rolling-years", type=float, default=None, help="rolling-return window, e.g. 3 or 5")
    ap.add_argument("--workers", type=int, default=4, help="parallel NAV downloads (default 4)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.weights:
            config.apply_weights(args.weights)
    except weights_loader.WeightsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    err = shortlist.set_rolling_years(args.rolling_years)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    if args.workers < 1:
        print("ERROR: --workers must be at least 1", file=sys.stderr)
        return 2
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("ERROR: writing Excel needs openpyxl:  pip install openpyxl", file=sys.stderr)
        return 2

    if args.funds and args.input:
        print("ERROR: give funds on the command line OR with --input, not both", file=sys.stderr)
        return 2
    if args.funds:
        funds = args.funds
    else:
        path = args.input or DEFAULT_INPUT
        try:
            funds = read_input_funds(path)
        except SystemExit as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"Read {len(funds)} fund(s) from {path}", file=sys.stderr)

    try:
        text = mfs.load_navall(args.navall, args.refresh, log=lambda s: print(s, file=sys.stderr))
    except (OSError, SystemExit) as exc:
        print(f"ERROR: could not get AMFI's NAVAll.txt ({exc})", file=sys.stderr)
        return 2
    index = mfs.AmfiIndex(mfs.parse_navall(text))
    if not index.records:
        print("ERROR: the NAVAll file has no scheme rows", file=sys.stderr)
        return 2

    recs, resolve_notes, problems = resolve_all(index, funds)
    if problems:
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 2
    if len(recs) < MIN_FUNDS:
        print(f"ERROR: give at least {MIN_FUNDS} different funds to compare (got {len(recs)}). "
              f"For one fund use check_fund.py.", file=sys.stderr)
        return 2

    today = date.today()
    by_group = {}
    for r in recs:
        by_group.setdefault(group_key(r), []).append(r)
    results, groups_info = {}, {}
    for key, rs in by_group.items():
        print(f"Fetching and scoring '{mfs.short_category(rs[0]['category'])}' ({len(rs)} of your funds) ...", file=sys.stderr)
        res, info = evaluate_group(index, rs, not args.no_peers, args.refresh, args.workers, today)
        results.update(res)
        groups_info[key] = info

    if all(results[r["code"]]["nav_error"] for r in recs):
        print("ERROR: no NAV data could be fetched for any of the funds.", file=sys.stderr)
        return 1

    out = args.output or os.path.join("output", f"compare_funds_{today:%Y%m%d}.xlsx")
    if not out.lower().endswith(".xlsx"):
        out += ".xlsx"
    notes = build_notes(recs, results, groups_info, resolve_notes, problems, not args.no_peers)
    try:
        write_excel(out, recs, results, groups_info, notes)
    except OSError as exc:
        print(f"ERROR: could not write {out} ({exc}). Is it open in Excel?", file=sys.stderr)
        return 2

    print(f"\nComparison of {len(recs)} funds written to {os.path.abspath(out)}\n")
    for r in recs:
        x = results[r["code"]]
        p = x["peer"]
        rank = f"rank {p['rank']}/{p['size']}" if p else "no rank"
        score = f", score {x['score']:.1f}" if x["score"] is not None else ""
        print(f"  {r['name'][:60]:<60} {check_fund.V_TEXT.get(x['decision']['verdict'], ''):<32} {rank}{score}")
    failed = [r["name"] for r in recs if results[r["code"]]["nav_error"]]
    if failed:
        print("\nNo NAV data for: " + "; ".join(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
