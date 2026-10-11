"""
backtest.py
-----------
Did the NAV-derived forward signals actually rank funds that went on to do
better? For a category this:

  1. takes a grid of past "as-of" dates (every BACKTEST_STEP_MONTHS),
  2. truncates every fund's NAV history to that date (no look-ahead),
  3. computes each signal as it would have looked then,
  4. measures the fund's realised annualized return over the NEXT 1 and 3
     years, and
  5. computes the rank information coefficient (Spearman correlation between
     signal "goodness" and the later return, across funds) at each date.

Backward-looking metrics (3y/5y CAGR, Sortino, alpha ...) are tested the same
way as a yardstick: a forward signal that doesn't beat plain past performance
at predicting the future hasn't earned a weight.

A signal is called "supported" only if its mean IC >= BACKTEST_MIN_MEAN_IC
and the IC was positive on >= BACKTEST_MIN_POSITIVE_SHARE of dates.

HONEST LIMITS -- read before trusting any weight:
  * Overlapping horizons: as-of dates 6 months apart with a 3-year horizon
    share most of their outcome window, so the observations are NOT
    independent. "Supported" is indicative, not statistically conclusive.
  * Few dates: you need (risk window + rolling window + horizon) years of
    history, so a 10-year-old category yields only a handful of dates.
  * Survivorship bias: only funds alive today are tested; funds that were
    closed or merged away (typically the weak ones) are absent, which
    flatters every signal that rewards past strength.
  * The CSV signals (expense ratio, AUM, tenure) can't be back-tested here
    because there is no dated history of them. Expense ratio is justified by
    arithmetic (it is deducted from returns), not by this test.

Usage:
    python backtest.py "mid cap"
    python backtest.py "small cap" --horizon 1 3 --step-months 3 --window 3
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import benchmark
import config
import forward_signals
import fund_universe
import shortlist
from fetch_nav_data import fetch_many
from logutil import get_logger, setup_logging
from metrics import (_nav_on_or_before, calculate_benchmark_stats,
                     compute_all_metrics, years_of_history)

log = get_logger(__name__)

# Past-performance yardsticks (all "higher is better"; max_drawdown is negative so
# a shallower drawdown is already higher).
BACKWARD_METRICS = ["cagr_3y", "cagr_5y", "sortino_ratio", "max_drawdown",
                    "alpha", "information_ratio", "rolling_beat_pct"]
TESTED_SIGNALS = forward_signals.NAV_SIGNALS


def signals_at(df: pd.DataFrame, bench_df: pd.DataFrame | None, window_years: float) -> dict:
    """Every tested quantity for one fund using ONLY data up to df's last date."""
    out = {}
    m = compute_all_metrics(
        df, config.RISK_FREE_RATE, sip_years=config.SIP_YEARS,
        sip_monthly_amount=config.SIP_MONTHLY_AMOUNT,
        rolling_window_years=config.ROLLING_WINDOW_YEARS, risk_window_years=window_years,
        nav_jump_threshold=config.NAV_JUMP_THRESHOLD, rolling_min_windows=config.ROLLING_MIN_WINDOWS,
        rolling_hurdle=config.ROLLING_HURDLE)
    out.update({k: m.get(k) for k in ("cagr_3y", "cagr_5y", "sortino_ratio", "max_drawdown")})
    out.update(forward_signals.compute_nav_signals(
        df, bench_df, config.RISK_FREE_RATE, window_years,
        rolling_window_years=config.ROLLING_WINDOW_YEARS,
        rolling_min_windows=config.ROLLING_MIN_WINDOWS,
        min_bench_coverage=config.BENCHMARK_MIN_COVERAGE))
    if bench_df is not None:
        b = calculate_benchmark_stats(df, bench_df, config.RISK_FREE_RATE, window_years,
                                      rolling_window_years=config.ROLLING_WINDOW_YEARS,
                                      min_coverage=config.BENCHMARK_MIN_COVERAGE)
        out.update({k: b.get(k) for k in ("alpha", "information_ratio", "rolling_beat_pct")})
    return out


def forward_return(df: pd.DataFrame, asof: pd.Timestamp, years: float, tol_days: int = 10) -> float | None:
    """Annualized realised return from `asof` to asof + years (None if the NAV
    history doesn't reach that far)."""
    target = asof + pd.Timedelta(days=int(years * 365.25))
    if df["date"].max() < target - pd.Timedelta(days=tol_days):
        return None
    start, end = _nav_on_or_before(df, asof), _nav_on_or_before(df, target)
    if not start or not end or start <= 0:
        return None
    return float((end / start) ** (1 / years) - 1)


