"""
benchmark.py
------------
Builds the benchmark NAV series that benchmark-relative metrics (alpha, beta,
information ratio, capture ratios, rolling beat %) are measured against.

Two kinds of benchmark are supported, both returned as a DataFrame with
columns (date, nav) so the same metric code handles either:

  1. An INDEX PROXY: a Direct+Growth index fund / ETF from the AMFI scheme
     master that tracks the category's reference index (Nifty 50, Midcap 150,
     Smallcap 250, Nifty 500 ...). Pin one with config.BENCHMARK_SCHEME_CODES
     or --benchmark <scheme_code>, or let `auto` discover one by name using
     config.BENCHMARK_NAME_HINTS.
  2. The CATEGORY AVERAGE: equal-weight average monthly return of every
     eligible fund in the scanned category. Needs no external data, so it is
     the fallback when no index proxy with enough history is found. (It
     includes the fund under test, a small self-reference that shrinks as the
     category gets bigger.)

Index funds tracking newer indices (e.g. Midcap 150, Smallcap 250) may not
have a full 5 years of history yet; such a proxy is rejected in `auto` mode
and the category average is used instead, with a printed note.
"""

from __future__ import annotations

import pandas as pd

import config
import fund_universe
from logutil import get_logger
from fetch_nav_data import get_nav_history, get_scheme_meta
from metrics import calculate_monthly_returns, years_of_history

log = get_logger(__name__)


def build_category_average(nav_data: dict, min_funds: int | None = None) -> pd.DataFrame | None:
    """Equal-weight category-average NAV index built from monthly returns of
    all funds in `nav_data` ({code: df}). Months with fewer than `min_funds`
    contributing funds are dropped."""
    if not nav_data:
        return None
    if min_funds is None:
        min_funds = min(config.CATEGORY_AVG_MIN_FUNDS, max(2, len(nav_data) // 2))

    monthly = {code: calculate_monthly_returns(df) for code, df in nav_data.items()}
    mat = pd.concat(monthly, axis=1)
    counts = mat.notna().sum(axis=1)
    avg = mat.mean(axis=1)[counts >= min_funds].dropna()
    if len(avg) < 12:
        return None

    nav = 100.0 * (1 + avg).cumprod()
    # Prepend a base row (value 100) one month before the first return so
    # that the first month's return survives a later pct_change().
    base_date = nav.index[0] - pd.offsets.MonthEnd(1)
    dates = [base_date] + list(nav.index)
    values = [100.0] + list(nav.values)
    return pd.DataFrame({"date": pd.to_datetime(dates), "nav": values})


def _name_ok_for_benchmark(name: str) -> bool:
    n = fund_universe._normalize(name)
    if "direct" not in n or "growth" not in n:
        return False
    return not any(bad in n for bad in config.BENCHMARK_NAME_EXCLUDE)


def find_index_proxy(canonical: str, schemes: list, force_refresh: bool = False,
                     min_years: float = 0.0):
    """Name-based discovery of an index proxy. Walks the keyword-sets in
    config.BENCHMARK_NAME_HINTS[canonical] in priority order; for each set
    with matches, downloads up to BENCHMARK_MAX_CANDIDATES of them and takes
    the one with the longest NAV history. The first set whose best candidate
    has at least `min_years` of history wins; if none does, the overall
    longest-history candidate is returned (the caller then decides whether it
    is usable). Returns (code, name, df), or None if nothing matches."""
    overall_best = None
    for keywords in config.BENCHMARK_NAME_HINTS.get(canonical, []):
        matches = []
        for s in schemes:
            name = s.get("schemeName", "") or ""
            n = fund_universe._normalize(name)
            if all(fund_universe._normalize(k) in n for k in keywords) and _name_ok_for_benchmark(name):
                matches.append((str(s.get("schemeCode")), name))
        if not matches:
            continue

        best = None
        for code, name in matches[:config.BENCHMARK_MAX_CANDIDATES]:
            try:
                df = get_nav_history(code, force_refresh=force_refresh)
            except Exception as exc:
                log.debug(f"  (benchmark candidate {code} unavailable: {exc})")
                continue
            if best is None or years_of_history(df) > years_of_history(best[2]):
                best = (code, name, df)
        if best is None:
            continue
        if years_of_history(best[2]) >= min_years:
            return best
        if overall_best is None or years_of_history(best[2]) > years_of_history(overall_best[2]):
            overall_best = best
    return overall_best


def resolve_benchmark(canonical: str | None, nav_data: dict, mode: str | None = None,
                      override: str | None = None, force_refresh: bool = False):
    """Chooses and builds the benchmark for this run.

    Returns (label, benchmark_df, note) -- or (None, None, note) when
    benchmark-relative metrics are disabled or unavailable. `override` is a
    scheme code, "category" (category average) or "none"."""
    mode = (mode or config.BENCHMARK_MODE).lower()
    min_years = config.RISK_WINDOW_YEARS * config.BENCHMARK_MIN_COVERAGE

    if override:
        o = override.strip().lower()
        if o == "none":
            mode = "none"
        elif o in ("category", "category_average", "avg"):
            mode = "category_average"
        else:
            code = override.strip()
            df = get_nav_history(code, force_refresh=force_refresh)
            name = get_scheme_meta(code).get("scheme_name") or code
            if years_of_history(df) < min_years:
                log.warning(f"pinned benchmark {code} has only {years_of_history(df):.1f}y of history "
                      f"(< {min_years:.1f}y needed); benchmark metrics will be blank for most funds.")
            return f"{name} [{code}]", df, "user-specified benchmark"

    if mode == "none":
        return None, None, "benchmark-relative metrics disabled"

    if mode in ("auto", "index") and canonical:
        pinned = config.BENCHMARK_SCHEME_CODES.get(canonical)
        found = None
        try:
            if pinned:
                df = get_nav_history(str(pinned), force_refresh=force_refresh)
                found = (str(pinned), get_scheme_meta(str(pinned)).get("scheme_name") or str(pinned), df)
            else:
                schemes = fund_universe.download_scheme_master(force_refresh=force_refresh)
                found = find_index_proxy(canonical, schemes, force_refresh=force_refresh,
                                         min_years=min_years)
        except Exception as exc:
            log.debug(f"  (index benchmark lookup failed: {exc})")

        if found and years_of_history(found[2]) >= min_years:
            code, name, df = found
            return f"{name} [{code}]", df, "index proxy"
        reason = ("none found" if not found else
                  f"'{found[1]}' has only {years_of_history(found[2]):.1f}y history (< {min_years:.1f}y)")
        if mode == "index":
            log.warning(f"no usable index benchmark ({reason}); benchmark-relative metrics will be blank.")
            return None, None, f"no usable index benchmark ({reason})"
        log.info(f"Index benchmark unavailable ({reason}); falling back to the category average.")

    avg = build_category_average(nav_data)
    if avg is None:
        log.warning("could not build a category-average benchmark (too few funds / too little data); "
              "benchmark-relative metrics will be blank.")
        return None, None, "category average unavailable"
    return f"Category average (equal-weight, {len(nav_data)} funds)", avg, "category average"
