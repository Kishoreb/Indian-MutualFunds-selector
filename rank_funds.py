#!/usr/bin/env python3
"""
rank_funds.py
-------------
The scoring engine of mutual_fund_scoring_specification.md as a stand-alone program: it ranks funds
from a CSV of metric values you supply (no internet, no NAV download), using the weights in
weights.ini and the same scoring engine (scoring.py) as shortlist.py.

    python rank_funds.py --input funds.csv
    python rank_funds.py --input funds.csv --weights weights.ini --output-dir output --as-of-date 2026-10-09
    python rank_funds.py --input shortlisted_funds.csv                 # shortlist.py's own CSV works too
    python rank_funds.py --input funds.csv --category "small cap"      # only that category
    python rank_funds.py --input funds.csv --exploratory               # + a labelled cross-category list

INPUT CSV. One row per fund. Two column styles are understood (use either; units differ):

  spec style (percent numbers, as in the specification; 18.5 means 18.5%)
      fund_name, fund_category, plan_type, option, as_of_date (YYYY-MM-DD),
      return_3y, return_5y, rolling_consistency (0-100), benchmark_excess_return (percentage points),
      sharpe_ratio, sortino_ratio, maximum_drawdown (negative percent, e.g. -35.0),
      portfolio_quality (0-100), benchmark_name, data_source, data_quality_notes
      (expense_ratio may be present; it is NOT scored.)

  toolkit style (fractions, as in shortlisted_funds.csv; 0.185 means 18.5%)
      scheme_code, scheme_name, scheme_category, last_nav_date, cagr_1y, cagr_3y, cagr_5y,
      risk_return_ratio, sortino_ratio, rolling_positive_pct, sip_xirr, max_drawdown,
      benchmark_excess_return, rolling_beat_benchmark_pct, portfolio_quality, downside_capture,
      quartile_consistency, jensen_alpha, beta

  Mapping spec -> toolkit: return_3y=cagr_3y, return_5y=cagr_5y, rolling_consistency=
  rolling_beat_benchmark_pct, sharpe_ratio=risk_return_ratio, maximum_drawdown=max_drawdown.
  Only benchmark_excess_return has the same name in both styles but different units (pp vs fraction);
  --units spec|toolkit settles it (default: decided from the other columns; an ambiguous file is an error).

Only metrics that have a weight above 0 in weights.ini are scored; a weighted metric that is missing
from the file counts as missing for every fund (handled by the missing-data policy in weights.ini).

CHECKS (nothing is repaired or guessed):
  * a blank / NA cell is MISSING; a cell that is not a number, or is outside its possible range
    (e.g. a positive drawdown, a 0-100 score of 140), is INVALID: it is treated as missing and the fund is
    flagged INVALID(<column>); a real 0 is a valid value
  * identical duplicate rows are dropped; funds with the same name but different data are kept and flagged
    DUPLICATE_NAME; rows with no fund name are rejected
  * rows that are not Direct + Growth (when plan_type / option columns exist) are rejected unless
    --include-all-plans is given
  * stale as_of_date (older than the newest date in the category by more than config.STALE_NAV_DAYS) is flagged
    and, per config.EXCLUDE_STALE_FUNDS, excluded; an as_of_date after --as-of-date is excluded as inconsistent
  * funds are ranked WITHIN their fund_category; a category with fewer funds than min_group_size in
    weights.ini is marked LOW CONFIDENCE; a fund with too little of the weight measured is INSUFFICIENT_DATA

OUTPUT (in --output-dir, default "output"): ranked_funds.csv, ranked_funds.md, run_log.txt.
Exit status: 0 done; 1 nothing could be ranked; 2 bad command line, weights file or input file.
"""

import argparse
import os
import re
import sys

import numpy as np
import pandas as pd

import data_checks
import report_md
import scoring
import weights_loader