def asof_grid(nav_data: dict, window_years: float, horizon_years: float, step_months: int) -> list[pd.Timestamp]:
    """Month-end as-of dates, stepping back from the latest date at which a
    `horizon_years` outcome is still observable."""
    last = max(df["date"].max() for df in nav_data.values())
    first_possible = min(df["date"].min() for df in nav_data.values())
    latest = (last - pd.Timedelta(days=int(horizon_years * 365.25))) + pd.offsets.MonthEnd(0)
    dates, d = [], latest
    # need history for the risk window plus the rolling window beneath it
    min_history = pd.Timedelta(days=int((window_years + config.ROLLING_WINDOW_YEARS) * 365.25))
    while d - min_history >= first_possible:
        dates.append(d)
        d = d - pd.DateOffset(months=step_months) + pd.offsets.MonthEnd(0)
    return sorted(dates)


def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    mask = a.notna() & b.notna()
    if mask.sum() < 3:
        return None
    ra, rb = a[mask].rank(), b[mask].rank()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(ra.corr(rb))


def run_backtest(nav_data: dict, bench_df: pd.DataFrame | None, window_years: float,
                 horizons: list[float], step_months: int, min_funds: int | None = None):
    """Returns (detail, summary) DataFrames. detail has one row per
    (asof, horizon, signal); summary aggregates per (signal, horizon)."""
    min_funds = config.BACKTEST_MIN_FUNDS if min_funds is None else min_funds
    quantities = TESTED_SIGNALS + BACKWARD_METRICS
    rows = []

    for h in horizons:
        for asof in asof_grid(nav_data, window_years, h, step_months):
            table, fwd = {}, {}
            for code, df in nav_data.items():
                trunc = df[df["date"] <= asof]
                if trunc.empty or years_of_history(trunc) < window_years + config.ROLLING_WINDOW_YEARS:
                    continue
                fr = forward_return(df, asof, h)
                if fr is None:
                    continue
                bt = None if bench_df is None else bench_df[bench_df["date"] <= asof]
                if bt is not None and bt.empty:
                    bt = None
                table[code] = signals_at(trunc, bt, window_years)
                fwd[code] = fr
            if len(fwd) < min_funds:
                log.debug(f"as-of {asof.date()} h={h}: only {len(fwd)} funds; skipped")
                continue
            sig_df = pd.DataFrame(table).T.astype(float)
            fwd_s = pd.Series(fwd)
            for q in quantities:
                if q not in sig_df.columns:
                    continue
                goodness = -sig_df[q] if q in config.FORWARD_LOWER_IS_BETTER else sig_df[q]
                ic = _spearman(goodness, fwd_s)
                if ic is not None:
                    rows.append({"asof": asof, "horizon_years": h, "signal": q, "ic": ic,
                                 "n_funds": int((goodness.notna() & fwd_s.notna()).sum())})

    detail = pd.DataFrame(rows, columns=["asof", "horizon_years", "signal", "ic", "n_funds"])
    return detail, summarize(detail, quantities, horizons)


def verdict(n_dates: int, mean_ic: float, pos_share: float) -> str:
    if n_dates < config.BACKTEST_MIN_DATES:
        return "insufficient data"
    if mean_ic >= config.BACKTEST_MIN_MEAN_IC and pos_share >= config.BACKTEST_MIN_POSITIVE_SHARE:
        return "supported"
    if mean_ic <= -config.BACKTEST_MIN_MEAN_IC and pos_share <= 1 - config.BACKTEST_MIN_POSITIVE_SHARE:
        return "inverted"
    return "not supported"


def summarize(detail: pd.DataFrame, quantities: list[str], horizons: list[float]) -> pd.DataFrame:
    rows = []
    for q in quantities:
        for h in horizons:
            sub = detail[(detail["signal"] == q) & (detail["horizon_years"] == h)]
            n = len(sub)
            mean_ic = float(sub["ic"].mean()) if n else np.nan
            pos = float((sub["ic"] > 0).mean()) if n else np.nan
            rows.append({
                "signal": q,
                "kind": "forward signal" if q in TESTED_SIGNALS else "past performance (yardstick)",
                "horizon_years": h, "n_dates": n, "avg_funds": float(sub["n_funds"].mean()) if n else np.nan,
                "mean_ic": mean_ic, "median_ic": float(sub["ic"].median()) if n else np.nan,
                "positive_share": pos,
                "verdict": verdict(n, mean_ic, pos) if n else "insufficient data",
            })
    return pd.DataFrame(rows)


def suggest_weights(summary: pd.DataFrame) -> dict:
    """FORWARD_WEIGHTS suggestion: NAV signals not supported at ANY horizon are
    zeroed; supported ones and the untestable CSV signals keep their configured
    weights. Insufficient data leaves the configured weight alone (no evidence
    either way) -- check the n_dates column."""
    suggested = dict(config.FORWARD_WEIGHTS)
    for sig in TESTED_SIGNALS:
        verdicts = set(summary.loc[summary["signal"] == sig, "verdict"])
        if verdicts and verdicts <= {"not supported", "inverted"}:
            suggested[sig] = 0.0
    return suggested


