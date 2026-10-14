"""
benchmark.py
------------
Benchmark-relative metrics (spec parameters 3 and 4):

    * benchmark_excess_return        fund CAGR minus benchmark CAGR over the
                                     same matched dates (config.BENCHMARK_EXCESS_YEARS)
    * rolling_beat_benchmark_pct     share of rolling-return windows in which the
                                     fund's trailing CAGR beat the benchmark's
                                     (config.ROLLING_WINDOW_YEARS)

Benchmark data source (first match wins, per category):
    1. A local CSV you drop in config.BENCHMARK_DIR, named after the category
       (e.g. data/benchmarks/small_cap.csv) with columns `date` and `nav`
       (or `tri` / `close`). Use this for real NSE Total Return Index history.
    2. A pinned scheme code in config.BENCHMARKS[category]["scheme_code"].
    3. Auto-discovery: the Direct-Growth index fund tracking the benchmark index
       with the LONGEST NAV history, found in the AMFI scheme master.

Option 3 is only a PROXY for the TRI: an index fund's NAV runs slightly below
the true TRI (expense ratio + tracking error), so excess return is flattered
by roughly that gap. Every output row records which proxy was used.

Nothing is inferred: if the benchmark is missing, stale, or too short, the
benchmark metrics are None and the scorer treats them as missing.
"""

import os
from datetime import timedelta

import pandas as pd

import config

MIN_ROLLING_WINDOWS = 12  # same floor as metrics.rolling_return_stats

# Order matters: "large & mid cap" must be tested before "large cap"/"mid cap".
_CATEGORY_PATTERNS = [
    ("large & mid cap", ["large & mid cap", "large and mid cap", "large & midcap", "large midcap"]),
    ("small cap", ["small cap", "smallcap"]),
    ("mid cap", ["mid cap", "midcap"]),
    ("large cap", ["large cap", "largecap", "bluechip", "blue chip"]),
    ("multi cap", ["multi cap", "multicap"]),
    ("flexi cap", ["flexi cap", "flexicap"]),
    ("elss", ["elss", "tax saver", "tax saving"]),
    ("focused", ["focused"]),
    ("value", ["value"]),
    ("contra", ["contra"]),
    ("dividend yield", ["dividend yield"]),
    ("sectoral", ["sectoral", "thematic"]),
]


def category_key(scheme_category: str | None, fallback: str | None = None) -> str | None:
    """Maps an AMFI category string (e.g. 'Equity Scheme - Mid Cap Fund') to
    a key of config.BENCHMARKS. Falls back to the category the user asked for
    on the command line when the fund's own category is blank/unrecognised."""
    text = (scheme_category or "").lower()
    for key, patterns in _CATEGORY_PATTERNS:
        if any(p in text for p in patterns):
            return key
    return fallback


def _squash(text: str) -> str:
    return "".join(text.lower().split())


