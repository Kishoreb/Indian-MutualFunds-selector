#!/usr/bin/env python3
"""
check_fund.py
-------------
Look at ONE mutual fund. Give a name (or an AMFI scheme code) and get a report on how the fund
has done: its metrics, how it compares with its category peers and its benchmark, the weights.ini
score and rank, whether it passes the shortlist filters in config.py, and a screen result built from the
same rules as mf_holdings_screener.py.

    python check_fund.py "Axis Small Cap"
    python check_fund.py 125354                              # AMFI scheme code
    python check_fund.py "Nippon India Small Cap" --no-peers  # faster: skip the category comparison
    python check_fund.py "Parag Parikh Flexi Cap" --rolling-years 5 --weights my_weights.ini
    python check_fund.py "Axis Small Cap" --navall NAVAll.txt  # AMFI file you saved in a browser

WHAT THE SCREEN RESULT MEANS (and does not)
  NO RED FLAGS            nothing in the past data stands out against the fund
  MIXED                   one area of concern (or two milder cautions)
  CONCERNS                several red flags, or the scheme looks closed/merged (stale NAV)
  INSUFFICIENT DATA       too little history, no NAV data, or not mapped
It is a screen of PAST NAV data. It is NOT advice and cannot say whether you should invest: it does
not know your goal, time horizon, tax position or other holdings, and it does not use the expense
ratio (excluded by design), exit load, fund-manager changes or the fund's current portfolio.

HOW THE FUND IS FOUND
  The name is matched against AMFI's NAVAll.txt (Direct + Growth schemes). If several schemes fit, the
  list is shown and you pick one by passing its scheme code. Schemes whose NAV stopped updating are
  ignored when a live one fits, and a scheme with two ISINs (an IDCW/dividend option that AMFI labels
  Growth) loses a tie with a one-ISIN twin; both are said in the report.

PEERS
  All open-ended Direct-Growth schemes in the same AMFI category with a current NAV (capped at
  config.MAX_FUNDS_TO_SCAN, alphabetically). Hard filters are NOT applied to peers, so you see where the
  fund really stands. Index funds, fund-of-funds, sectoral/thematic and debt categories are not fair peer
  groups (the screener's list), so those funds are judged against their benchmark / absolute returns only.

Exit status: 0 report written; 1 the fund was found but its NAV data could not be fetched;
2 bad command line, bad weights file, fund not found or ambiguous, AMFI file unavailable.
"""

import argparse
import difflib
import os
import re
import sys
from datetime import date

import pandas as pd

import benchmark
import config
import data_checks
import mf_holdings_screener as mfs
import report_docx
import report_md
import shortlist
import weights_loader

V_TEXT = {
    mfs.V_CONTINUE: "NO RED FLAGS in this data",
    mfs.V_WATCH: "MIXED - one area of concern",
    mfs.V_REVIEW: "CONCERNS - several red flags",
    mfs.V_NODATA: "INSUFFICIENT DATA",
}
STALE_TWIN_DAYS = 30          # a candidate whose NAV is this much older than the newest candidate is "stale"
MAX_LISTED = 15               # candidates shown when a name is ambiguous

# metrics shown in the comparison table, in this order
METRIC_ROWS = ["cagr_1y", "cagr_3y", "cagr_5y", "volatility", "risk_return_ratio", "sortino_ratio",
               "rolling_positive_pct", "sip_xirr", "max_drawdown", "benchmark_excess_return",
               "rolling_beat_benchmark_pct", "downside_capture", "jensen_alpha", "beta",
               "quartile_consistency", "portfolio_quality"]
LOWER_BETTER = {"volatility", "downside_capture", "beta"}


class FundLookupError(Exception):
    """The query matched nothing, or too much. The message says what to do next."""


# --------------------------------------------------------------------------------------
# Finding the fund
# --------------------------------------------------------------------------------------
_DROP = {"direct", "plan", "growth", "option", "regular", "scheme", "the", "fund", "mutual", "and"}


def name_tokens(text):
    """Words of a scheme name that identify it (plan/option/'fund' words dropped, '&' = 'and' dropped)."""
    s = re.sub(r"\([^)]*\)", " ", str(text or "").lower()).replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return [t for t in s.split() if t not in _DROP]


