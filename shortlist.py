"""
shortlist.py
------------
Main entry point. Given one or more fund categories (e.g. "small cap", "midcap", "large cap",
"flexi cap", "elss" ...), this:

  1. Looks up every matching Direct+Growth fund from AMFI's scheme master (fund_universe.py)
  2. Fetches/loads NAV history for each candidate
  3. Computes CAGR (1y/3y/5y), volatility, Sharpe-style ratio, Sortino ratio, rolling 3-year
     consistency, SIP XIRR, max drawdown (metrics.py), benchmark-relative metrics (benchmark.py),
     downside capture and quartile consistency (extra_metrics.py) and a portfolio-quality score
     from disclosed holdings files (portfolio_quality.py)
  4. Checks data quality (duplicates, stale NAVs, inconsistent values), applies the hard filters
     (config.py), ranks the survivors with the weights in weights.ini (scoring.py) and writes
     CSV, Excel, ranked_funds.md and run_log.txt.

Usage:
    python shortlist.py "small cap"
    python shortlist.py midcap --refresh
    python shortlist.py --category "small cap" --category "mid cap"     # each ranked separately
    python shortlist.py --all-categories                               # + a labelled exploratory list
    python shortlist.py "small cap" --weights my_weights.ini --output-dir out
    python shortlist.py my_funds.csv                                   # CSV with a 'scheme_code' column

Exit status: 0 = finished and wrote output; 1 = nothing could be ranked/no funds; 2 = bad
command line, bad weights file or other fatal input error.
"""

import argparse
import os
import sys

import pandas as pd

import benchmark
import config
import data_checks
import extra_metrics
import fund_filters
import fund_universe
import holdings_fetch
import portfolio_quality
import report
import report_md
import scoring
import weights_loader
from fetch_nav_data import get_nav_history, get_scheme_meta
from metrics import compute_all_metrics


def load_fund_list_from_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "scheme_code" not in df.columns:
        raise ValueError("Input CSV must contain a 'scheme_code' column.")
    df["scheme_code"] = df["scheme_code"].astype(str)
    return df


def load_fund_list_from_category(category_input: str, force_refresh: bool = False, log=print) -> pd.DataFrame:
    log(f"Looking up '{category_input}' funds from the AMFI scheme master ...")
    canonical, candidates = fund_universe.find_candidates(category_input, force_refresh=force_refresh)
    log(f"Resolved category: '{canonical}'. Found {len(candidates)} candidate Direct-Growth fund(s).")

    if not candidates:
        df = pd.DataFrame(columns=["scheme_code", "scheme_name_hint"])
        df.attrs["category_key"] = canonical
        return df

    if len(candidates) > config.MAX_FUNDS_TO_SCAN:
        candidates = sorted(candidates, key=lambda c: c["scheme_name_hint"])
        log(f"Capping full analysis to {config.MAX_FUNDS_TO_SCAN} of {len(candidates)} candidates, "
            f"alphabetically (this is a safety limit, NOT a quality pre-filter -- raise "
            f"MAX_FUNDS_TO_SCAN in config.py to scan every match).")
        candidates = candidates[:config.MAX_FUNDS_TO_SCAN]

    df = pd.DataFrame(candidates)
    df.attrs["category_key"] = canonical  # used as the benchmark fallback
    return df


METRIC_COLUMNS = ["scheme_code", "scheme_name", "fund_house", "scheme_category",
                  "cagr_1y", "cagr_3y", "cagr_5y", "volatility", "risk_return_ratio",
                  "sortino_ratio", "downside_deviation", "ratio_window_years", "rolling_avg", "rolling_min",
                  "rolling_positive_pct", "rolling_std", "sip_xirr",
                  "max_drawdown", "history_years",
                  "benchmark_name", "benchmark_proxy", "benchmark_cagr",
                  "benchmark_excess_return", "rolling_beat_benchmark_pct", "benchmark_windows",
                  "downside_capture", "quartile_consistency", "q1_share",
                  "portfolio_quality", "pq_coverage", "pq_top10_pct", "pq_holdings", "pq_top_sector_pct",
                  "pq_largemid_pct", "pq_cash_pct", "pq_as_of", "pq_source", "pq_note",
                  "last_nav_date"]


