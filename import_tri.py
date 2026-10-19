#!/usr/bin/env python3
"""
import_tri.py
-------------
Turns Total Return Index (TRI) history you downloaded from NSE (or any CSV with a date column and an
index-value column) into the file benchmark.py looks for: data/benchmarks/<category>.csv with columns
date,nav. A real TRI replaces the index-fund proxy, which removes the small flattering bias in the
excess-return and rolling-beat metrics.

    python import_tri.py --category "small cap" smallcap250_tri_2015_2020.csv smallcap250_tri_2020_2026.csv
    python import_tri.py --list                      # categories and the index each one expects

Several input files (NSE limits the date range per download) are merged; duplicate dates are removed.
Checks: dates parse, values are positive numbers, no big gaps, history length, how recent the last date is.
Use the TRI (Total Returns Index), not the price index, so the fund (which reinvests dividends) is compared
like for like.
"""

import argparse
import os
import sys

import pandas as pd

import config


def filename_for(key: str) -> str:
    # must match benchmark.BenchmarkProvider._load
    return key.replace(" & ", " and ").replace(" ", "_") + ".csv"


def read_series(path: str) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=object, skip_blank_lines=True)
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    date_col = next((c for c in raw.columns if "date" in c), None)
    val_col = next((c for c in raw.columns if any(k in c for k in ("close", "tri", "total return", "value", "nav", "index"))
                    and c != date_col), None)
    if date_col is None or val_col is None:
        raise ValueError(f"{path}: needs a date column and an index-value column (found {list(raw.columns)})")
    df = pd.DataFrame({
        "date": pd.to_datetime(raw[date_col].astype(str).str.strip(), dayfirst=True, errors="coerce", format="mixed"),
        "nav": pd.to_numeric(raw[val_col].astype(str).str.replace(",", "").str.strip(), errors="coerce"),
    })
    bad = int(df["date"].isna().sum() + df["nav"].isna().sum())
    df = df.dropna()
    df = df[df["nav"] > 0]
    return df, bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Import TRI history as a benchmark CSV for a category.")
    ap.add_argument("files", nargs="*", help="one or more CSV files for the same index")
    ap.add_argument("--category", help="category key, e.g. 'small cap' (see --list)")
    ap.add_argument("--list", action="store_true", help="show categories and the benchmark each expects")
    ap.add_argument("--out-dir", default=None, help="default: config.BENCHMARK_DIR")
    a = ap.parse_args(argv)

    if a.list:
        for key, spec in config.BENCHMARKS.items():
            print(f"  {key:<16} {spec['label']:<36} -> {os.path.join(config.BENCHMARK_DIR, filename_for(key))}")
        print("  (sectoral/thematic funds have no benchmark)")
        return 0
    if not a.category or not a.files:
        print("ERROR: give --category and at least one input file (or use --list)", file=sys.stderr)
        return 2
    key = a.category.strip().lower()
    if key not in config.BENCHMARKS:
        print(f"ERROR: unknown category '{a.category}'. Use one of: {', '.join(config.BENCHMARKS)}", file=sys.stderr)
        return 2

    parts, skipped = [], 0
    for f in a.files:
        try:
            df, bad = read_series(f)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        skipped += bad
        parts.append(df)
    series = pd.concat(parts).drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    if len(series) < 250:
        print(f"ERROR: only {len(series)} usable rows; need a few years of daily history", file=sys.stderr)
        return 1

    out_dir = a.out_dir or config.BENCHMARK_DIR
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, filename_for(key))
    series.assign(date=series["date"].dt.strftime("%Y-%m-%d")).to_csv(out, index=False)

    years = (series["date"].iloc[-1] - series["date"].iloc[0]).days / 365.25
    print(f"Wrote {len(series)} rows ({series['date'].iloc[0].date()} to {series['date'].iloc[-1].date()}, "
          f"{years:.1f} years) to {out}  [expected index: {config.BENCHMARKS[key]['label']}]")
    gaps = series["date"].diff().dt.days
    if gaps.max() > 10:
        at = series.loc[gaps.idxmax(), "date"].date()
        print(f"WARNING: largest gap is {int(gaps.max())} days, ending {at}; a file for that period may be missing")
    age = (pd.Timestamp.now().normalize() - series["date"].iloc[-1]).days
    if age > config.BENCHMARK_MAX_STALENESS_DAYS + 5:
        print(f"WARNING: the last date is {age} days old; benchmark metrics are left empty for funds whose NAV "
              f"is more than {config.BENCHMARK_MAX_STALENESS_DAYS} days newer. Download recent data.")
    if years < 5:
        print(f"WARNING: only {years:.1f} years of history; rolling-window metrics need 3y plus a year or more")
    if skipped:
        print(f"Note: {skipped} unreadable cell(s) skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