def _describe(r):
    nav = "n/a" if r.get("nav") is None else f"{r['nav']:.4g}"
    return (f"{r['code']}  {r['name']}  [{r.get('amc') or 'AMC n/a'}; {mfs.short_category(r['category'])}; "
            f"NAV {nav} on {r.get('nav_date') or 'n/a'}; {len(r['isins'])} ISIN(s)]")


def _direct_growth_records(index):
    return [r for r in index.records if mfs.is_direct_growth(r["name"])]


def find_matches(index, query):
    """Direct-Growth schemes whose name contains all the words of the query (or the same letters
    without spaces, so 'midcap' finds 'Mid Cap')."""
    q = name_tokens(query)
    if not q:
        return []
    qs = "".join(q)
    out = []
    for r in _direct_growth_records(index):
        t = name_tokens(r["name"])
        if set(q) <= set(t) or qs in "".join(t):
            out.append(r)
    return out


def suggestions(index, query, n=5):
    target = " ".join(name_tokens(query))
    scored = sorted(((difflib.SequenceMatcher(None, target, " ".join(name_tokens(r["name"]))).ratio(), r)
                     for r in _direct_growth_records(index)), key=lambda x: -x[0])
    return [r for s, r in scored[:n] if s >= 0.5]


def resolve_fund(index, query):
    """-> (record, notes). Raises FundLookupError when nothing fits or the choice is not clear."""
    q = str(query or "").strip()
    if not q:
        raise FundLookupError("give a fund name or an AMFI scheme code")
    if q.isdigit():
        rec = index.by_code.get(q)
        if rec is None:
            raise FundLookupError(f"scheme code {q} is not in AMFI's NAVAll file (it may be closed or mistyped)")
        return rec, [f"Found by scheme code {q}."]

    matches = find_matches(index, q)
    if not matches:
        other = [r for r in index.records if not mfs.is_direct_growth(r["name"])
                 and set(name_tokens(q)) <= set(name_tokens(r["name"]))]
        msg = f"no Direct-Growth scheme matches '{q}'."
        if other:
            msg += (" Only Regular / IDCW plans match: " + "; ".join(_describe(r) for r in other[:5]) +
                    ". To check one anyway, pass its scheme code.")
        else:
            sug = suggestions(index, q)
            if sug:
                msg += " Did you mean:\n  " + "\n  ".join(_describe(r) for r in sug)
        raise FundLookupError(msg)

    notes = []
    key = name_tokens(q)
    if len(matches) > 1:
        exact = [r for r in matches if name_tokens(r["name"]) == key]
        if exact:
            matches = exact
    if len(matches) > 1:                                  # drop schemes whose NAV stopped updating
        dated = [r["nav_date"] for r in matches if r.get("nav_date")]
        if dated:
            newest = max(dated)
            live = [r for r in matches if r.get("nav_date") and (newest - r["nav_date"]).days <= STALE_TWIN_DAYS]
            if live and len(live) < len(matches):
                gone = [r for r in matches if r not in live]
                notes.append("Ignored scheme(s) whose NAV stopped updating: " +
                             "; ".join(f"{r['code']} (last NAV {r.get('nav_date')})" for r in gone) + ".")
                matches = live
    if len(matches) > 1:                                  # an IDCW option mislabelled Growth has 2 ISINs
        single = [r for r in matches if len(r["isins"]) < 2]
        if single and len(single) < len(matches):
            gone = [r for r in matches if r not in single]
            notes.append("Ignored scheme(s) with two ISINs, which is how AMFI lists a dividend (IDCW) option even "
                         "when the name says Growth: " + "; ".join(r["code"] for r in gone) + ".")
            matches = single
    if len(matches) == 1:
        notes.insert(0, f"Matched '{q}' to {matches[0]['name']} ({matches[0]['code']}).")
        return matches[0], notes
    shown = sorted(matches, key=lambda r: r["name"])[:MAX_LISTED]
    more = len(matches) - len(shown)
    raise FundLookupError(
        f"'{q}' fits {len(matches)} schemes; pass the scheme code of the one you mean:\n  " +
        "\n  ".join(_describe(r) for r in shown) + (f"\n  ... and {more} more; add more words to the name" if more else ""))