def build_metrics_table(fund_list: pd.DataFrame, force_refresh: bool = False, log=print) -> pd.DataFrame:
    rows = []
    rolling_by_code = {}
    total = len(fund_list)
    default_key = fund_list.attrs.get("category_key")
    bench_provider = benchmark.BenchmarkProvider(force_refresh=force_refresh) if config.BENCHMARK_ENABLED else None
    pq_index = portfolio_quality.PortfolioIndex() if config.PORTFOLIO_QUALITY_ENABLED else None
    if pq_index is not None:
        log(f"Holdings files: {pq_index.files_read} workbook(s) read, {len(pq_index.entries)} portfolio sheet(s) "
            f"parsed under {pq_index.root}/")
        for w in pq_index.warnings:
            log(f"  WARNING: {w}")

    for i, row in enumerate(fund_list.itertuples(index=False), 1):
        code = row.scheme_code
        log(f"[{i}/{total}] Processing scheme {code} ...")
        try:
            nav_df = get_nav_history(code, force_refresh=force_refresh)
        except Exception as exc:
            log(f"  WARNING: skipping {code}, could not fetch NAV data: {exc}")
            continue

        meta = get_scheme_meta(code)
        m = compute_all_metrics(
            nav_df, config.RISK_FREE_RATE,
            sip_years=config.SIP_YEARS, sip_monthly_amount=config.SIP_MONTHLY_AMOUNT,
            rolling_window_years=config.ROLLING_WINDOW_YEARS,
            align_ratio_window=config.RATIO_ALIGN_WINDOW,
        )
        m["scheme_code"] = code
        m["scheme_name"] = meta.get("scheme_name", "") or getattr(row, "scheme_name_hint", "")
        m["fund_house"] = meta.get("fund_house", "")
        m["scheme_category"] = meta.get("scheme_category", "")
        m.update(benchmark.metrics_for_fund(nav_df, bench_provider, m["scheme_category"], default_key))
        m.update(portfolio_quality.fields_for_fund(pq_index, m["scheme_name"]))
        m["last_nav_date"] = nav_df["date"].max() if len(nav_df) else pd.NaT

        # downside capture needs the benchmark series; rolling series feed the quartile metric
        bench = None
        if bench_provider is not None:
            bench = bench_provider.get(benchmark.category_key(m["scheme_category"], default_key))
        m["downside_capture"] = extra_metrics.downside_capture(nav_df, bench["df"]) if bench else None
        try:
            rolling_by_code[str(code)] = benchmark._rolling_cagr(benchmark._month_end_nav(nav_df),
                                                                  config.ROLLING_WINDOW_YEARS)
        except Exception:
            rolling_by_code[str(code)] = None
        rows.append(m)

    q = extra_metrics.quartile_consistency(rolling_by_code, min_peers=config.QUARTILE_MIN_PEERS)
    for m in rows:
        info = q.get(str(m["scheme_code"]), {})
        m["quartile_consistency"] = info.get("quartile_consistency")
        m["q1_share"] = info.get("q1_share")

    if bench_provider is not None:
        lines = bench_provider.describe()
        if lines:
            log("\nBenchmarks used:")
            log("\n".join(lines))
    build_metrics_table.benchmarks = bench_provider.describe() if bench_provider is not None else []

    if pq_index is not None and rows:
        scored_n = sum(1 for r in rows if r.get("portfolio_quality") is not None)
        log(f"\nPortfolio quality scored for {scored_n} of {len(rows)} funds "
            f"(the rest have no usable holdings file; see pq_note in the CSV).")

    return pd.DataFrame(rows, columns=METRIC_COLUMNS)


build_metrics_table.benchmarks = []


def apply_hard_filters(df: pd.DataFrame, return_reasons: bool = False, log=print):
    """Drops funds that fail any configured minimum threshold. Explains
    why each fund was dropped so the user can see the reasoning."""
    kept = df.copy()
    reasons = {}

    def fails(mask, label):
        dropped = kept.loc[mask, "scheme_code"]
        for code in dropped:
            reasons.setdefault(code, []).append(label)

    if config.MIN_HISTORY_YEARS is not None:
        fails(kept["history_years"] < config.MIN_HISTORY_YEARS, "insufficient history")
    if config.MIN_CAGR_1Y is not None:
        fails(kept["cagr_1y"].isna() | (kept["cagr_1y"] < config.MIN_CAGR_1Y), "1y CAGR too low")
    if config.MIN_CAGR_3Y is not None:
        fails(kept["cagr_3y"].isna() | (kept["cagr_3y"] < config.MIN_CAGR_3Y), "3y CAGR too low")
    if config.MIN_CAGR_5Y is not None:
        fails(kept["cagr_5y"].isna() | (kept["cagr_5y"] < config.MIN_CAGR_5Y), "5y CAGR too low")
    if config.MAX_VOLATILITY is not None:
        fails(kept["volatility"].isna() | (kept["volatility"] > config.MAX_VOLATILITY), "volatility too high")
    if config.MIN_RISK_RETURN_RATIO is not None:
        fails(kept["risk_return_ratio"].isna() | (kept["risk_return_ratio"] < config.MIN_RISK_RETURN_RATIO),
              "risk-return ratio too low")
    if config.MIN_SORTINO_RATIO is not None:
        fails(kept["sortino_ratio"].isna() | (kept["sortino_ratio"] < config.MIN_SORTINO_RATIO),
              "Sortino ratio too low")
    if config.MIN_ROLLING_POSITIVE_PCT is not None:
        fails(kept["rolling_positive_pct"].isna() | (kept["rolling_positive_pct"] < config.MIN_ROLLING_POSITIVE_PCT),
              "rolling-return consistency too low")

    if reasons:
        log("\nFunds excluded by hard filters:")
        for code, why in reasons.items():
            name = kept.loc[kept["scheme_code"] == code, "scheme_name"].values
            name = name[0] if len(name) else code
            log(f"  - {code} ({name}): {', '.join(why)}")

    survivors = kept[~kept["scheme_code"].isin(reasons.keys())].reset_index(drop=True)
    return (survivors, reasons) if return_reasons else survivors