# --------------------------------------------------------------------------------------
# Column vocabulary
# --------------------------------------------------------------------------------------
# spec column -> (toolkit metric, factor that turns the spec's unit into the toolkit's unit)
SPEC_METRICS = {
    "return_3y": ("cagr_3y", 0.01),
    "return_5y": ("cagr_5y", 0.01),
    "rolling_consistency": ("rolling_beat_benchmark_pct", 0.01),
    "sharpe_ratio": ("risk_return_ratio", 1.0),
    "maximum_drawdown": ("max_drawdown", 0.01),
}
# Same name in both styles; the unit depends on the style (spec: percentage points, toolkit: fraction)
SHARED_METRICS = {"benchmark_excess_return": 0.01, "sortino_ratio": 1.0, "portfolio_quality": 1.0}
SPEC_ONLY_COLUMNS = {"fund_name", "fund_category", "as_of_date", "return_3y", "return_5y",
                     "rolling_consistency", "sharpe_ratio", "maximum_drawdown", "expense_ratio"}
TOOLKIT_ONLY_COLUMNS = {"scheme_code", "scheme_name", "scheme_category", "last_nav_date", "cagr_1y", "cagr_3y",
                        "cagr_5y", "risk_return_ratio", "rolling_positive_pct", "sip_xirr", "max_drawdown",
                        "rolling_beat_benchmark_pct", "downside_capture", "quartile_consistency",
                        "jensen_alpha", "beta"}
IDENTITY_TOOLKIT = {"scheme_code", "scheme_name", "scheme_category", "last_nav_date"}
IDENTITY = {"fund_name": "scheme_name", "fund_category": "scheme_category", "as_of_date": "last_nav_date"}
PASS_THROUGH = ["plan_type", "option", "benchmark_name", "data_source", "data_quality_notes"]
NOT_SCORED = {"expense_ratio"}

# possible range of each metric in toolkit units (inclusive); outside -> INVALID
RANGES = {
    "cagr_1y": (-1.0, 10.0), "cagr_3y": (-1.0, 10.0), "cagr_5y": (-1.0, 10.0), "sip_xirr": (-1.0, 10.0),
    "max_drawdown": (-1.0, 0.0), "benchmark_excess_return": (-1.0, 1.0),
    "rolling_positive_pct": (0.0, 1.0), "rolling_beat_benchmark_pct": (0.0, 1.0), "quartile_consistency": (0.0, 1.0),
    "portfolio_quality": (0.0, 100.0), "jensen_alpha": (-1.0, 1.0),
}
MISSING_TOKENS = {"", "na", "n/a", "nan", "none", "null", "-", "--", "nil"}


class InputError(Exception):
    """Fatal problem with the input file (exit status 2)."""


# --------------------------------------------------------------------------------------
# Reading the input
# --------------------------------------------------------------------------------------
def _clean_number(text):
    """-> (value, status) with status 'ok' | 'missing' | 'invalid'."""
    t = str(text).strip()
    if t.lower() in MISSING_TOKENS:
        return np.nan, "missing"
    t = t.replace(",", "").replace("%", "").strip()
    try:
        v = float(t)
    except ValueError:
        return np.nan, "invalid"
    if not np.isfinite(v):
        return np.nan, "invalid"
    return v, "ok"


def decide_units(columns, requested="auto"):
    """Unit style of the file. Only benchmark_excess_return is ambiguous (percentage points in spec style,
    a fraction in toolkit style), so the style is read from the OTHER metric columns; a file that mixes
    both styles AND has benchmark_excess_return is an error."""
    cols = set(columns)
    if requested in ("spec", "toolkit"):
        return requested
    has_spec = bool(cols & set(SPEC_METRICS))
    has_tk = bool(cols & (TOOLKIT_ONLY_COLUMNS - IDENTITY_TOOLKIT))
    if has_spec and has_tk and "benchmark_excess_return" in cols:
        raise InputError("the file mixes spec-style columns (e.g. return_3y, maximum_drawdown) and toolkit-style "
                         "columns (e.g. cagr_3y, max_drawdown), so the unit of benchmark_excess_return is unclear. "
                         "Pass --units spec (percent numbers) or --units toolkit (fractions).")
    if has_spec:
        return "spec"
    if has_tk:
        return "toolkit"
    return "spec" if cols & {"fund_name", "fund_category"} else "toolkit"