# --------------------------------------------------------------------------------------
# Peers
# --------------------------------------------------------------------------------------
def peer_pool(index, rec, cap=None, stale_days=None):
    """-> (records [the fund first, then peers], skipped_stale, number_capped)."""
    cap = config.MAX_FUNDS_TO_SCAN if cap is None else cap
    stale_days = config.STALE_NAV_DAYS if stale_days is None else stale_days
    ckey = data_checks.norm_category(rec["category"])
    pool = {}
    for r in index.records:
        if r["open_ended"] and data_checks.norm_category(r["category"]) == ckey and mfs.is_direct_growth(r["name"]):
            pool.setdefault(r["code"], r)
    pool[rec["code"]] = rec                                # the fund itself is always in the group
    skipped = []
    dates = [r["nav_date"] for r in pool.values() if r.get("nav_date")]
    if dates:
        newest = max(dates)
        for code, r in list(pool.items()):
            if code != rec["code"] and r.get("nav_date") and (newest - r["nav_date"]).days > stale_days:
                skipped.append(r)
                del pool[code]
    others = sorted((r for c, r in pool.items() if c != rec["code"]), key=lambda r: r["name"])
    capped = 0
    if len(others) > max(0, cap - 1):
        capped = len(others) - max(0, cap - 1)
        others = others[:max(0, cap - 1)]
    return [rec] + others, skipped, capped


