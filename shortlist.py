"""
shortlist.py
------------
Main entry point. Given a fund category (e.g. "small cap", "midcap",
"large cap", "flexi cap", "elss" ...), this:

  1. Looks up every matching Direct+Growth fund from AMFI's scheme master
     (via fund_universe.py) -- no silent alphabetical cap
  2. Fetches/loads NAV history for each candidate, in parallel
  3. Computes CAGR (1y/3y/5y), volatility, risk-adjusted ratios, Sortino,
     rolling-return consistency, SIP XIRR and max drawdown -- all risk
     metrics over one common trailing window (metrics.py)
  4. Data-quality gate: drops funds whose AMFI category doesn't match the
     request, whose NAV feed is stale, or whose NAV history has suspicious
     jumps
  5. Builds a benchmark (index proxy, or the category average) and computes
     beta / alpha / information ratio / up-down capture / rolling beat %
  6. Applies hard filters (category-relative by default), ranks the
     survivors with a weighted composite score standardized against the
     whole eligible category, and writes CSV + Excel, plus a CSV listing
     every excluded fund and why.

Usage:
    python shortlist.py "small cap"
    python shortlist.py midcap
    python shortlist.py "large cap" --refresh          # force re-download
    python shortlist.py "mid cap" --benchmark 123456   # pin a benchmark scheme code
    python shortlist.py "flexi cap" --benchmark category --window 5
    python shortlist.py my_funds.csv                   # CSV with a 'scheme_code' column
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import benchmark
import config
import forward_signals
import fund_universe
import manifest
import report
from scoring import pct_rank, should_use_percentile, standardize
from logutil import get_logger, setup_logging
from fetch_nav_data import fetch_many, get_scheme_meta
from metrics import BENCH_KEYS, calculate_benchmark_stats, compute_all_metrics

log = get_logger(__name__)

BASE_COLS = ["scheme_code", "scheme_name", "fund_house", "scheme_category",
             "cagr_1y", "cagr_3y", "cagr_5y", "volatility", "risk_return_ratio",
             "sortino_ratio", "downside_deviation", "rolling_avg", "rolling_min",
             "rolling_positive_pct", "rolling_above_hurdle_pct", "rolling_std",
             "rolling_windows", "sip_xirr", "max_drawdown", "history_years",
             "last_nav_date", "nav_anomalies", "max_daily_move"]


# ---------------------------------------------------------------------------
# Loading the fund list
# ---------------------------------------------------------------------------

def load_fund_list_from_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "scheme_code" not in df.columns:
        raise ValueError("Input CSV must contain a 'scheme_code' column.")
    df["scheme_code"] = df["scheme_code"].astype(str)
    return df


def load_fund_list_from_category(category_input: str, force_refresh: bool = False):
    log.info(f"Looking up '{category_input}' funds from the AMFI scheme master ...")
    canonical, candidates = fund_universe.find_candidates(category_input, force_refresh=force_refresh)
    log.info(f"Resolved category: '{canonical}'. Found {len(candidates)} candidate Direct-Growth fund(s).")

    if not candidates:
        return canonical, pd.DataFrame(columns=["scheme_code", "scheme_name_hint"])
    return canonical, pd.DataFrame(fund_universe.cap_candidates(candidates))


# ---------------------------------------------------------------------------
# Metrics table
# ---------------------------------------------------------------------------

def build_metrics_table(fund_list: pd.DataFrame, nav_data: dict) -> pd.DataFrame:
    """One row of benchmark-independent metrics per fund that has NAV data."""
    rows = []
    for row in fund_list.itertuples(index=False):
        code = row.scheme_code
        nav_df = nav_data.get(code)
        if nav_df is None or nav_df.empty:
            continue

        meta = get_scheme_meta(code)
        m = compute_all_metrics(
            nav_df, config.RISK_FREE_RATE,
            sip_years=config.SIP_YEARS, sip_monthly_amount=config.SIP_MONTHLY_AMOUNT,
            rolling_window_years=config.ROLLING_WINDOW_YEARS,
            risk_window_years=config.RISK_WINDOW_YEARS,
            nav_jump_threshold=config.NAV_JUMP_THRESHOLD,
            rolling_min_windows=config.ROLLING_MIN_WINDOWS,
            rolling_hurdle=config.ROLLING_HURDLE,
        )
        m["scheme_code"] = code
        m["scheme_name"] = meta.get("scheme_name", "") or getattr(row, "scheme_name_hint", "")
        m["fund_house"] = meta.get("fund_house", "")
        m["scheme_category"] = meta.get("scheme_category", "")
        rows.append(m)
    return pd.DataFrame(rows, columns=BASE_COLS)


# ---------------------------------------------------------------------------
# Data-quality gate
# ---------------------------------------------------------------------------

def apply_data_quality_filters(df: pd.DataFrame, canonical: str | None, excluded: dict) -> pd.DataFrame:
    """Drops funds with a mismatched AMFI category, a stale NAV feed, or
    suspicious NAV jumps. Appends reasons to `excluded` ({code: [reasons]}).
    Adds a `nav_age_days` column (days behind the freshest fund in the set)."""
    if df.empty:
        return df
    out = df.copy()

    latest = pd.to_datetime(out["last_nav_date"])
    out["nav_age_days"] = (latest.max() - latest).dt.days

    def drop(mask, reason_fn):
        for _, r in out[mask].iterrows():
            excluded.setdefault(r["scheme_code"], []).append(reason_fn(r))

    drop_mask = pd.Series(False, index=out.index)

    if canonical and config.VERIFY_SCHEME_CATEGORY:
        verdict = out["scheme_category"].apply(lambda c: fund_universe.category_matches(canonical, c))
        mismatch = verdict.apply(lambda v: v is False)
        unverified = verdict.apply(lambda v: v is None)
        drop(mismatch, lambda r: f"AMFI category '{r['scheme_category']}' is not '{canonical}'")
        drop_mask |= mismatch
        if unverified.any():
            log.info(f"{int(unverified.sum())} fund(s) had no AMFI category label and were kept on name match alone.")

    if config.MAX_NAV_STALENESS_DAYS is not None:
        stale = out["nav_age_days"] > config.MAX_NAV_STALENESS_DAYS
        drop(stale, lambda r: f"stale NAV (last NAV {r['last_nav_date']}, {int(r['nav_age_days'])}d behind the category)")
        drop_mask |= stale

    anomalous = out["nav_anomalies"].fillna(0) > 0
    if anomalous.any():
        if config.EXCLUDE_ON_NAV_ANOMALY:
            drop(anomalous, lambda r: f"suspicious NAV jump ({r['max_daily_move']*100:.0f}% in one day; "
                                      f"{int(r['nav_anomalies'])} move(s) > {config.NAV_JUMP_THRESHOLD*100:.0f}%)")
            drop_mask |= anomalous
        else:
            log.info(f"{int(anomalous.sum())} fund(s) have single-day NAV moves > "
                  f"{config.NAV_JUMP_THRESHOLD*100:.0f}% (kept; see nav_anomalies column).")

    return out[~drop_mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Benchmark-relative metrics
# ---------------------------------------------------------------------------

def attach_benchmark_metrics(df: pd.DataFrame, nav_data: dict, canonical: str | None,
                             override: str | None, force_refresh: bool):
    """Resolves the benchmark and adds beta/alpha/IR/capture columns.
    Returns (df, benchmark_label_or_None, benchmark_df_or_None)."""
    out = df.copy()
    label, bench_df, note = benchmark.resolve_benchmark(
        canonical, {c: nav_data[c] for c in out["scheme_code"] if c in nav_data},
        override=override, force_refresh=force_refresh)

    if bench_df is None:
        for k in BENCH_KEYS:
            out[k] = np.nan
        log.info(f"Benchmark-relative metrics skipped: {note}.")
        return out, None, None

    log.info(f"Benchmark ({note}): {label}")
    stats = [
        calculate_benchmark_stats(
            nav_data[code], bench_df, config.RISK_FREE_RATE,
            window_years=config.RISK_WINDOW_YEARS,
            rolling_window_years=config.ROLLING_WINDOW_YEARS,
            min_coverage=config.BENCHMARK_MIN_COVERAGE)
        for code in out["scheme_code"]
    ]
    stats_df = pd.DataFrame(stats, columns=BENCH_KEYS).astype(float)
    return pd.concat([out.reset_index(drop=True), stats_df], axis=1), label, bench_df


# ---------------------------------------------------------------------------
# Hard filters
# ---------------------------------------------------------------------------

def apply_hard_filters(df: pd.DataFrame, universe: pd.DataFrame | None = None,
                       excluded: dict | None = None) -> pd.DataFrame:
    """Drops funds that fail any configured minimum threshold, recording why.

    Structural filters (history, volatility) are always applied. Performance
    filters depend on config.FILTER_MODE: "relative" = percentile within the
    category (`universe`, the whole eligible set), "absolute" = fixed floors,
    "both" = must pass both."""
    universe = df if universe is None else universe
    excluded = {} if excluded is None else excluded
    kept = df.copy()
    reasons = {}

    def fails(mask, label_fn):
        for _, r in kept[mask].iterrows():
            reasons.setdefault(r["scheme_code"], []).append(label_fn(r) if callable(label_fn) else label_fn)

    if config.MIN_HISTORY_YEARS is not None:
        fails(kept["history_years"] < config.MIN_HISTORY_YEARS, "insufficient history")
    if config.MAX_VOLATILITY is not None:
        fails(kept["volatility"].isna() | (kept["volatility"] > config.MAX_VOLATILITY), "volatility too high / unavailable")

    mode = config.FILTER_MODE.lower()
    if mode in ("absolute", "both"):
        abs_rules = [
            ("cagr_1y", config.MIN_CAGR_1Y, "1y CAGR too low"),
            ("cagr_3y", config.MIN_CAGR_3Y, "3y CAGR too low"),
            ("cagr_5y", config.MIN_CAGR_5Y, "5y CAGR too low"),
            ("risk_return_ratio", config.MIN_RISK_RETURN_RATIO, "risk-return ratio too low"),
            ("sortino_ratio", config.MIN_SORTINO_RATIO, "Sortino ratio too low"),
            ("rolling_positive_pct", config.MIN_ROLLING_POSITIVE_PCT, "rolling-return consistency too low"),
        ]
        for col, floor, label in abs_rules:
            if floor is not None:
                fails(kept[col].isna() | (kept[col] < floor), label)

    if mode in ("relative", "both"):
        for col, min_pct in config.RELATIVE_MIN_PERCENTILES.items():
            if min_pct is None:
                continue
            pct = pct_rank(universe[col], kept[col])
            bad = pct.isna() | (pct < min_pct)
            for idx in kept.index[bad]:
                p = pct.loc[idx]
                shown = "n/a" if pd.isna(p) else f"percentile {p*100:.0f}"
                reasons.setdefault(kept.at[idx, "scheme_code"], []).append(
                    f"{col} below category cut-off ({shown} < required {min_pct*100:.0f})")

    # Optional benchmark-relative floors (only when benchmark metrics exist).
    bench_rules = [
        ("alpha", config.MIN_ALPHA, "min", "alpha below floor"),
        ("rolling_beat_pct", config.MIN_ROLLING_BEAT_PCT, "min", "beats benchmark in too few rolling windows"),
        ("down_capture", config.MAX_DOWN_CAPTURE, "max", "down-capture too high"),
    ]
    for col, limit, kind, label in bench_rules:
        if limit is None or kept[col].notna().sum() == 0 and universe[col].notna().sum() == 0:
            continue
        bad = kept[col].isna() | ((kept[col] < limit) if kind == "min" else (kept[col] > limit))
        fails(bad, label)

    if reasons:
        log.info("Funds excluded by hard filters:")
        for code, why in reasons.items():
            name = kept.loc[kept["scheme_code"] == code, "scheme_name"].values
            name = name[0] if len(name) else code
            log.info(f"  - {code} ({name}): {'; '.join(why)}")
            excluded.setdefault(code, []).extend(why)

    return kept[~kept["scheme_code"].isin(reasons.keys())].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _active_weights(universe: pd.DataFrame) -> dict:
    """Weighted metrics that actually have data in the universe."""
    active = {}
    min_n = min(3, len(universe))
    for metric, w in config.SCORE_WEIGHTS.items():
        if not w or metric not in universe.columns:
            continue
        if universe[metric].notna().sum() < max(min_n, 1):
            log.info(f"  (scoring: '{metric}' has no data in this category -- its weight is redistributed)")
            continue
        active[metric] = w
    return active


def warn_on_correlated_metrics(universe: pd.DataFrame, weights: dict):
    """Prints pairs of weighted metrics that move almost together across the
    category -- they would double-count the same evidence."""
    cols = list(weights)
    if len(cols) < 2 or len(universe) < 8:
        return
    corr = universe[cols].astype(float).corr(method="spearman")
    flagged = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            c = corr.loc[a, b]
            if pd.notna(c) and abs(c) >= config.CORR_WARN_THRESHOLD:
                flagged.append((a, b, c))
    if flagged:
        log.warning("heavily-weighted metrics that are near-duplicates in this category "
              f"(rank correlation >= {config.CORR_WARN_THRESHOLD:.2f}); consider dropping one:")
        for a, b, c in flagged:
            log.warning(f"  - {a} ~ {b}: rho={c:+.2f} (combined weight {weights[a] + weights[b]:.2f})")


def score_and_rank(df: pd.DataFrame, universe: pd.DataFrame | None = None) -> pd.DataFrame:
    """Combines the weighted metrics into a composite score.

    Each metric is standardized against `universe` (the whole eligible
    category, before hard filters) rather than only the survivors:
      - "zscore": robust z-score, (value - median) / (1.4826 * MAD), winsorized
        at +/- SCORE_WINSORIZE_Z
      - "percentile": percentile rank, centered at 0 (used automatically when
        the universe has fewer than SCORE_MIN_FUNDS_FOR_ZSCORE funds)
    Metrics where lower is better (config.LOWER_IS_BETTER) are sign-flipped.
    NOTE max_drawdown is stored as a negative fraction, so it is NOT flipped:
    -0.10 (a shallow drawdown) already ranks above -0.40.
    A fund missing a metric is scored neutrally (0 = category average) for it."""
    if df.empty:
        return df
    universe = df if universe is None else universe
    scored = df.copy()

    weights = _active_weights(universe)
    if not weights:
        raise ValueError("No scoring metric has data; check SCORE_WEIGHTS in config.py.")
    weight_sum = sum(weights.values())

    use_percentile = should_use_percentile(len(universe))
    if use_percentile and config.SCORING_METHOD.lower() != "percentile":
        log.info(f"only {len(universe)} eligible funds (< {config.SCORE_MIN_FUNDS_FOR_ZSCORE}); "
                 f"using percentile ranks instead of z-scores.")

    total = pd.Series(0.0, index=scored.index)
    for metric, weight in weights.items():
        component = standardize(universe[metric], scored[metric],
                                lower_is_better=metric in config.LOWER_IS_BETTER,
                                use_percentile=use_percentile)
        total += component * (weight / weight_sum)

    warn_on_correlated_metrics(universe, weights)

    scored["composite_score"] = total
    scored = scored.sort_values("composite_score", ascending=False).reset_index(drop=True)
    scored.insert(0, "rank", range(1, len(scored) + 1))
    return scored


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

PCT_COLS = ["rolling_p10", "rolling_dispersion", "aum_growth_12m", "cagr_1y", "cagr_3y", "cagr_5y", "volatility", "max_drawdown",
            "downside_deviation", "rolling_avg", "rolling_min", "rolling_std",
            "rolling_positive_pct", "rolling_above_hurdle_pct", "sip_xirr",
            "alpha", "tracking_error", "excess_cagr", "rolling_beat_pct",
            "up_capture", "down_capture", "max_daily_move"]
RATIO_COLS = ["risk_return_ratio", "sortino_ratio", "beta", "information_ratio", "sharpe_stability",
              "beta_drift", "down_capture_drift", "aum_vs_median", "aum_strain"]


def format_for_display(df: pd.DataFrame) -> pd.DataFrame:
    pretty = df.copy()
    for c in PCT_COLS:
        if c in pretty.columns:
            pretty[c] = pretty[c].apply(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "N/A")
    for c in RATIO_COLS:
        if c in pretty.columns:
            pretty[c] = pretty[c].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "N/A")
    for c in ["composite_score", "forward_tilt", "combined_score"]:
        if c in pretty.columns:
            pretty[c] = pretty[c].apply(lambda v: f"{v:.3f}" if pd.notna(v) else "N/A")
    if "expense_ratio" in pretty.columns:
        pretty["expense_ratio"] = pretty["expense_ratio"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "N/A")
    if "rank_change" in pretty.columns:
        pretty["rank_change"] = pretty["rank_change"].apply(lambda v: f"{int(v):+d}" if pd.notna(v) else "")
    return pretty


def write_excluded(excluded: dict, names: dict, path: str):
    if not excluded:
        return
    rows = [{"scheme_code": c, "scheme_name": names.get(c, ""), "reasons": "; ".join(r)}
            for c, r in excluded.items()]
    pd.DataFrame(rows).to_csv(path, index=False)
    log.info(f"{len(rows)} excluded fund(s) and the reasons written to {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Shortlist Indian mutual funds by category.",
        epilog="Supported categories: " + ", ".join(fund_universe.supported_categories()))
    p.add_argument("query", nargs="*", help='category (e.g. "small cap") or a CSV with a scheme_code column')
    p.add_argument("--refresh", action="store_true", help="force re-download of NAV / scheme data")
    p.add_argument("--benchmark", default=None, metavar="CODE|category|none",
                   help="benchmark scheme code, 'category' (category average) or 'none'")
    p.add_argument("--window", type=float, default=None, metavar="YEARS",
                   help=f"common risk window in years (default {config.RISK_WINDOW_YEARS})")
    p.add_argument("--filter-mode", choices=["relative", "absolute", "both"], default=None)
    p.add_argument("--top", type=int, default=None, help=f"how many funds to display (default {config.TOP_N})")
    p.add_argument("--forward", action="store_true",
                   help="let the forward-looking tilt influence the ranking (default: columns shown only)")
    p.add_argument("--no-forward", action="store_true", help="force the tilt off even if enabled in config.py")
    p.add_argument("--forward-blend", type=float, default=None, metavar="0-0.25",
                   help=f"weight of the tilt in combined_score (default {config.FORWARD_BLEND}, "
                        f"capped at {config.FORWARD_MAX_BLEND})")
    p.add_argument("--make-template", action="store_true",
                   help=f"create/extend {config.FUND_ATTRIBUTES_CSV} for this category (never overwrites your values) and exit")
    p.add_argument("--verbose", action="store_true", help="debug-level console output")
    p.add_argument("--quiet", action="store_true", help="warnings/errors and the final table only")
    p.add_argument("--log-file", default=None, metavar="PATH", help="also write a timestamped log file")
    return p.parse_args(argv)


def print_usage():
    print("Usage: python shortlist.py <category|file.csv> [--refresh] [--benchmark CODE|category|none] "
          "[--window YEARS] [--filter-mode relative|absolute|both] [--top N] "
          "[--forward|--no-forward] [--forward-blend X] [--make-template] "
          "[--verbose|--quiet] [--log-file PATH]")
    print('Examples: python shortlist.py "small cap"')
    print("          python shortlist.py midcap --benchmark category")
    print("          python shortlist.py my_funds.csv   (CSV with a 'scheme_code' column)")
    print(f"\nSupported categories: {', '.join(fund_universe.supported_categories())}")


def _run(args, run_info: dict) -> str:
    """The pipeline. Returns a short status string; fills `run_info` as it goes
    so the manifest reflects how far the run got."""
    if args.window is not None:
        config.RISK_WINDOW_YEARS = args.window
    if args.filter_mode:
        config.FILTER_MODE = args.filter_mode
    top_n = args.top or config.TOP_N
    force_refresh = args.refresh
    counts = run_info.setdefault("counts", {})

    query = " ".join(args.query)
    canonical = None
    try:
        if query.lower().endswith(".csv") and os.path.exists(query):
            log.info(f"Loading fund list from {query} ...")
            fund_list = load_fund_list_from_csv(query)
        else:
            canonical, fund_list = load_fund_list_from_category(query, force_refresh=force_refresh)
    except ValueError as exc:
        log.error(f"{exc}")
        return "error: unrecognized category"
    run_info["category"] = canonical
    counts["candidates"] = int(len(fund_list))

    if fund_list.empty:
        log.warning("No candidate funds found. Try a different category name.")
        return "no candidates"

    if args.make_template:
        kept, added = forward_signals.write_template(config.FUND_ATTRIBUTES_CSV, fund_list)
        log.info(f"{config.FUND_ATTRIBUTES_CSV}: {kept} existing row(s) kept untouched, {added} new row(s) added. "
                 f"Fill in expense_ratio (PERCENT, e.g. 0.72), aum_cr, aum_cr_12m_ago, manager_tenure_years, "
                 f"turnover_pct (optional) and as_of (YYYY-MM-DD) from AMC factsheets / AMFI data, then re-run "
                 f"with --forward.")
        run_info.setdefault("outputs", []).append(config.FUND_ATTRIBUTES_CSV)
        return "template written"

    excluded: dict = {}
    names = {r.scheme_code: getattr(r, "scheme_name_hint", "") for r in fund_list.itertuples(index=False)}

    log.info(f"Fetching NAV history for {len(fund_list)} funds ({config.FETCH_WORKERS} parallel workers) ...")
    nav_data = fetch_many(fund_list["scheme_code"].tolist(), force_refresh=force_refresh)
    counts["fetched"] = len(nav_data)
    for code in fund_list["scheme_code"]:
        if code not in nav_data:
            excluded.setdefault(code, []).append("NAV data could not be fetched")

    log.info("Computing metrics ...")
    metrics_df = build_metrics_table(fund_list, nav_data)
    if metrics_df.empty:
        log.error("No funds could be processed. Check scheme codes and network access.")
        write_excluded(excluded, names, config.EXCLUDED_CSV)
        return "error: no NAV data"
    names.update(dict(zip(metrics_df["scheme_code"], metrics_df["scheme_name"])))
    run_info["latest_nav_date"] = str(metrics_df["last_nav_date"].max())

    eligible = apply_data_quality_filters(metrics_df, canonical, excluded)
    counts["passed_data_quality"] = int(len(eligible))
    log.info(f"{len(eligible)} of {len(metrics_df)} funds passed the data-quality checks "
             f"(category match, fresh NAV, no suspicious jumps).")
    if eligible.empty:
        log.warning("No eligible funds remain.")
        write_excluded(excluded, names, config.EXCLUDED_CSV)
        return "no eligible funds"

    eligible, bench_label, bench_df = attach_benchmark_metrics(
        eligible, nav_data, canonical, args.benchmark, force_refresh)
    run_info["benchmark"] = bench_label

    # Forward-looking signal columns (always computed; they only affect the
    # ranking when the tilt is enabled -- see config.FORWARD_TILT_ENABLED / --forward).
    eligible = forward_signals.attach_nav_signals(eligible, nav_data, bench_df)
    eligible = forward_signals.attach_attribute_signals(eligible, canonical)
    valuation = forward_signals.category_valuation_note(canonical)
    if valuation:
        log.info(valuation["text"])
        run_info["category_valuation"] = valuation

    log.info(f"Applying hard filters (mode: {config.FILTER_MODE}; risk window: {config.RISK_WINDOW_YEARS:g}y) ...")
    survivors = apply_hard_filters(eligible, universe=eligible, excluded=excluded)
    counts["passed_hard_filters"] = int(len(survivors))
    log.info(f"{len(survivors)} of {len(eligible)} eligible funds passed the hard filters.")

    if survivors.empty:
        log.warning("No funds passed the filters. Consider relaxing thresholds in config.py.")
        write_excluded(excluded, names, config.EXCLUDED_CSV)
        return "no survivors"

    ranked = score_and_rank(survivors, universe=eligible)
    forward_on = True if args.forward else (False if args.no_forward else config.FORWARD_TILT_ENABLED)
    ranked, fwd_info = forward_signals.apply_forward_tilt(
        ranked, eligible, enabled=forward_on, blend=args.forward_blend)
    run_info["forward"] = {k: fwd_info[k] for k in ("enabled", "weights", "blend", "reranked")}
    if fwd_info["reranked"]:
        log.info(f"Forward tilt applied (blend {fwd_info['blend']:.0%}); ranking uses combined_score. "
                 f"Signals used: {', '.join(fwd_info['weights'])}.")
    ranked.to_csv(config.OUTPUT_CSV, index=False)
    outputs = run_info.setdefault("outputs", [])
    outputs.append(config.OUTPUT_CSV)
    log.info(f"Full ranked shortlist written to {config.OUTPUT_CSV}")
    write_excluded(excluded, names, config.EXCLUDED_CSV)
    if excluded:
        outputs.append(config.EXCLUDED_CSV)

    if config.EXPORT_EXCEL:
        excluded_rows = [{"scheme_code": c, "scheme_name": names.get(c, ""), "reasons": "; ".join(r)}
                         for c, r in excluded.items()]
        notes = {
            "Category": canonical or query,
            "Benchmark": bench_label or "none",
            "Risk window (years)": config.RISK_WINDOW_YEARS,
            "Filter mode": config.FILTER_MODE,
            "Scoring": f"{config.SCORING_METHOD} (winsorized at +/-{config.SCORE_WINSORIZE_Z})",
            "Eligible funds (scoring universe)": len(eligible),
            "Latest NAV date in data": run_info.get("latest_nav_date"),
            "Forward tilt": ("ON, blend %.0f%% (signals: %s)" % (fwd_info["blend"] * 100, ", ".join(fwd_info["weights"]))
                             if fwd_info["reranked"] else "off (columns shown for information only)"),
        }
        if valuation:
            notes["Category valuation"] = valuation["text"]
        if report.export_to_excel(ranked, config.OUTPUT_XLSX, excluded=excluded_rows, notes=notes):
            outputs.append(config.OUTPUT_XLSX)
            log.info(f"Formatted Excel report written to {config.OUTPUT_XLSX}")

    top = ranked.head(top_n)
    print(f"\n=== Top {len(top)} Shortlisted Funds ===\n")
    display_cols = ["rank", "scheme_name", "scheme_category", "cagr_3y", "cagr_5y",
                    "sortino_ratio", "alpha", "information_ratio", "down_capture",
                    "rolling_beat_pct", "max_drawdown", "composite_score"]
    if fwd_info["weights"]:
        display_cols.append("forward_tilt")
    if fwd_info["reranked"]:
        display_cols += ["combined_score", "rank_change"]
    print(format_for_display(top)[display_cols].to_string(index=False))
    return "ok"


MIN_PYTHON = (3, 10)
MIN_PANDAS = (2, 2)   # month-end resample alias "ME" needs pandas >= 2.2


def check_environment():
    """Fails fast with a readable message instead of a cryptic error deep in a
    run (the month-end alias 'ME' used throughout metrics.py needs pandas 2.2+)."""
    problems = []
    if sys.version_info < MIN_PYTHON:
        problems.append(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required "
                        f"(found {sys.version_info.major}.{sys.version_info.minor}).")
    try:
        pv = tuple(int(x) for x in pd.__version__.split(".")[:2])
    except ValueError:
        pv = MIN_PANDAS
    if pv < MIN_PANDAS:
        problems.append(f"pandas {MIN_PANDAS[0]}.{MIN_PANDAS[1]}+ is required (found {pd.__version__}); "
                        f"run: pip install -r requirements.txt")
    if problems:
        raise SystemExit("Environment check failed:\n  - " + "\n  - ".join(problems))


def main(argv=None):
    args = parse_args(argv)
    if not args.query:
        print_usage()
        return
    check_environment()

    setup_logging(verbose=args.verbose, quiet=args.quiet, log_file=args.log_file)
    run_info = {
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": " ".join(args.query),
        "arguments": {k: v for k, v in vars(args).items() if k != "query"},
        "status": "crashed",
    }
    try:
        run_info["status"] = _run(args, run_info)
    finally:
        # Always leave an audit trail, even if the run stopped early or crashed.
        try:
            manifest.write_manifest(config.MANIFEST_JSON, run_info)
            if run_info["status"] == "ok":
                log.info(f"Run manifest (settings, versions, benchmark, counts) written to {config.MANIFEST_JSON}")
        except OSError as exc:
            log.warning(f"could not write run manifest: {exc}")


if __name__ == "__main__":
    main()