def load_input(path, units="auto", include_all_plans=False, reference_date=None):
    """Reads and standardises the CSV.
    Returns (df, info). df has toolkit-style columns plus input_<col> copies of every converted input column.
    info: {units, rejected [(line, name, reason)], dropped_duplicates, invalid [(line, name, column, text)],
           ignored [columns], missing_weighted [metrics], date_column bool}."""
    if not os.path.exists(path):
        raise InputError(f"input file not found: {path}")
    try:
        raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", skip_blank_lines=True)
    except Exception as exc:
        raise InputError(f"cannot read {path} as CSV ({exc})")
    if raw.empty:
        raise InputError(f"{path} has no data rows")
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    mangled = [c for c in raw.columns if re.search(r"\.\d+$", c) and re.sub(r"\.\d+$", "", c) in raw.columns]
    if mangled:
        names = sorted(set(re.sub(r"\.\d+$", "", c) for c in mangled))
        raise InputError("duplicate column name(s) in the header: " + ", ".join(names))
    raw["_line"] = np.arange(2, len(raw) + 2)          # line number in the file (header = line 1)
    cols = set(raw.columns)

    name_col = "fund_name" if "fund_name" in cols else "scheme_name" if "scheme_name" in cols else None
    if name_col is None:
        raise InputError("the file needs a fund_name column (or scheme_name)")
    if "fund_name" in cols and "scheme_name" in cols:
        raise InputError("the file has both fund_name and scheme_name; keep one")
    units = decide_units(cols, units)

    # metric column -> (toolkit metric, factor)
    mapping = {}
    for col, (metric, factor) in SPEC_METRICS.items():
        if col in cols:
            mapping[col] = (metric, factor)
    for col, factor in SHARED_METRICS.items():
        if col in cols:
            mapping[col] = (col, factor if units == "spec" else 1.0)
    for metric in weights_loader.KNOWN_METRICS:
        if metric in cols and metric not in mapping and metric not in SHARED_METRICS:
            mapping[metric] = (metric, 1.0)
    # two input columns that feed the same metric are a conflict, not something to pick between
    seen = {}
    for col, (metric, _) in mapping.items():
        if metric in seen:
            raise InputError(f"columns '{seen[metric]}' and '{col}' both give '{metric}'; keep one")
        seen[metric] = col
    if not mapping:
        raise InputError("no metric columns found. Expected e.g. return_3y, return_5y, rolling_consistency, "
                         "benchmark_excess_return, sharpe_ratio, sortino_ratio, maximum_drawdown, portfolio_quality "
                         "(or the toolkit names cagr_3y, max_drawdown, ...)")
    ignored = sorted(c for c in cols if c in NOT_SCORED)

    rejected, invalid = [], []
    # 1. identical duplicate rows
    key_cols = [c for c in raw.columns if c != "_line"]
    dup_mask = raw.duplicated(subset=key_cols, keep="first")
    first_line = {}
    for i, row in raw.iterrows():
        first_line.setdefault(tuple(row[key_cols]), row["_line"])
    for i in raw.index[dup_mask]:
        row = raw.loc[i]
        rejected.append((int(row["_line"]), row[name_col], f"duplicate of line {first_line[tuple(row[key_cols])]}"))
    work = raw[~dup_mask].copy()
    n_dup = int(dup_mask.sum())

    # 2. no name
    blank = work[name_col].str.strip() == ""
    for _, row in work[blank].iterrows():
        rejected.append((int(row["_line"]), "", "no fund name"))
    work = work[~blank].copy()

    # 3. plan / option
    flags_extra = {}
    if ("plan_type" in cols or "option" in cols) and len(work):
        plan = work["plan_type"].str.lower() if "plan_type" in cols else pd.Series("direct", index=work.index)
        opt = work["option"].str.lower() if "option" in cols else pd.Series("growth", index=work.index)
        direct = plan.str.contains("direct", na=False)
        growth = opt.str.contains("growth", na=False) & ~opt.str.contains("idcw|dividend|payout", na=False)
        bad = ~(direct & growth)
        if "plan_type" not in cols:
            bad = ~growth
        if "option" not in cols:
            bad = ~direct
        if include_all_plans:
            for i in work.index[bad]:
                flags_extra.setdefault(i, []).append("NOT_DIRECT_GROWTH")
        else:
            for i in work.index[bad]:
                row = work.loc[i]
                rejected.append((int(row["_line"]), row[name_col],
                                 f"not Direct Growth (plan_type='{row.get('plan_type', '')}', option='{row.get('option', '')}'); "
                                 f"use --include-all-plans to rank it anyway"))
            work = work[~bad].copy()
    if work.empty:
        raise InputError("no usable rows left after rejecting duplicates, unnamed and non-Direct-Growth rows")

    # 4. build the standard frame
    out = pd.DataFrame(index=work.index)
    out["scheme_name"] = work[name_col].str.strip()
    cat_col = "fund_category" if "fund_category" in cols else "scheme_category" if "scheme_category" in cols else None
    out["scheme_category"] = work[cat_col].str.strip() if cat_col else ""
    if "scheme_code" in cols:
        out["scheme_code"] = work["scheme_code"].str.strip()
        if (out["scheme_code"] == "").any():
            raise InputError("scheme_code is present but blank on some rows; fill it in or remove the column")
    else:
        out["scheme_code"] = ["row" + str(int(n)) for n in work["_line"]]       # stable id = line number in the file
    out["_line"] = work["_line"].astype(int)
    date_col = "as_of_date" if "as_of_date" in cols else "last_nav_date" if "last_nav_date" in cols else None
    flags = {i: list(flags_extra.get(i, [])) for i in work.index}
    if date_col:
        parsed = pd.to_datetime(work[date_col].str.strip(), format="%Y-%m-%d", errors="coerce")
        bad_date = parsed.isna() & (work[date_col].str.strip().str.lower().isin(MISSING_TOKENS) == False)
        for i in work.index[bad_date]:
            flags[i].append("INVALID(as_of_date: use YYYY-MM-DD)")
        out["last_nav_date"] = parsed
    else:
        out["last_nav_date"] = pd.NaT
    for c in PASS_THROUGH:
        if c in cols:
            out[c] = work[c].str.strip()

    for col, (metric, factor) in mapping.items():
        vals = []
        for i in work.index:
            v, status = _clean_number(work.at[i, col])
            if status == "ok":
                v = v * factor
                lo_hi = RANGES.get(metric)
                if lo_hi and not (lo_hi[0] <= v <= lo_hi[1]):
                    status = "invalid"
            if status == "invalid":
                flags[i].append(f"INVALID({col})")
                invalid.append((int(work.at[i, "_line"]), work.at[i, name_col], col, work.at[i, col]))
                v = np.nan
            vals.append(v)
        out[metric] = vals
        out[f"input_{col}"] = work[col].values
    for c in ignored:
        out[f"input_{c}"] = work[c].values
    out["input_flags"] = ["; ".join(flags[i]) for i in work.index]
    out = out.reset_index(drop=True)
    return out, {"units": units, "rejected": sorted(rejected), "dropped_duplicates": n_dup, "invalid": invalid,
                 "ignored": ignored, "date_column": date_col is not None, "has_category": cat_col is not None,
                 "metric_columns": {c: m for c, (m, _) in mapping.items()}}