# --------------------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------------------
def _clean(v):
    """None for NaN / NaT / None so the screener's rules (which test `is not None`) behave."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def comparison_rows(target, peers_df, weights, rolling_years, drawdown_years):
    """[(metric, label, fund value, peer median, 'better than x% of peers', weight %)]."""
    labels = dict(report_md.LABELS)
    labels["rolling_positive_pct"] = f"Rolling {rolling_years:g}y windows positive"
    labels["volatility"] = "Volatility (annualised, whole history)"
    labels["max_drawdown"] = (f"Maximum drawdown (worst fall, last {drawdown_years:g}y)" if drawdown_years
                              else "Maximum drawdown (whole history)")
    rows = []
    for m in METRIC_ROWS:
        v = _clean(target.get(m))
        pv = pd.Series(dtype=float)
        if peers_df is not None and len(peers_df) and m in peers_df.columns:
            pv = pd.to_numeric(peers_df[m], errors="coerce").dropna()
        if v is None and pv.empty:
            continue
        med = float(pv.median()) if len(pv) else None
        better = None
        if v is not None and len(pv) >= 3:
            wins = int((pv > v).sum()) if m in LOWER_BETTER or report_md.DIRECTION.get(m) == "lower" else int((pv < v).sum())
            ties = int((pv == v).sum())
            better = 100.0 * (wins + 0.5 * ties) / len(pv)
        rows.append((m, labels.get(m, m), v, med, better, round(weights.get(m, 0.0) * 100, 1)))
    return rows


def evaluate(rec, index, with_peers=True, refresh=False, workers=4, today=None):
    """Everything the report needs. Network access happens only through mf_holdings_screener.fetch_many and
    shortlist.build_metrics_table (both go through fetch_nav_data)."""
    today = today or date.today()
    res = {"rec": rec, "today": today, "nav_error": None, "peer": None, "peer_unranked": False,
           "scored": None, "target": {}, "shortlist_fails": None, "flags": [], "benchmarks": [],
           "comparison": [], "pool_size": 1, "peers_failed": 0, "skipped_stale": [], "capped": 0,
           "peer_mode": "none", "notes": [], "peer_count": 0}
    eligible = bool(with_peers and mfs.peer_eligible(rec["category"]))
    if not with_peers:
        res["peer_mode"] = "skipped"
    elif not eligible:
        res["peer_mode"] = "not_eligible"
    pool, skipped, capped = peer_pool(index, rec) if eligible else ([rec], [], 0)
    res.update(pool_size=len(pool), skipped_stale=skipped, capped=capped)

    got = mfs.fetch_many([r["code"] for r in pool], refresh, workers, lambda *_: None)
    err = got.get(rec["code"])
    facts = {"zero_value": False, "mapped": True, "nav_error": None,
             "category_short": mfs.short_category(rec["category"]), "peer": None, "peer_unranked": False}
    if isinstance(err, Exception):
        res["nav_error"] = str(err)[:120]
        facts["nav_error"] = res["nav_error"]
        res["decision"] = mfs.decide(facts)
        return res

    ok = [r for r in pool if not isinstance(got.get(r["code"]), Exception)]
    fl = pd.DataFrame([{"scheme_code": r["code"], "scheme_name_hint": r["name"]} for r in ok])
    fl.attrs["category_key"] = benchmark.category_key(rec["category"])
    mdf = shortlist.build_metrics_table(fl, force_refresh=False, log=lambda s: None)
    res["benchmarks"] = list(shortlist.build_metrics_table.benchmarks)
    res["peers_failed"] = (len(pool) - len(ok)) + (len(ok) - len(mdf))
    mdf["scheme_code"] = mdf["scheme_code"].astype(str)
    trow = mdf[mdf["scheme_code"] == rec["code"]]
    if trow.empty:
        res["nav_error"] = "metrics could not be computed from the NAV data"
        facts["nav_error"] = res["nav_error"]
        res["decision"] = mfs.decide(facts)
        return res
    target = trow.iloc[0].to_dict()
    last = _clean(target.get("last_nav_date"))
    target["nav_age_days"] = (today - pd.Timestamp(last).date()).days if last is not None else None
    res["target"] = target

    peers_df = None
    if eligible and len(mdf) <= 1:
        res["peer_mode"] = "too_few"
    if eligible and len(mdf) > 1:
        ranking = mfs.rank_peers(mdf.to_dict("records"))
        res["peer"] = ranking.get(rec["code"])
        res["peer_unranked"] = bool(ranking) and res["peer"] is None
        res["peer_mode"] = "ranked" if res["peer"] else ("unranked" if res["peer_unranked"] else "too_few")
        old_enough = mdf["history_years"] >= mfs.REVIEW_RULES["min_peer_history_years"]
        group = mdf[old_enough].reset_index(drop=True)
        if len(group):
            res["scored"] = shortlist.score_and_rank(group)
        peers_df = group[group["scheme_code"] != rec["code"]]
        res["peer_count"] = len(peers_df)

    _, reasons = shortlist.apply_hard_filters(trow.copy(), return_reasons=True, log=lambda s: None)
    res["shortlist_fails"] = reasons.get(trow.iloc[0]["scheme_code"], [])
    flags, _info = data_checks.check_table(mdf, stale_days=config.STALE_NAV_DAYS)
    pos = list(mdf["scheme_code"]).index(rec["code"])
    res["flags"] = [f for f in flags[pos] if not f.startswith("DUPLICATE_NAME")] if flags else []
    res["comparison"] = comparison_rows(target, peers_df, config.SCORE_WEIGHTS, config.ROLLING_WINDOW_YEARS,
                                        config.DRAWDOWN_WINDOW_YEARS)

    facts.update(peer=res["peer"], peer_unranked=res["peer_unranked"])
    for k in ("history_years", "nav_age_days", "last_nav_date", "cagr_3y", "cagr_5y", "max_drawdown",
              "benchmark_excess_return", "rolling_beat_benchmark_pct", "benchmark_name"):
        facts[k] = _clean(target.get(k))
    res["decision"] = mfs.decide(facts)
    return res


# --------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------
def _fmt(metric, v):
    v = _clean(v)
    if v is None:
        return "n/a"
    if metric == "volatility":
        return f"{v * 100:.1f}%"
    return report_md.fmt(metric, v)


def _list(title, items):
    return ([f"**{title}**"] + [f"- {x}" for x in items] + [""]) if items else []


def render(res):
    rec, d, t = res["rec"], res["decision"], res["target"]
    L = [f"# Fund check: {rec['name']}", ""]
    nav = "n/a" if rec.get("nav") is None else f"Rs {rec['nav']:.4g}"
    hist = _clean(t.get("history_years"))
    L.append(f"Scheme code **{rec['code']}** | {rec.get('amc') or 'AMC n/a'} | {rec['category']}")
    L.append(f"Last NAV {rec.get('nav_date') or 'n/a'} ({nav})"
             + (f" | NAV history {hist:.1f} years" if hist is not None else "")
             + f" | checked on {res['today']}")
    L.append("")
    for n in res["notes"]:
        L.append(f"_{n}_")
    if res["notes"]:
        L.append("")
    L.append(f"## Screen result: {V_TEXT.get(d['verdict'], d['verdict'])}")
    L.append("")
    L.append("_This screens PAST data. It is not a recommendation to buy, hold or sell._")
    L.append("")
    if d["confidence"] not in ("-", "n/a"):
        L.append(f"Evidence used: {d['evidence']} (confidence {d['confidence']}).")
        L.append("")
    L += _list("Red flags", d["red"]) + _list("Cautions", d["amber"]) + _list("In its favour", d["green"])
    L += _list("Notes", d["notes"])
    if res["nav_error"]:
        L.append(f"NAV data problem: {res['nav_error']}")
        L.append("")
    if "direct" not in rec["name"].lower() or any(w in rec["name"].lower() for w in ("idcw", "dividend")):
        L += ["**Plan note:** this is not a Direct-Growth scheme. Peers and benchmark are Direct-Growth, so "
              "returns are not like-for-like (Regular plans cost more; IDCW NAVs are reduced by payouts).", ""]

    if t:
        L.append("## Metrics")
        L.append("")
        peer = res["peer"]
        mode = res["peer_mode"]
        if peer:
            sc = res["scored"]
            row = sc[sc["scheme_code"].astype(str) == rec["code"]]
            extra = ""
            if len(row):
                r0 = row.iloc[0]
                extra = (f" Score {r0['final_score_0_100']:.1f}/100 ({config.SCORING_METHOD} ranking, "
                         f"{r0['score_coverage'] * 100:.0f}% of the weight measured).")
            L.append(f"Rank **{peer['rank']} of {peer['size']}** in its category "
                     f"({mfs.short_category(rec['category'])}); percentile {peer['percentile']:.0f} (100 = best)." + extra)
            if peer.get("unranked"):
                L.append(f"{peer['unranked']} peer(s) with too little data were not ranked.")
        elif mode == "skipped":
            L.append("Peer comparison skipped (--no-peers).")
        elif mode == "not_eligible":
            L.append(f"No like-for-like peer group: '{mfs.short_category(rec['category'])}' mixes funds with different "
                     f"mandates, so the fund is judged on its benchmark and absolute returns only.")
        elif mode == "unranked":
            L.append("The fund could not be ranked against its peers: too little measured data for a comparable "
                     "score (see the coverage floor in weights.ini).")
        elif mode == "too_few":
            L.append("Too few peers with enough history for a ranking.")
        if res["pool_size"] > 1:
            bits = [f"{res['pool_size'] - 1} peers fetched"]
            if res["peers_failed"]:
                bits.append(f"{res['peers_failed']} failed")
            if res["skipped_stale"]:
                bits.append(f"{len(res['skipped_stale'])} skipped (NAV stopped updating)")
            if res["capped"]:
                bits.append(f"{res['capped']} not scanned (config.MAX_FUNDS_TO_SCAN)")
            L.append("Peer group: " + ", ".join(bits) + ".")
        L.append("")
        rows = []
        for m, label, v, med, better, w in res["comparison"]:
            rows.append([label, _fmt(m, v), _fmt(m, med) if med is not None else "-",
                         f"{better:.0f}%" if better is not None else "-", f"{w:g}" if w else "not scored"])
        L += report_md._table(["Metric", "This fund", "Peer median", "Better than", "Weight %"], rows)
        L.append("")
        L.append("'Better than' = share of peers with a worse value (direction-aware: lower volatility, "
                 "beta and downside capture, and a smaller fall, count as better).")
        L.append("")
        if res["benchmarks"]:
            L.append("**Benchmark:** " + "; ".join(b.strip() for b in res["benchmarks"]))
            L.append("An index-fund proxy trails the true Total Return Index by about its expense ratio, so "
                     "excess return and alpha are flattered a little; load a real TRI with import_tri.py for better accuracy.")
            L.append("")
        fails = res["shortlist_fails"]
        L.append("## Shortlist filters (config.py)")
        L.append("")
        L.append("Passes every hard filter." if fails == [] else
                 "Would be dropped by: " + ", ".join(fails) + ".")
        L.append("")
        if res["flags"]:
            L.append("**Data flags:** " + "; ".join(res["flags"]))
            L.append("")
        sc = res["scored"]
        if sc is not None and len(sc):
            top = sc[sc["status"] == "RANKED"].head(5)
            if len(top):
                L.append("## Top of this category (same weights)")
                L.append("")
                L += report_md._table(
                    ["Rank", "Fund", "Score", "3y CAGR", "5y CAGR"],
                    [[int(r["rank"]), ("-> " if str(r["scheme_code"]) == rec["code"] else "") + r["scheme_name"],
                      f"{r['final_score_0_100']:.1f}", _fmt("cagr_3y", r["cagr_3y"]), _fmt("cagr_5y", r["cagr_5y"])]
                     for _, r in top.iterrows()])
                L.append("")
    L.append("## What this check cannot tell you")
    L.append("")
    L.append("- Whether to invest: that depends on your goal, time horizon, tax position and what you already hold.")
    L.append("- Anything about cost or people: the expense ratio is deliberately not used, and exit load, fund-manager "
             "changes and the fund's current portfolio are not looked at.")
    L.append("- The future. " + report_md.DISCLAIMER.split(". ", 1)[1])
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------
def _parse_args(argv):
    ap = argparse.ArgumentParser(prog="check_fund.py", description="Report on one Indian mutual fund (see the top of this file).")
    ap.add_argument("fund", nargs="+", help="fund name (words), or an AMFI scheme code")
    ap.add_argument("--navall", help="AMFI NAVAll.txt you saved yourself (when the download is blocked)")
    ap.add_argument("--no-peers", action="store_true", help="skip the category comparison (faster)")
    ap.add_argument("--refresh", action="store_true", help="re-download NAV data instead of using the cache")
    ap.add_argument("--weights", help="weights file (default: weights.ini next to config.py)")
    ap.add_argument("--rolling-years", type=float, default=None, help="rolling-return window, e.g. 3 or 5")
    ap.add_argument("--workers", type=int, default=4, help="parallel NAV downloads (default 4)")
    ap.add_argument("--output-dir", default="output", help="folder for the report file (default: output)")
    ap.add_argument("--no-file", action="store_true", help="print the report only; write no file")
    ap.add_argument("--format", choices=["docx", "md"], default="docx",
                    help="report file format (default: docx; md = Markdown text)")
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
        text = mfs.load_navall(args.navall, args.refresh, log=lambda s: print(s, file=sys.stderr))
    except (OSError, SystemExit) as exc:
        print(f"ERROR: could not get AMFI's NAVAll.txt ({exc})", file=sys.stderr)
        return 2
    index = mfs.AmfiIndex(mfs.parse_navall(text))
    if not index.records:
        print("ERROR: the NAVAll file has no scheme rows", file=sys.stderr)
        return 2

    query = " ".join(args.fund)
    try:
        rec, notes = resolve_fund(index, query)
    except FundLookupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Checking {rec['name']} ({rec['code']}) ...", file=sys.stderr)
    res = evaluate(rec, index, with_peers=not args.no_peers, refresh=args.refresh, workers=args.workers)
    res["notes"] = notes
    report = render(res)
    print(report)
    if not args.no_file:
        path = os.path.join(args.output_dir, f"fund_check_{rec['code']}.{args.format}")
        try:
            os.makedirs(args.output_dir, exist_ok=True)
            if args.format == "docx":
                report_docx.markdown_to_docx(report, path, title=f"Fund check: {rec['name']}")
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(report)
            print(f"\nReport written to {os.path.abspath(path)}", file=sys.stderr)
        except report_docx.DocxUnavailable as exc:
            print(f"WARNING: no report file written. {exc}  (or use --format md)", file=sys.stderr)
        except OSError as exc:
            print(f"WARNING: could not write the report file ({exc})", file=sys.stderr)
    return 1 if res["nav_error"] else 0


if __name__ == "__main__":
    sys.exit(main())
