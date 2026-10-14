"""
shortlist.py
------------
Main entry point. Given a fund category (e.g. "small cap", "midcap",
"large cap", "flexi cap", "elss" ...), this:

  1. Looks up every matching Direct+Growth fund from AMFI's scheme master
     (via fund_universe.py)
  2. Fetches/loads NAV history for each candidate
  3. Computes CAGR (1y/3y/5y), volatility, risk-adjusted return ratio (Sharpe-
     style), Sortino ratio (downside-only risk-adjusted return), rolling
     3-year return consistency, SIP XIRR, and max drawdown (via metrics.py),
     plus benchmark-relative metrics -- excess return over, and rolling
     win-rate against, the category benchmark (via benchmark.py), and a
     0-100 portfolio-quality score from disclosed holdings files
     (via portfolio_quality.py; missing where no holdings file is found)
  4. Applies hard filters, ranks the survivors with a weighted composite
     score, and writes the result to both CSV and a formatted Excel file.

Usage:
    python shortlist.py "small cap"
    python shortlist.py midcap
    python shortlist.py "large cap" --refresh     # force re-download of NAV/scheme data
    python shortlist.py "small cap" --fetch-holdings   # also download AMC portfolio files first

You can also still pass a CSV of your own scheme codes if you'd rather
choose funds manually:
    python shortlist.py my_funds.csv              # CSV with a 'scheme_code' column
"""

import os
import sys

import pandas as pd

import benchmark
import config
import fund_universe
import holdings_fetch
import portfolio_quality
import report
from fetch_nav_data import get_nav_history, get_scheme_meta
from metrics import compute_all_metrics


def load_fund_list_from_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "scheme_code" not in df.columns:
        raise ValueError("Input CSV must contain a 'scheme_code' column.")
    df["scheme_code"] = df["scheme_code"].astype(str)
    return df


def load_fund_list_from_category(category_input: str, force_refresh: bool = False) -> pd.DataFrame:
    print(f"Looking up '{category_input}' funds from the AMFI scheme master ...")
    canonical, candidates = fund_universe.find_candidates(category_input, force_refresh=force_refresh)
    print(f"Resolved category: '{canonical}'. Found {len(candidates)} candidate Direct-Growth fund(s).")

    if not candidates:
        return pd.DataFrame(columns=["scheme_code", "scheme_name_hint"])

    if len(candidates) > config.MAX_FUNDS_TO_SCAN:
        candidates = sorted(candidates, key=lambda c: c["scheme_name_hint"])
        print(f"Capping full analysis to {config.MAX_FUNDS_TO_SCAN} of {len(candidates)} candidates, "
              f"alphabetically (this is a safety limit, NOT a quality pre-filter -- raise "
              f"MAX_FUNDS_TO_SCAN in config.py to scan every match).")
        candidates = candidates[:config.MAX_FUNDS_TO_SCAN]

    df = pd.DataFrame(candidates)
    df.attrs["category_key"] = canonical  # used as the benchmark fallback
    return df


def build_metrics_table(fund_list: pd.DataFrame, force_refresh: bool = False) -> pd.DataFrame:
    rows = []
    total = len(fund_list)
    default_key = fund_list.attrs.get("category_key")
    bench_provider = benchmark.BenchmarkProvider(force_refresh=force_refresh) if config.BENCHMARK_ENABLED else None
    pq_index = portfolio_quality.PortfolioIndex() if config.PORTFOLIO_QUALITY_ENABLED else None
    if pq_index is not None:
        print(f"Holdings files: {pq_index.files_read} workbook(s) read, {len(pq_index.entries)} portfolio sheet(s) "
              f"parsed under {pq_index.root}/")
        for w in pq_index.warnings:
            print(f"  WARNING: {w}")

    for i, row in enumerate(fund_list.itertuples(index=False), 1):
        code = row.scheme_code
        print(f"[{i}/{total}] Processing scheme {code} ...")
        try:
            nav_df = get_nav_history(code, force_refresh=force_refresh)
        except Exception as exc:
            print(f"  WARNING: skipping {code}, could not fetch NAV data: {exc}")
            continue

        meta = get_scheme_meta(code)
        m = compute_all_metrics(
            nav_df, config.RISK_FREE_RATE,
            sip_years=config.SIP_YEARS, sip_monthly_amount=config.SIP_MONTHLY_AMOUNT,
            rolling_window_years=config.ROLLING_WINDOW_YEARS,
        )
        m["scheme_code"] = code
        m["scheme_name"] = meta.get("scheme_name", "") or getattr(row, "scheme_name_hint", "")
        m["fund_house"] = meta.get("fund_house", "")
        m["scheme_category"] = meta.get("scheme_category", "")
        m.update(benchmark.metrics_for_fund(nav_df, bench_provider, m["scheme_category"], default_key))
        m.update(portfolio_quality.fields_for_fund(pq_index, m["scheme_name"]))
        rows.append(m)

    if bench_provider is not None:
        lines = bench_provider.describe()
        if lines:
            print("\nBenchmarks used:")
            print("\n".join(lines))

    if pq_index is not None and rows:
        scored_n = sum(1 for r in rows if r.get("portfolio_quality") is not None)
        print(f"\nPortfolio quality scored for {scored_n} of {len(rows)} funds "
              f"(the rest have no usable holdings file; see pq_note in the CSV).")

    cols = ["scheme_code", "scheme_name", "fund_house", "scheme_category",
            "cagr_1y", "cagr_3y", "cagr_5y", "volatility", "risk_return_ratio",
            "sortino_ratio", "downside_deviation", "rolling_avg", "rolling_min",
            "rolling_positive_pct", "rolling_std", "sip_xirr",
            "max_drawdown", "history_years",
            "benchmark_name", "benchmark_proxy", "benchmark_cagr",
            "benchmark_excess_return", "rolling_beat_benchmark_pct", "benchmark_windows",
            "portfolio_quality", "pq_coverage", "pq_top10_pct", "pq_holdings", "pq_top_sector_pct",
            "pq_largemid_pct", "pq_cash_pct", "pq_as_of", "pq_source", "pq_note"]
    return pd.DataFrame(rows, columns=cols)