def format_summary(summary: pd.DataFrame) -> str:
    pretty = summary.copy()
    pretty["avg_funds"] = pretty["avg_funds"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "-")
    for c in ["mean_ic", "median_ic"]:
        pretty[c] = pretty[c].map(lambda v: f"{v:+.2f}" if pd.notna(v) else "-")
    pretty["positive_share"] = pretty["positive_share"].map(lambda v: f"{v:.0%}" if pd.notna(v) else "-")
    return pretty[["signal", "kind", "horizon_years", "n_dates", "avg_funds", "mean_ic",
                   "median_ic", "positive_share", "verdict"]].to_string(index=False)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Back-test the NAV-derived forward signals for a category.")
    p.add_argument("query", nargs="*", help='category (e.g. "mid cap") or a CSV with a scheme_code column')
    p.add_argument("--horizon", type=float, nargs="+", default=None, metavar="YEARS",
                   help=f"forward horizons in years (default {config.BACKTEST_HORIZONS_YEARS})")
    p.add_argument("--step-months", type=int, default=None, help=f"months between as-of dates (default {config.BACKTEST_STEP_MONTHS})")
    p.add_argument("--window", type=float, default=None, help=f"risk window in years (default {config.RISK_WINDOW_YEARS})")
    p.add_argument("--benchmark", default=None, metavar="CODE|category|none")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--log-file", default=None)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.query:
        print('Usage: python backtest.py <category|file.csv> [--horizon 1 3] [--step-months 6] [--window 5] '
              '[--benchmark CODE|category|none] [--refresh]')
        return
    shortlist.check_environment()
    setup_logging(verbose=args.verbose, quiet=args.quiet, log_file=args.log_file)

    window = args.window or config.RISK_WINDOW_YEARS
    horizons = args.horizon or config.BACKTEST_HORIZONS_YEARS
    step = args.step_months or config.BACKTEST_STEP_MONTHS
    query = " ".join(args.query)

    canonical = None
    try:
        if query.lower().endswith(".csv"):
            fund_list = shortlist.load_fund_list_from_csv(query)
        else:
            canonical, fund_list = shortlist.load_fund_list_from_category(query, force_refresh=args.refresh)
    except (ValueError, FileNotFoundError) as exc:
        log.error(str(exc))
        return
    if fund_list.empty:
        log.warning("No candidate funds found.")
        return

    log.info(f"Fetching NAV history for {len(fund_list)} funds ...")
    nav_data = fetch_many(fund_list["scheme_code"].tolist(), force_refresh=args.refresh)
    metrics_df = shortlist.build_metrics_table(fund_list, nav_data)
    eligible = shortlist.apply_data_quality_filters(metrics_df, canonical, {})
    nav_data = {c: nav_data[c] for c in eligible["scheme_code"]}
    log.info(f"{len(nav_data)} funds eligible for the back-test.")
    if len(nav_data) < config.BACKTEST_MIN_FUNDS:
        log.warning(f"Only {len(nav_data)} eligible funds (< BACKTEST_MIN_FUNDS={config.BACKTEST_MIN_FUNDS}); "
                    f"rank correlations would be meaningless.")
        return

    label, bench_df, note = benchmark.resolve_benchmark(canonical, nav_data, override=args.benchmark,
                                                        force_refresh=args.refresh)
    log.info(f"Benchmark: {label or 'none'} ({note})")

    detail, summary = run_backtest(nav_data, bench_df, window, horizons, step, min_funds=config.BACKTEST_MIN_FUNDS)
    if detail.empty:
        log.warning("No usable as-of dates: the funds don't have enough history for this window + horizon. "
                    "Try --window 3 and/or a shorter --horizon.")
        return

    summary.to_csv(config.BACKTEST_CSV, index=False)
    detail_path = config.BACKTEST_CSV.replace(".csv", "_detail.csv")
    detail.to_csv(detail_path, index=False)
    log.info(f"Back-test summary written to {config.BACKTEST_CSV} (per-date detail: {detail_path})")

    print(f"\n=== Signal back-test: {canonical or query} | risk window {window:g}y | "
          f"horizons {horizons} | every {step} months ===\n")
    print(format_summary(summary))
    print("\nIC = rank correlation between a signal (sign-adjusted so higher = better) and the fund's later "
          "annualized return.\nOverlapping horizons and survivorship bias mean this is indicative, not conclusive "
          "(see backtest.py docstring).")

    suggested = suggest_weights(summary)
    zeroed = [k for k in forward_signals.NAV_SIGNALS if suggested[k] == 0 and config.FORWARD_WEIGHTS.get(k)]
    if zeroed:
        print(f"\nSignals with no support at any tested horizon (suggest FORWARD_WEIGHTS[...] = 0.0): {', '.join(zeroed)}")
    else:
        print("\nNo NAV signal was rejected outright; keep the configured FORWARD_WEIGHTS "
              "(check n_dates before trusting a 'supported' verdict).")


if __name__ == "__main__":
    main()