def score_and_rank(df: pd.DataFrame, policy=None, min_coverage=None, method=None, min_group_size=None) -> pd.DataFrame:
    """Ranks df with the weights and policy from weights.ini (see scoring.py). Optional arguments
    override the file's policy/coverage floor/method/group size for one call."""
    return scoring.score_and_rank(
        df, config.SCORE_WEIGHTS,
        policy=config.MISSING_DATA_POLICY if policy is None else policy,
        min_coverage=config.MIN_SCORE_COVERAGE if min_coverage is None else min_coverage,
        method=config.SCORING_METHOD if method is None else method,
        min_group_size=config.MIN_GROUP_SIZE if min_group_size is None else min_group_size)


def prepare_group(metrics_df: pd.DataFrame, log: report_md.RunLog, reference_date=None, attributes=None):
    """Data checks + all filters for one group. Returns (survivors, excluded[(code, name, reasons)], as_of)."""
    excluded = []
    df, n_dup = data_checks.drop_duplicate_codes(metrics_df)
    if n_dup:
        log.warn(f"{n_dup} duplicate scheme_code row(s) dropped")

    flags, info = data_checks.check_table(df, stale_days=config.STALE_NAV_DAYS, reference_date=reference_date)
    for w in info["warnings"]:
        log.warn(w)
    df = df.copy()
    df["data_flags"] = ["; ".join(f) for f in flags]

    if config.EXCLUDE_STALE_FUNDS:
        stale = df["data_flags"].str.contains("STALE_NAV", regex=False)
        for _, r in df[stale].iterrows():
            excluded.append((r["scheme_code"], r["scheme_name"], [x for x in r["data_flags"].split("; ") if x.startswith("STALE_NAV")]))
        if stale.any():
            log.add(f"  {int(stale.sum())} stale fund(s) excluded (config.EXCLUDE_STALE_FUNDS)")
        df = df[~stale].reset_index(drop=True)

    df = fund_filters.merge_attributes(df, attributes)
    log.add("Applying hard filters (min 1y/3y/5y CAGR, max volatility, min risk-return ratio, history) ...")
    df, reasons = apply_hard_filters(df, return_reasons=True, log=lambda s: log.add(s))
    names = metrics_df.set_index("scheme_code")["scheme_name"].to_dict() if len(metrics_df) else {}
    for code, why in reasons.items():
        excluded.append((code, names.get(code, code), why))

    df, attr_reasons, gaps = fund_filters.apply_attribute_filters(df, config)
    for code, why in attr_reasons.items():
        excluded.append((code, names.get(code, code), why))
    if attr_reasons:
        log.add(f"  {len(attr_reasons)} fund(s) dropped by the optional AUM/tenure/turnover/cash/concentration filters")
    if gaps:
        df["data_flags"] = [("; ".join(x for x in [r["data_flags"], "; ".join(sorted(set(gaps.get(str(r['scheme_code']), []))))] if x))
                            for _, r in df.iterrows()]
    return df, excluded, info["as_of"]


DISPLAY_COLS = ["rank", "scheme_name", "cagr_1y", "cagr_3y", "cagr_5y", "sortino_ratio",
                "rolling_positive_pct", "sip_xirr", "max_drawdown", "benchmark_excess_return",
                "rolling_beat_benchmark_pct", "downside_capture", "portfolio_quality",
                "final_score_0_100", "composite_score", "score_coverage", "status"]