# --------------------------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------------------------
def rank_group(df, cfg, reference_date, log, has_dates=True):
    """Data checks + scoring for one category. Returns (ranked, excluded, as_of)."""
    excluded = []
    flags, info = data_checks.check_table(df, stale_days=cfg.STALE_NAV_DAYS, reference_date=reference_date)
    for w in info["warnings"]:
        if has_dates or "not current" not in w:
            log.warn(w)
    df = df.copy()
    merged = []
    for i, f in enumerate(flags):
        f = [x for x in f if has_dates or x != "NO_NAV_DATE"]
        pre = df["input_flags"].iloc[i]
        merged.append("; ".join(([pre] if pre else []) + f))
    df["data_flags"] = merged
    df = df.drop(columns=["input_flags"])

    drop = pd.Series(False, index=df.index)
    if has_dates and reference_date is not None:
        fut = df["last_nav_date"] > pd.Timestamp(reference_date)
        for i in df.index[fut]:
            excluded.append((df.at[i, "scheme_code"], df.at[i, "scheme_name"],
                             [f"as_of_date {df.at[i, 'last_nav_date']:%Y-%m-%d} is after --as-of-date"]))
            df.at[i, "data_flags"] = "; ".join(x for x in [df.at[i, "data_flags"], "FUTURE_DATE"] if x)
        drop |= fut
    if cfg.EXCLUDE_STALE_FUNDS:
        stale = df["data_flags"].str.contains("STALE_NAV", regex=False)
        for i in df.index[stale]:
            excluded.append((df.at[i, "scheme_code"], df.at[i, "scheme_name"],
                             [x for x in df.at[i, "data_flags"].split("; ") if x.startswith("STALE_NAV")]))
        drop |= stale
    df = df[~drop].reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(), excluded, info["as_of"]
    ranked = scoring.score_and_rank(df, cfg.SCORE_WEIGHTS, policy=cfg.MISSING_DATA_POLICY,
                                    min_coverage=cfg.MIN_SCORE_COVERAGE, method=cfg.SCORING_METHOD,
                                    min_group_size=cfg.MIN_GROUP_SIZE)
    return ranked, excluded, info["as_of"]