def _clean_nav_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["date", "nav"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    return df.dropna().sort_values("date").reset_index(drop=True)


def _history_days(df: pd.DataFrame) -> int:
    return 0 if df.empty else (df["date"].max() - df["date"].min()).days


class BenchmarkProvider:
    """Resolves and caches one benchmark series per category for a run."""

    def __init__(self, force_refresh: bool = False):
        self.force_refresh = force_refresh
        self._cache = {}
        self._schemes = None

    # -- public -----------------------------------------------------------
    def get(self, key: str | None):
        if key is None:
            return None
        if key not in self._cache:
            try:
                self._cache[key] = self._load(key)
            except Exception as exc:  # never let a benchmark failure abort the run
                print(f"  WARNING: could not load benchmark for '{key}': {exc}")
                self._cache[key] = None
        return self._cache[key]

    def describe(self) -> list[str]:
        lines = []
        for key, b in self._cache.items():
            if b is None:
                lines.append(f"  {key}: NO benchmark available -> benchmark metrics left missing")
            else:
                years = _history_days(b["df"]) / 365.25
                lines.append(f"  {key}: {b['label']} via {b['source']} "
                             f"[{b['proxy_name']}] ({years:.1f}y history)")
        return lines

    # -- loading ----------------------------------------------------------
    def _load(self, key: str):
        spec = config.BENCHMARKS.get(key)
        if not spec:
            return None  # e.g. sectoral: no single fair benchmark

        csv_path = os.path.join(config.BENCHMARK_DIR, key.replace(" & ", " and ").replace(" ", "_") + ".csv")
        if os.path.exists(csv_path):
            return self._from_csv(spec, csv_path)

        from fetch_nav_data import get_nav_history  # lazy: keeps this module importable alone

        code = spec.get("scheme_code")
        if code:
            df = _clean_nav_frame(get_nav_history(str(code), force_refresh=self.force_refresh))
            return {"label": spec["label"], "df": df, "source": "pinned index-fund proxy",
                    "proxy_name": str(code), "proxy_code": str(code)}

        return self._discover(spec, get_nav_history)

    def _from_csv(self, spec, path):
        raw = pd.read_csv(path)
        raw.columns = [c.strip().lower() for c in raw.columns]
        value_col = next((c for c in ("nav", "tri", "close", "value") if c in raw.columns), None)
        if "date" not in raw.columns or value_col is None:
            raise ValueError(f"{path} needs a 'date' column and one of nav/tri/close/value")
        raw = raw.rename(columns={value_col: "nav"})
        raw["date"] = pd.to_datetime(raw["date"], dayfirst=True, format="mixed")
        return {"label": spec["label"], "df": _clean_nav_frame(raw), "source": "local TRI csv",
                "proxy_name": os.path.basename(path), "proxy_code": ""}

    def _discover(self, spec, get_nav_history):
        import fund_universe

        if self._schemes is None:
            self._schemes = fund_universe.download_scheme_master(force_refresh=self.force_refresh)

        keywords = [_squash(k) for k in spec["keywords"]]
        excluded = [_squash(w) for w in config.BENCHMARK_EXCLUDE_WORDS + spec.get("exclude", [])]

        matches = []
        for s in self._schemes:
            name = s.get("schemeName", "") or ""
            n = _squash(name)
            if "direct" not in n or "growth" not in n:
                continue
            if not any(k in n for k in keywords):
                continue
            if any(x in n for x in excluded):
                continue
            matches.append((int(s["schemeCode"]), name))

        if not matches:
            print(f"  WARNING: no index-fund proxy found for {spec['label']}; "
                  f"drop a TRI csv into {config.BENCHMARK_DIR}/ to enable it.")
            return None

        # Older funds have lower AMFI codes; check the oldest few for longest history.
        matches.sort()
        best = None
        for code, name in matches[: config.BENCHMARK_MAX_CANDIDATES]:
            try:
                df = _clean_nav_frame(get_nav_history(str(code), force_refresh=self.force_refresh))
            except Exception as exc:
                print(f"  WARNING: proxy {code} unavailable: {exc}")
                continue
            if best is None or _history_days(df) > _history_days(best["df"]):
                best = {"label": spec["label"], "df": df, "source": "index-fund proxy",
                        "proxy_name": name, "proxy_code": str(code)}
        return best


# ---------------------------------------------------------------------------
# Pure calculations (no network, no config lookups except noted)
# ---------------------------------------------------------------------------

def _nav_on_or_before(df: pd.DataFrame, target) -> float | None:
    subset = df[df["date"] <= target]
    return None if subset.empty else float(subset.iloc[-1]["nav"])


def matched_cagrs(fund_df: pd.DataFrame, bench_df: pd.DataFrame, years: float,
                  max_staleness_days: int = 10):
    """(fund_cagr, bench_cagr) over the SAME start/end dates, or (None, None)
    if either series is too short or the benchmark lags the fund by more than
    max_staleness_days."""
    if fund_df.empty or bench_df.empty:
        return None, None
    fund_end, bench_end = fund_df["date"].max(), bench_df["date"].max()
    if (fund_end - bench_end).days > max_staleness_days:
        return None, None

    end = min(fund_end, bench_end)
    start = end - timedelta(days=int(years * 365.25))
    for df in (fund_df, bench_df):
        if df["date"].min() > start + timedelta(days=30):
            return None, None

    vals = [_nav_on_or_before(d, t) for d in (fund_df, bench_df) for t in (end, start)]
    if any(v is None or v <= 0 for v in vals):
        return None, None
    f_end, f_start, b_end, b_start = vals
    return (f_end / f_start) ** (1 / years) - 1, (b_end / b_start) ** (1 / years) - 1


def _month_end_nav(df: pd.DataFrame) -> pd.Series:
    return df.set_index("date")["nav"].sort_index().resample("ME").last().dropna()


def _rolling_cagr(monthly: pd.Series, window_years: float) -> pd.Series:
    """Trailing CAGR at every month-end (same rule as metrics.calculate_rolling_returns)."""
    window = pd.Timedelta(days=int(window_years * 365.25))
    idx = monthly.index
    out = {}
    for end_date, end_nav in monthly.items():
        start_date = end_date - window
        pos = idx.searchsorted(start_date, side="right") - 1
        if pos < 0 or start_date - idx[pos] > pd.Timedelta(days=45):
            continue
        start_nav = monthly.iloc[pos]
        if start_nav <= 0:
            continue
        out[end_date] = (end_nav / start_nav) ** (1 / window_years) - 1
    return pd.Series(out, dtype=float)


def rolling_beat_pct(fund_df: pd.DataFrame, bench_df: pd.DataFrame, window_years: float):
    """(share of matched windows where fund beat benchmark, number of windows)."""
    f = _rolling_cagr(_month_end_nav(fund_df), window_years)
    b = _rolling_cagr(_month_end_nav(bench_df), window_years)
    common = f.index.intersection(b.index)
    if len(common) < MIN_ROLLING_WINDOWS:
        return None, len(common)
    return float((f[common] > b[common]).mean()), len(common)


def compute_benchmark_metrics(fund_df: pd.DataFrame, bench_df: pd.DataFrame,
                              excess_years: float, rolling_window_years: float,
                              max_staleness_days: int = 10) -> dict:
    fund_cagr, bench_cagr = matched_cagrs(fund_df, bench_df, excess_years, max_staleness_days)
    excess = None if fund_cagr is None else fund_cagr - bench_cagr
    beat, n_windows = rolling_beat_pct(fund_df, bench_df, rolling_window_years)
    return {
        "benchmark_cagr": bench_cagr,
        "benchmark_excess_return": excess,
        "rolling_beat_benchmark_pct": beat,
        "benchmark_windows": n_windows,
    }


EMPTY_BENCHMARK_METRICS = {
    "benchmark_name": "", "benchmark_proxy": "", "benchmark_cagr": None,
    "benchmark_excess_return": None, "rolling_beat_benchmark_pct": None,
    "benchmark_windows": 0,
}


def metrics_for_fund(fund_df: pd.DataFrame, provider: BenchmarkProvider | None,
                     scheme_category: str | None, default_key: str | None) -> dict:
    """Everything shortlist.py needs for one fund. Always returns the full
    key set so DataFrame columns are stable."""
    out = dict(EMPTY_BENCHMARK_METRICS)
    if provider is None:
        return out
    bench = provider.get(category_key(scheme_category, default_key))
    if bench is None:
        return out
    out.update(compute_benchmark_metrics(
        fund_df, bench["df"], config.BENCHMARK_EXCESS_YEARS, config.ROLLING_WINDOW_YEARS,
        config.BENCHMARK_MAX_STALENESS_DAYS))
    out["benchmark_name"] = bench["label"]
    out["benchmark_proxy"] = bench["proxy_name"]
    return out