def format_for_display(df: pd.DataFrame) -> pd.DataFrame:
    pretty = df.copy()
    pct_cols = ["cagr_1y", "cagr_3y", "cagr_5y", "volatility", "max_drawdown",
                "downside_deviation", "rolling_avg", "rolling_min", "rolling_std",
                "rolling_positive_pct", "sip_xirr",
                "benchmark_cagr", "benchmark_excess_return", "rolling_beat_benchmark_pct",
                "pq_coverage", "score_coverage", "downside_capture", "quartile_consistency", "q1_share"]
    for c in pct_cols:
        if c in pretty.columns:
            pretty[c] = pretty[c].apply(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "N/A")
    for c in ["risk_return_ratio", "sortino_ratio"]:
        if c in pretty.columns:
            pretty[c] = pretty[c].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "N/A")
    if "portfolio_quality" in pretty.columns:
        pretty["portfolio_quality"] = pretty["portfolio_quality"].apply(lambda v: f"{v:.0f}" if pd.notna(v) else "N/A")
    for c, f in (("composite_score", "{:.3f}"), ("final_score_0_100", "{:.1f}")):
        if c in pretty.columns:
            pretty[c] = pretty[c].apply(lambda v, f=f: f.format(v) if pd.notna(v) else "N/A")
    if "rank" in pretty.columns:
        pretty["rank"] = pretty["rank"].apply(lambda v: str(int(v)) if pd.notna(v) else "-")
    return pretty