def _parse_args(argv):
    ap = argparse.ArgumentParser(
        prog="rank_funds.py",
        description="Rank mutual funds from a CSV of metric values using weights.ini (see the top of this file).")
    ap.add_argument("--input", required=True, help="CSV with one row per fund")
    ap.add_argument("--weights", help="weights file (default: weights.ini next to config.py)")
    ap.add_argument("--output-dir", default="output", help="folder for the output files (default: output)")
    ap.add_argument("--as-of-date", help="YYYY-MM-DD reference date for staleness; fund dates after it are excluded "
                                         "(default: the newest as_of_date in each category)")
    ap.add_argument("--category", action="append", default=[], help="rank only this category (repeat for several)")
    ap.add_argument("--units", choices=["auto", "spec", "toolkit"], default="auto",
                    help="spec = percent numbers, toolkit = fractions (default: decided from the column names)")
    ap.add_argument("--include-all-plans", action="store_true",
                    help="also rank rows that are not Direct + Growth (they are flagged NOT_DIRECT_GROWTH)")
    ap.add_argument("--ignore-category", action="store_true",
                    help="rank every row together (exploratory only) instead of by fund_category")
    ap.add_argument("--exploratory", action="store_true", help="also write a labelled cross-category list")
    ap.add_argument("--top-n", type=int, default=15, help="funds shown per category in ranked_funds.md (default 15)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        import config                                   # loads the default weights.ini
        if args.weights:
            config.apply_weights(args.weights)
    except weights_loader.WeightsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    reference = None
    if args.as_of_date:
        reference = pd.to_datetime(args.as_of_date, format="%Y-%m-%d", errors="coerce")
        if pd.isna(reference):
            print(f"ERROR: --as-of-date '{args.as_of_date}' is not a valid YYYY-MM-DD date", file=sys.stderr)
            return 2
    if args.top_n < 1:
        print("ERROR: --top-n must be at least 1", file=sys.stderr)
        return 2

    log = report_md.RunLog()
    log.add(f"Run started {log.started:%Y-%m-%d %H:%M}")
    log.add(f"Input file: {os.path.abspath(args.input)}")
    log.add(f"Weights file: {config.WEIGHTS_FILE} (version {config.WEIGHTS_VERSION}); policy {config.MISSING_DATA_POLICY}; "
            f"method {config.SCORING_METHOD}; coverage floor {config.MIN_SCORE_COVERAGE:.0%}; low-confidence below "
            f"{config.MIN_GROUP_SIZE} funds")
    log.add("Weights %: " + ", ".join(f"{m}={w * 100:g}" for m, w in config.SCORE_WEIGHTS.items() if w > 0))

    try:
        df, info = load_input(args.input, args.units, args.include_all_plans, reference)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    log.add(f"Input read: {len(df)} usable row(s); units = {info['units']} "
            f"({'percent numbers' if info['units'] == 'spec' else 'fractions'}); "
            f"{info['dropped_duplicates']} identical duplicate row(s) dropped.")
    for c in info["ignored"]:
        log.add(f"Column '{c}' is present but is not scored (expense ratio is excluded by design).")
    if info["rejected"]:
        log.add(f"{len(info['rejected'])} row(s) rejected:")
        for line, name, why in info["rejected"]:
            log.add(f"  - line {line}: {name or '(no name)'} -- {why}")
    for line, name, col, text in info["invalid"]:
        log.warn(f"line {line}: {name}: '{text}' in '{col}' is not a valid value; treated as missing")
    have = set(info["metric_columns"].values())
    weighted = [m for m, w in config.SCORE_WEIGHTS.items() if w > 0]
    absent = [m for m in weighted if m not in have]
    if absent:
        log.warn("weights.ini gives weight to " + ", ".join(absent) + ", which the input file does not have; "
                 "they count as missing for every fund (see the missing-data policy)")
    if not [m for m in weighted if m in have]:
        print("ERROR: none of the metrics that have a weight in weights.ini are in the input file", file=sys.stderr)
        log.add("ERROR: none of the weighted metrics are in the input file")
        _write_log(log, args.output_dir)
        return 2
    if info["units"] == "toolkit" and "benchmark_excess_return" in have:
        ex = df["benchmark_excess_return"].abs().max()
        if pd.notna(ex) and ex > 0.5:
            log.warn(f"benchmark_excess_return reaches {ex:.2f} (= {ex * 100:.0f} points) in fraction units; "
                     f"if the file holds percentage points pass --units spec")
    if info["units"] == "spec" and "benchmark_excess_return" in have and len(df) >= 3:
        ex = df["benchmark_excess_return"].abs().max()
        if pd.notna(ex) and ex < 0.01:
            log.warn("every benchmark_excess_return is under 1 percentage point; if the file holds fractions "
                     "pass --units toolkit")
    if not info["date_column"]:
        log.warn("no as_of_date column: staleness cannot be checked and no data date is shown")

    if args.ignore_category or not info["has_category"]:
        if not info["has_category"] and not args.ignore_category:
            print("ERROR: the file has no fund_category column. Add one, or pass --ignore-category to rank all rows "
                  "together (exploratory only).", file=sys.stderr)
            log.add("ERROR: no fund_category column")
            _write_log(log, args.output_dir)
            return 2
        df["scheme_category"] = "ALL FUNDS (exploratory: categories ignored)"
        log.warn("categories ignored: this single list is EXPLORATORY; funds with different mandates are not comparable")

    cats = sorted(df["scheme_category"].replace("", "(no category)").unique(), key=str.lower)
    df["scheme_category"] = df["scheme_category"].replace("", "(no category)")
    if args.category:
        wanted = {c.strip().lower() for c in args.category}
        unknown = sorted(wanted - {c.lower() for c in cats})
        if unknown:
            print(f"ERROR: category not in the file: {', '.join(unknown)}. Categories found: {', '.join(cats)}",
                  file=sys.stderr)
            return 2
        cats = [c for c in cats if c.lower() in wanted]

    groups, pool = [], []
    for cat in cats:
        sub = df[df["scheme_category"] == cat].reset_index(drop=True)
        log.add(f"\n=== {cat}: {len(sub)} fund(s) ===")
        ranked, excluded, as_of = rank_group(sub, config, reference, log, has_dates=info["date_column"])
        for code, name, why in excluded:
            log.add(f"  excluded: {name} ({code}): {', '.join(why)}")
        if ranked.empty:
            log.warn(f"{cat}: nothing left to rank")
            groups.append({"name": cat, "ranked": pd.DataFrame(), "excluded": excluded, "as_of": as_of})
            continue
        ranked.insert(0, "group", cat)
        pool.append(ranked.drop(columns=["rank", "status", "confidence", "composite_score", "final_score_0_100",
                                         "score_coverage", "score_missing"] +
                                [c for c in ranked.columns if c.startswith(("score_", "contrib_"))],
                                errors="ignore"))
        groups.append({"name": cat, "ranked": ranked, "excluded": excluded, "as_of": as_of})
        n_ok = int((ranked["status"] == "RANKED").sum())
        log.add(f"{cat}: {n_ok} ranked, {int((ranked['status'] == 'INSUFFICIENT_DATA').sum())} with insufficient data; "
                f"confidence {ranked['confidence'].iloc[0]}")

    ranked_groups = [g for g in groups if len(g["ranked"])]
    out_dir = args.output_dir
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        print(f"ERROR: cannot create {out_dir}: {exc}", file=sys.stderr)
        return 2
    if not ranked_groups or not any((g["ranked"]["status"] == "RANKED").any() for g in ranked_groups):
        log.warn("nothing could be ranked")
        _write_log(log, out_dir)
        print(f"\nRun log written to {os.path.join(out_dir, 'run_log.txt')}")
        return 1

    exploratory = None
    if args.exploratory and len(ranked_groups) > 1:
        pooled = pd.concat(pool, ignore_index=True).drop(columns=["group", "data_flags"], errors="ignore")
        pooled["data_flags"] = pd.concat([g["ranked"]["data_flags"] for g in ranked_groups], ignore_index=True).values
        exploratory = scoring.score_and_rank(pooled, config.SCORE_WEIGHTS, policy=config.MISSING_DATA_POLICY,
                                             min_coverage=config.MIN_SCORE_COVERAGE, method=config.SCORING_METHOD,
                                             min_group_size=config.MIN_GROUP_SIZE)
        exploratory.insert(0, "group", "EXPLORATORY cross-category")
        if "volatility" not in exploratory.columns:
            exploratory["volatility"] = np.nan
        log.add("Cross-category list is EXPLORATORY: categories have different risk profiles.")
    elif args.exploratory:
        log.add("--exploratory needs at least two categories; no cross-category list written.")

    all_ranked = pd.concat([g["ranked"] for g in ranked_groups], ignore_index=True)
    csv_path = os.path.join(out_dir, "ranked_funds.csv")
    _output_frame(all_ranked).to_csv(csv_path, index=False)
    log.add(f"\nRanked list written to {csv_path}")
    if exploratory is not None:
        exp_path = os.path.join(out_dir, "ranked_funds_exploratory.csv")
        _output_frame(exploratory).to_csv(exp_path, index=False)
        log.add(f"Exploratory cross-category list written to {exp_path}")

    md_path = os.path.join(out_dir, "ranked_funds.md")
    note = (f"metrics were supplied in {os.path.basename(args.input)} ({info['units']} style units) and are used as given; "
            f"their definitions (periods, benchmark, return basis) are those of whoever produced the file, see the "
            f"data_source / data_quality_notes columns. Funds are compared only within their category.")
    extra = []
    if info["rejected"] or info["invalid"] or info["dropped_duplicates"]:
        lines = []
        for line, name, why in info["rejected"]:
            lines.append(f"- line {line}: {name or '(no name)'} -- rejected: {why}")
        for line, name, col, text in info["invalid"]:
            lines.append(f"- line {line}: {name} -- '{text}' in `{col}` is not valid; treated as missing")
        extra.append(("Input rows with problems", lines))
    sources = sorted({str(x) for x in df.get("data_source", pd.Series(dtype=str)) if str(x).strip()})
    report_md.write_markdown(md_path, ranked_groups, config, log, exploratory, top_n=args.top_n,
                             sources=sources or None, input_note=note, extra_sections=extra)
    log.add(f"Markdown report written to {md_path}")
    for g in ranked_groups:
        top = g["ranked"][g["ranked"]["status"] == "RANKED"].head(args.top_n)
        log.add(f"\n=== {g['name']}: top {len(top)} ===")
        for _, r in top.iterrows():
            log.add(f"  {int(r['rank']):>3}. {r['scheme_name']}  score {r['final_score_0_100']:.1f}  "
                    f"(weight measured {r['score_coverage'] * 100:.0f}%){'  ' + r['data_flags'] if r['data_flags'] else ''}")
        if str(g["ranked"]["confidence"].iloc[0]).startswith("LOW"):
            log.add(f"  LOW CONFIDENCE: {g['ranked']['confidence'].iloc[0]}")
    _write_log(log, out_dir)
    print(f"\nFiles written to {os.path.abspath(out_dir)}: ranked_funds.csv, ranked_funds.md, run_log.txt")
    return 0


def _write_log(log, out_dir):
    try:
        os.makedirs(out_dir, exist_ok=True)
        log.write(os.path.join(out_dir, "run_log.txt"))
    except OSError:
        pass


def _output_frame(df):
    """Column order for the CSV: identity and result first, then the metrics, scores and the inputs as supplied."""
    first = ["group", "rank", "status", "confidence", "scheme_code", "scheme_name", "scheme_category",
             "final_score_0_100", "composite_score", "score_coverage", "score_missing", "last_nav_date", "data_flags"]
    first = [c for c in first if c in df.columns]
    rest = [c for c in df.columns if c not in first and c != "_line"]
    out = df[first + rest].copy()
    for c in out.columns:
        if c == "last_nav_date":
            out[c] = pd.to_datetime(out[c]).dt.strftime("%Y-%m-%d")
    if "rank" in out.columns:
        out["rank"] = pd.to_numeric(out["rank"], errors="coerce").astype("Int64")
    return out


if __name__ == "__main__":
    sys.exit(main())