def apply_hard_filters(df: pd.DataFrame) -> pd.DataFrame:
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
        print("\nFunds excluded by hard filters:")
        for code, why in reasons.items():
            name = kept.loc[kept["scheme_code"] == code, "scheme_name"].values
            name = name[0] if len(name) else code
            print(f"  - {code} ({name}): {', '.join(why)}")

    survivors = kept[~kept["scheme_code"].isin(reasons.keys())].reset_index(drop=True)
    return survivors


def score_and_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Z-scores each metric across the surviving funds and combines them
    into a single weighted composite score. max_drawdown is inverted
    (less negative = better) before scoring. Metrics with missing values
    for a given fund are neutrally treated (z=0, i.e. "average") rather
    than excluding the fund, since not every fund has enough history for
    every metric (e.g. rolling stats need extra years of data)."""
    if df.empty:
        return df

    scored = df.copy()
    weights = config.SCORE_WEIGHTS
    weight_sum = sum(weights.values()) or 1.0

    z_cols = {}
    for metric, weight in weights.items():
        values = scored[metric].astype(float)
        if metric == "max_drawdown":
            values = -values  # flip sign: smaller drawdown -> higher is better

        mean, std = values.mean(), values.std()
        if std == 0 or pd.isna(std):
            z = values.fillna(0) * 0  # no variance -> no discriminating power
        else:
            z = ((values - mean) / std).fillna(0)  # missing metric -> treated as average
        z_cols[metric] = z * (weight / weight_sum)

    scored["composite_score"] = sum(z_cols.values())
    scored = scored.sort_values("composite_score", ascending=False).reset_index(drop=True)
    scored.insert(0, "rank", range(1, len(scored) + 1))
    return scored


def format_for_display(df: pd.DataFrame) -> pd.DataFrame:
    pretty = df.copy()
    pct_cols = ["cagr_1y", "cagr_3y", "cagr_5y", "volatility", "max_drawdown",
                "downside_deviation", "rolling_avg", "rolling_min", "rolling_std",
                "rolling_positive_pct", "sip_xirr",
                "benchmark_cagr", "benchmark_excess_return", "rolling_beat_benchmark_pct",
                "pq_coverage"]
    for c in pct_cols:
        if c in pretty.columns:
            pretty[c] = pretty[c].apply(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "N/A")
    for c in ["risk_return_ratio", "sortino_ratio"]:
        if c in pretty.columns:
            pretty[c] = pretty[c].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "N/A")
    if "portfolio_quality" in pretty.columns:
        pretty["portfolio_quality"] = pretty["portfolio_quality"].apply(lambda v: f"{v:.0f}" if pd.notna(v) else "N/A")
    pretty["composite_score"] = pretty["composite_score"].apply(lambda v: f"{v:.3f}")
    return pretty


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force_refresh = "--refresh" in sys.argv
    if "--fetch-holdings" in sys.argv:
        holdings_fetch.fetch_all()
        print()

    if not args:
        print("Usage: python shortlist.py <category> [--refresh] [--fetch-holdings]")
        print('Examples: python shortlist.py "small cap"')
        print("          python shortlist.py midcap")
        print("          python shortlist.py my_funds.csv   (CSV with a 'scheme_code' column)")
        print(f"\nSupported categories: {', '.join(fund_universe.supported_categories())}")
        return

    query = " ".join(args)

    try:
        if query.lower().endswith(".csv") and os.path.exists(query):
            print(f"Loading fund list from {query} ...")
            fund_list = load_fund_list_from_csv(query)
        else:
            fund_list = load_fund_list_from_category(query, force_refresh=force_refresh)
    except ValueError as exc:
        print(f"\n{exc}")
        return

    if fund_list.empty:
        print("No candidate funds found. Try a different category name.")
        return

    print(f"\nFetching NAV history and computing metrics for {len(fund_list)} funds ...")
    metrics_df = build_metrics_table(fund_list, force_refresh=force_refresh)

    if metrics_df.empty:
        print("No funds could be processed. Check scheme codes and network access.")
        return

    print(f"\nApplying hard filters (min 1y/3y/5y CAGR, max volatility, min risk-return ratio) ...")
    survivors = apply_hard_filters(metrics_df)
    print(f"\n{len(survivors)} of {len(metrics_df)} funds passed the hard filters.")

    if survivors.empty:
        print("No funds passed the filters. Consider relaxing thresholds in config.py.")
        return

    ranked = score_and_rank(survivors)
    ranked.to_csv(config.OUTPUT_CSV, index=False)
    print(f"\nFull ranked shortlist written to {config.OUTPUT_CSV}")

    if config.EXPORT_EXCEL:
        if report.export_to_excel(ranked, config.OUTPUT_XLSX):
            print(f"Formatted Excel report written to {config.OUTPUT_XLSX}")

    top = ranked.head(config.TOP_N)
    print(f"\n=== Top {len(top)} Shortlisted Funds ===\n")
    display_cols = ["rank", "scheme_name", "scheme_category", "cagr_1y", "cagr_3y",
                     "cagr_5y", "sortino_ratio", "rolling_positive_pct", "sip_xirr",
                     "max_drawdown", "benchmark_excess_return", "rolling_beat_benchmark_pct",
                     "portfolio_quality", "composite_score"]
    print(format_for_display(top)[display_cols].to_string(index=False))


if __name__ == "__main__":
    main()