def _parse_args(argv):
    ap = argparse.ArgumentParser(prog="shortlist.py", add_help=True,
                                 description="Shortlist and rank Indian mutual funds by category.")
    ap.add_argument("query", nargs="*", help='a category ("small cap") or a CSV with a scheme_code column')
    ap.add_argument("--category", action="append", default=[], help="a category to rank (repeat for several)")
    ap.add_argument("--all-categories", action="store_true",
                    help="rank every supported category separately, plus a labelled exploratory cross-category list")
    ap.add_argument("--refresh", action="store_true", help="force re-download of NAV/scheme data")
    ap.add_argument("--fetch-holdings", action="store_true", help="download AMC portfolio files first")
    ap.add_argument("--weights", help="weights file (default: weights.ini next to config.py)")
    ap.add_argument("--output-dir", default=None, help=f"folder for output files (default: {config.OUTPUT_DIR})")
    ap.add_argument("--as-of-date", help="YYYY-MM-DD reference date for the stale-NAV check "
                                         "(default: the newest NAV date in each group)")
    ap.add_argument("--top-n", type=int, default=None, help=f"funds to show per category (default {config.TOP_N})")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    log = report_md.RunLog()

    try:
        if args.weights:
            config.apply_weights(args.weights)
    except weights_loader.WeightsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    out_dir = args.output_dir or config.OUTPUT_DIR
    top_n = args.top_n or config.TOP_N
    reference = None
    if args.as_of_date:
        reference = pd.to_datetime(args.as_of_date, errors="coerce")
        if pd.isna(reference):
            print(f"ERROR: --as-of-date '{args.as_of_date}' is not a valid YYYY-MM-DD date", file=sys.stderr)
            return 2

    query = " ".join(args.query).strip()
    csv_mode = query.lower().endswith(".csv")
    categories = list(args.category)
    if args.all_categories:
        categories += [c for c in fund_universe.supported_categories() if c not in categories]
    elif query and not csv_mode:
        categories.append(query)
    if not categories and not csv_mode:
        print("Usage: python shortlist.py <category> [--refresh] [--fetch-holdings] [--weights FILE] [--output-dir DIR]")
        print('Examples: python shortlist.py "small cap"')
        print('          python shortlist.py --category "small cap" --category "mid cap"')
        print("          python shortlist.py --all-categories")
        print("          python shortlist.py my_funds.csv   (CSV with a 'scheme_code' column)")
        print(f"\nSupported categories: {', '.join(fund_universe.supported_categories())}")
        return 2

    try:
        os.makedirs(out_dir, exist_ok=True)
        attributes = fund_filters.load_attributes(config.FUND_ATTRIBUTES_CSV)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.fetch_holdings:
        holdings_fetch.fetch_all()
        print()

    log.add(f"Run started {log.started:%Y-%m-%d %H:%M}")
    log.add(f"Weights file: {config.WEIGHTS_FILE} (version {config.WEIGHTS_VERSION}); policy {config.MISSING_DATA_POLICY}; "
            f"method {config.SCORING_METHOD}; coverage floor {config.MIN_SCORE_COVERAGE:.0%}; low-confidence below "
            f"{config.MIN_GROUP_SIZE} funds")
    log.add("Weights %: " + ", ".join(f"{m}={w * 100:g}" for m, w in config.SCORE_WEIGHTS.items() if w > 0))

    jobs = []   # (group name, fund_list)
    try:
        if csv_mode:
            if not os.path.exists(query):
                print(f"ERROR: file not found: {query}", file=sys.stderr)
                return 2
            log.add(f"Input file: {query}")
            jobs.append(("custom list (categories may be mixed)", load_fund_list_from_csv(query)))
        for cat in categories:
            fl = load_fund_list_from_category(cat, force_refresh=args.refresh, log=lambda s: log.add(s))
            jobs.append((fl.attrs.get("category_key") or cat, fl))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: could not build the fund list ({exc})", file=sys.stderr)
        return 2

    groups, pool, benchmarks = [], [], []
    for name, fl in jobs:
        if fl.empty:
            log.warn(f"{name}: no candidate funds found; skipped")
            continue
        log.add(f"\n=== {name}: fetching NAV history and computing metrics for {len(fl)} funds ===")
        mdf = build_metrics_table(fl, force_refresh=args.refresh, log=lambda s: log.add(s))
        benchmarks += build_metrics_table.benchmarks
        if mdf.empty:
            log.warn(f"{name}: no funds could be processed (check scheme codes and network access)")
            continue
        survivors, excluded, as_of = prepare_group(mdf, log, reference, attributes)
        log.add(f"\n{name}: {len(survivors)} of {len(mdf)} funds passed the filters.")
        if survivors.empty:
            log.warn(f"{name}: no funds passed the filters; consider relaxing thresholds in config.py")
            groups.append({"name": name, "ranked": pd.DataFrame(), "excluded": excluded, "as_of": as_of})
            continue
        ranked = score_and_rank(survivors)
        ranked.insert(0, "group", name)
        pool.append(survivors)
        groups.append({"name": name, "ranked": ranked, "excluded": excluded, "as_of": as_of})
        log.add(f"{name}: {int((ranked['status'] == 'RANKED').sum())} ranked, "
                f"{int((ranked['status'] == 'INSUFFICIENT_DATA').sum())} with insufficient data; "
                f"confidence {ranked['confidence'].iloc[0]}")

    ranked_groups = [g for g in groups if len(g["ranked"])]
    if not ranked_groups:
        log.warn("nothing could be ranked")
        log.write(os.path.join(out_dir, config.OUTPUT_LOG))
        print(f"\nRun log written to {os.path.join(out_dir, config.OUTPUT_LOG)}")
        return 1

    exploratory = None
    if len(ranked_groups) > 1:
        exploratory = score_and_rank(pd.concat(pool, ignore_index=True))
        exploratory.insert(0, "group", "EXPLORATORY cross-category")
        log.add("Cross-category list is EXPLORATORY: categories have different risk profiles.")

    all_ranked = pd.concat([g["ranked"] for g in ranked_groups], ignore_index=True)
    csv_path = os.path.join(out_dir, config.OUTPUT_CSV)
    all_ranked.to_csv(csv_path, index=False)
    log.add(f"\nFull ranked list written to {csv_path}")
    if exploratory is not None:
        exp_path = os.path.join(out_dir, "shortlisted_exploratory.csv")
        exploratory.to_csv(exp_path, index=False)
        log.add(f"Exploratory cross-category list written to {exp_path}")
    if config.EXPORT_EXCEL and report.export_to_excel(all_ranked, os.path.join(out_dir, config.OUTPUT_XLSX)):
        log.add(f"Formatted Excel report written to {os.path.join(out_dir, config.OUTPUT_XLSX)}")

    md_path = os.path.join(out_dir, config.OUTPUT_MD)
    sources = ["NAV history from mfapi.in (mirrors AMFI); newest NAV dates are shown per category",
               f"holdings files under {config.HOLDINGS_DIR}/ where present"]
    report_md.write_markdown(md_path, ranked_groups, config, log, exploratory, top_n=top_n,
                             sources=sources, benchmarks=sorted(set(benchmarks)))
    log.add(f"Markdown report written to {md_path}")
    for g in ranked_groups:
        top = g["ranked"].head(top_n)
        log.add(f"\n=== {g['name']}: top {len(top)} ===\n")
        cols = [c for c in DISPLAY_COLS if c in top.columns]
        log.add(format_for_display(top)[cols].to_string(index=False))
    log_path = os.path.join(out_dir, config.OUTPUT_LOG)
    log.write(log_path)
    print(f"\nRun log written to {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
