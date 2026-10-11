"""
forward_signals.py
------------------
Forward-looking TILTS. None of these predict returns reliably -- they are
soft evidence that a fund's past record is more (or less) likely to repeat:

  NAV-derived (no extra data needed, always computed):
    sharpe_stability     worst-half Sharpe over the common window: a fund
                         that was good in only one half is penalized
    rolling_p10          10th-percentile rolling-3y return (bad entry points)
    rolling_dispersion   p90 - p10 of rolling returns (lower = more predictable)
    beta_drift           std of rolling beta vs the benchmark (lower = steadier style)
    down_capture_drift   std of rolling down-capture (lower = steadier protection)

  From a CSV you maintain (fund_attributes.csv; see write_template):
    expense_ratio, aum_strain (+ aum_vs_median, aum_growth_12m, capacity_flag),
    manager_tenure_years, turnover_pct

  Category-level note (never used to rank funds): P/E percentile from
  category_valuation.csv.

The signals are combined into `forward_tilt` (weights: config.FORWARD_WEIGHTS)
using the same robust standardization as the main score (scoring.py). The
tilt only changes the ranking when enabled; see apply_forward_tilt.
"""

from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import pandas as pd

import config
import fund_universe
import scoring
from logutil import get_logger
from metrics import (_restrict_to_window, calculate_monthly_returns,
                     calculate_rolling_returns, has_window_coverage,
                     monthly_rate, window_monthly_returns)

log = get_logger(__name__)

NAV_SIGNALS = ["sharpe_stability", "rolling_p10", "rolling_dispersion",
               "beta_drift", "down_capture_drift"]
ATTRIBUTE_SIGNALS = ["expense_ratio", "aum_strain", "manager_tenure_years", "turnover_pct"]
ATTRIBUTE_EXTRA_COLS = ["aum_cr", "aum_growth_12m", "aum_vs_median", "capacity_flag"]
SIGNAL_COLS = NAV_SIGNALS + ATTRIBUTE_SIGNALS

# Columns a user fills in fund_attributes.csv
ATTR_INPUT_COLS = ["expense_ratio", "aum_cr", "aum_cr_12m_ago",
                   "manager_tenure_years", "turnover_pct", "as_of"]


# ===========================================================================
# 1. NAV-derived signals
# ===========================================================================

def calculate_sharpe_stability(df: pd.DataFrame, risk_free_rate: float,
                               window_years: float, min_months: int = 12) -> float | None:
    """Splits the common window's monthly returns into two halves, computes an
    annualized Sharpe ratio for each, and returns the LOWER of the two. High
    only if the fund was good in both halves (persistence)."""
    r = window_monthly_returns(df, window_years)
    if len(r) < 2 * min_months:
        return None
    ex = r - monthly_rate(risk_free_rate)
    half = len(ex) // 2
    sharpes = []
    for part in (ex.iloc[:half], ex.iloc[half:]):
        sd = part.std()
        if len(part) < min_months or pd.isna(sd) or sd <= 0:
            return None
        sharpes.append(float(part.mean() / sd * np.sqrt(12)))
    return min(sharpes)


def calculate_rolling_p10_dispersion(df: pd.DataFrame, rolling_window_years: float,
                                     within_years: float, min_windows: int) -> tuple[float | None, float | None]:
    """(p10, p90 - p10) of rolling returns ending inside the common window."""
    if not has_window_coverage(df, within_years):
        return None, None
    rolling = _restrict_to_window(calculate_rolling_returns(df, rolling_window_years), df, within_years)
    if len(rolling) < min_windows:
        return None, None
    p10, p90 = float(rolling.quantile(0.10)), float(rolling.quantile(0.90))
    return p10, p90 - p10


def _aligned_monthly(fund_df: pd.DataFrame, bench_df: pd.DataFrame, window_years: float,
                     min_coverage: float) -> pd.DataFrame | None:
    f = window_monthly_returns(fund_df, window_years)
    b = calculate_monthly_returns(bench_df)
    if f.empty or b.empty:
        return None
    joined = pd.concat([f.rename("f"), b.rename("b")], axis=1, join="inner").dropna()
    if len(joined) < max(24, int(round(window_years * 12 * min_coverage))):
        return None
    return joined


def _geo_mean(s: pd.Series) -> float:
    return float(np.prod(1 + s.values) ** (1 / len(s)) - 1)


def calculate_beta_drift(joined: pd.DataFrame, risk_free_rate: float, window_months: int,
                         min_points: int = 8) -> float | None:
    """Std of the rolling `window_months` regression beta of fund on benchmark."""
    if joined is None or len(joined) < window_months + min_points - 1:
        return None
    rf_m = monthly_rate(risk_free_rate)
    ex_f, ex_b = joined["f"] - rf_m, joined["b"] - rf_m
    beta = (ex_f.rolling(window_months).cov(ex_b) / ex_b.rolling(window_months).var()).replace(
        [np.inf, -np.inf], np.nan).dropna()
    if len(beta) < min_points:
        return None
    return float(beta.std())


def calculate_down_capture_drift(joined: pd.DataFrame, window_months: int,
                                 min_points: int = 8, min_down_months: int = 6) -> float | None:
    """Std of rolling `window_months` down-capture (fund vs benchmark in
    benchmark-down months)."""
    if joined is None or len(joined) < window_months + min_points - 1:
        return None
    values = []
    for end in range(window_months, len(joined) + 1):
        seg = joined.iloc[end - window_months:end]
        down = seg[seg["b"] < 0]
        if len(down) < min_down_months:
            continue
        gb = _geo_mean(down["b"])
        if abs(gb) < 1e-9:
            continue
        values.append(_geo_mean(down["f"]) / gb)
    if len(values) < min_points:
        return None
    return float(np.std(values, ddof=1))


def compute_nav_signals(fund_df: pd.DataFrame, bench_df: pd.DataFrame | None,
                        risk_free_rate: float, risk_window_years: float,
                        rolling_window_years: float = 3.0, rolling_min_windows: int = 12,
                        min_bench_coverage: float = 0.9) -> dict:
    """All NAV-derived forward signals for one fund (None where the history
    or benchmark isn't sufficient). Pure function: also used by backtest.py
    on NAV truncated to a past date."""
    out = {k: None for k in NAV_SIGNALS}
    try:
        out["sharpe_stability"] = calculate_sharpe_stability(
            fund_df, risk_free_rate, risk_window_years, config.SHARPE_STABILITY_MIN_MONTHS)
        out["rolling_p10"], out["rolling_dispersion"] = calculate_rolling_p10_dispersion(
            fund_df, rolling_window_years, risk_window_years, rolling_min_windows)
        if bench_df is not None:
            joined = _aligned_monthly(fund_df, bench_df, risk_window_years, min_bench_coverage)
            out["beta_drift"] = calculate_beta_drift(joined, risk_free_rate, config.BETA_DRIFT_WINDOW_MONTHS)
            out["down_capture_drift"] = calculate_down_capture_drift(joined, config.CAPTURE_DRIFT_WINDOW_MONTHS)
    except Exception as exc:  # a malformed series must never abort a category run
        log.debug(f"nav signals failed: {exc}")
    return out


def attach_nav_signals(df: pd.DataFrame, nav_data: dict, bench_df: pd.DataFrame | None) -> pd.DataFrame:
    """Adds the NAV-derived signal columns to a metrics table."""
    rows = [compute_nav_signals(
        nav_data[code], bench_df, config.RISK_FREE_RATE, config.RISK_WINDOW_YEARS,
        rolling_window_years=config.ROLLING_WINDOW_YEARS,
        rolling_min_windows=config.ROLLING_MIN_WINDOWS,
        min_bench_coverage=config.BENCHMARK_MIN_COVERAGE) for code in df["scheme_code"]]
    sig = pd.DataFrame(rows, columns=NAV_SIGNALS).astype(float)
    return pd.concat([df.reset_index(drop=True), sig], axis=1)


# ===========================================================================
# 2. fund_attributes.csv (manual data) -- loader, validation, template
# ===========================================================================

def _today(today) -> pd.Timestamp:
    return pd.Timestamp(today).normalize() if today is not None else pd.Timestamp(datetime.now()).normalize()


def load_fund_attributes(path: str | None = None, today=None) -> pd.DataFrame | None:
    """Reads and validates fund_attributes.csv. Returns None if the file does
    not exist. Invalid entries (e.g. expense ratio 12 instead of 1.2) become
    missing with a warning rather than silently skewing scores."""
    path = path or config.FUND_ATTRIBUTES_CSV
    if not os.path.exists(path):
        return None
    raw = pd.read_csv(path, dtype={"scheme_code": str})
    if "scheme_code" not in raw.columns:
        raise ValueError(f"{path} must contain a 'scheme_code' column "
                         f"(generate one with: python shortlist.py \"<category>\" --make-template).")
    df = raw.copy()
    df["scheme_code"] = df["scheme_code"].astype(str).str.strip()
    df = df[df["scheme_code"].ne("") & df["scheme_code"].ne("nan")]

    if df["scheme_code"].duplicated().any():
        dups = sorted(df.loc[df["scheme_code"].duplicated(keep=False), "scheme_code"].unique())
        log.warning(f"{path}: duplicate scheme_code row(s) {dups}; keeping the last of each.")
        df = df.drop_duplicates("scheme_code", keep="last")

    for col in ATTR_INPUT_COLS:
        if col not in df.columns:
            df[col] = np.nan
    for col in ["expense_ratio", "aum_cr", "aum_cr_12m_ago", "manager_tenure_years", "turnover_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["as_of"] = pd.to_datetime(df["as_of"], errors="coerce")

    rules = {
        "expense_ratio": lambda s: (s > 0) & (s <= config.EXPENSE_RATIO_MAX_PCT),
        "aum_cr": lambda s: s > 0,
        "aum_cr_12m_ago": lambda s: s > 0,
        "manager_tenure_years": lambda s: (s >= 0) & (s <= 60),
        "turnover_pct": lambda s: (s >= 0) & (s <= 1000),
    }
    for col, ok in rules.items():
        bad = df[col].notna() & ~ok(df[col])
        if bad.any():
            codes = df.loc[bad, "scheme_code"].tolist()
            log.warning(f"{path}: ignoring out-of-range '{col}' for {codes[:8]}{'...' if len(codes) > 8 else ''} "
                        f"(expense_ratio is in PERCENT, e.g. 0.72 means 0.72%).")
            df.loc[bad, col] = np.nan

    return df[["scheme_code"] + ATTR_INPUT_COLS].reset_index(drop=True)


def check_staleness(attrs: pd.DataFrame, today=None) -> list[str]:
    """Warns about rows whose `as_of` is older than FORWARD_DATA_MAX_AGE_DAYS
    (or missing). If config.FORWARD_IGNORE_STALE, blanks the stale rows' values
    in place. Returns the stale scheme codes."""
    now = _today(today)
    age = (now - attrs["as_of"]).dt.days
    stale_mask = age > config.FORWARD_DATA_MAX_AGE_DAYS
    undated = attrs["as_of"].isna() & attrs[["expense_ratio", "aum_cr", "manager_tenure_years"]].notna().any(axis=1)

    stale_codes = attrs.loc[stale_mask, "scheme_code"].tolist()
    if stale_codes:
        oldest = int(age[stale_mask].max())
        log.warning(f"{len(stale_codes)} row(s) in {config.FUND_ATTRIBUTES_CSV} are older than "
                    f"{config.FORWARD_DATA_MAX_AGE_DAYS} days (oldest {oldest}d): "
                    f"{stale_codes[:8]}{'...' if len(stale_codes) > 8 else ''}. "
                    + ("Treating them as missing." if config.FORWARD_IGNORE_STALE else "Update them or expect stale tilts."))
        if config.FORWARD_IGNORE_STALE:
            attrs.loc[stale_mask, ["expense_ratio", "aum_cr", "aum_cr_12m_ago",
                                   "manager_tenure_years", "turnover_pct"]] = np.nan
    if undated.any():
        log.warning(f"{int(undated.sum())} row(s) in {config.FUND_ATTRIBUTES_CSV} have data but no valid 'as_of' date; "
                    f"their freshness can't be checked.")
    return stale_codes


def merge_attributes(df: pd.DataFrame, attrs: pd.DataFrame | None, canonical: str | None) -> pd.DataFrame:
    """Left-merges attributes onto the metrics table and derives aum_growth_12m,
    aum_vs_median, aum_strain and capacity_flag. All signal columns exist
    afterwards (NaN when there is no data)."""
    out = df.copy()
    for col in ["expense_ratio", "aum_cr", "aum_cr_12m_ago", "manager_tenure_years", "turnover_pct"]:
        out[col] = np.nan
    if attrs is not None and not attrs.empty:
        a = attrs.set_index("scheme_code")
        for col in ["expense_ratio", "aum_cr", "aum_cr_12m_ago", "manager_tenure_years", "turnover_pct"]:
            out[col] = out["scheme_code"].map(a[col])

    out["aum_growth_12m"] = out["aum_cr"] / out["aum_cr_12m_ago"] - 1
    median_aum = out["aum_cr"].median()
    out["aum_vs_median"] = out["aum_cr"] / median_aum if pd.notna(median_aum) and median_aum > 0 else np.nan
    growth = out["aum_growth_12m"].clip(lower=0).fillna(0.0)
    out["aum_strain"] = out["aum_vs_median"] * (1 + growth)
    sensitive = canonical in config.CAPACITY_SENSITIVE_CATEGORIES if canonical else False
    out["capacity_flag"] = bool(sensitive) & (out["aum_vs_median"] >= config.CAPACITY_RATIO_FLAG)
    out["capacity_flag"] = out["capacity_flag"].fillna(False).astype(bool)
    return out.drop(columns=["aum_cr_12m_ago"])


def attach_attribute_signals(df: pd.DataFrame, canonical: str | None, path: str | None = None,
                             today=None) -> pd.DataFrame:
    """Loads fund_attributes.csv (if present), checks freshness and merges it in."""
    path = path or config.FUND_ATTRIBUTES_CSV
    attrs = load_fund_attributes(path, today=today)
    if attrs is None:
        log.info(f"No {path} found; expense-ratio / AUM / tenure signals unavailable "
                 f"(create one with: python shortlist.py \"<category>\" --make-template).")
    else:
        check_staleness(attrs, today=today)
        matched = int(df["scheme_code"].isin(attrs["scheme_code"]).sum())
        log.info(f"Fund attributes: {matched} of {len(df)} eligible funds found in {path}.")
    return merge_attributes(df, attrs, canonical)


def write_template(path: str, fund_list: pd.DataFrame) -> tuple[int, int]:
    """Writes (or extends) the attributes CSV with one row per candidate fund.
    NEVER overwrites existing values: rows already in the file are kept
    byte-for-byte (read as text), and only missing scheme codes are appended.
    Returns (rows_kept, rows_added)."""
    names = {str(r.scheme_code): getattr(r, "scheme_name_hint", "") or ""
             for r in fund_list.itertuples(index=False)}
    cols = ["scheme_code", "scheme_name"] + ATTR_INPUT_COLS

    if os.path.exists(path):
        existing = pd.read_csv(path, dtype=str, keep_default_na=False)
        if "scheme_code" not in existing.columns:
            raise ValueError(f"{path} exists but has no 'scheme_code' column; refusing to overwrite it.")
        for c in cols:
            if c not in existing.columns:
                existing[c] = ""
        existing["scheme_code"] = existing["scheme_code"].str.strip()
        have = set(existing["scheme_code"])
        blank_name = existing["scheme_code"].map(lambda c: c in names) & existing["scheme_name"].eq("")
        existing.loc[blank_name, "scheme_name"] = existing.loc[blank_name, "scheme_code"].map(names)
    else:
        existing = pd.DataFrame(columns=cols)
        have = set()

    new_codes = [c for c in names if c not in have]
    added = pd.DataFrame({"scheme_code": new_codes, "scheme_name": [names[c] for c in new_codes]})
    for c in ATTR_INPUT_COLS:
        added[c] = ""
    extra = [c for c in existing.columns if c not in cols]      # preserve any user-added columns
    merged = pd.concat([existing, added], ignore_index=True)[cols + extra].fillna("")
    merged.to_csv(path, index=False)
    return len(existing), len(added)


# ===========================================================================
# 3. Category valuation note (category-level only)
# ===========================================================================

def category_valuation_note(canonical: str | None, path: str | None = None, today=None) -> dict | None:
    """Reads category_valuation.csv (category, pe_percentile, as_of) and returns
    {"pe_percentile", "band", "as_of", "text"} for this category, or None. This
    is context for how much to allocate to the category -- it is the same for
    every fund in it, so it is never used to rank funds against each other."""
    path = path or config.CATEGORY_VALUATION_CSV
    if not canonical or not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if not {"category", "pe_percentile"}.issubset(df.columns):
        log.warning(f"{path} needs columns: category, pe_percentile[, as_of]; ignoring it.")
        return None
    for row in df.itertuples(index=False):
        try:
            if fund_universe.resolve_category(str(row.category)) != canonical:
                continue
        except ValueError:
            continue
        pe = pd.to_numeric(row.pe_percentile, errors="coerce")
        if pd.isna(pe) or not 0 <= pe <= 100:
            log.warning(f"{path}: invalid pe_percentile for '{row.category}'; ignoring.")
            return None
        band = ("rich" if pe >= config.PE_RICH_PERCENTILE
                else "cheap" if pe <= config.PE_CHEAP_PERCENTILE else "neutral")
        as_of = pd.to_datetime(getattr(row, "as_of", None), errors="coerce")
        age = (_today(today) - as_of).days if pd.notna(as_of) else None
        stale = age is not None and age > config.FORWARD_DATA_MAX_AGE_DAYS
        text = (f"{canonical} valuation: P/E at the {pe:.0f}th percentile of its own history ({band})"
                + (f"; data is {age} days old" if stale else ""))
        return {"pe_percentile": float(pe), "band": band,
                "as_of": None if pd.isna(as_of) else as_of.strftime("%Y-%m-%d"), "text": text}
    return None


# ===========================================================================
# 4. Forward tilt and re-ranking
# ===========================================================================

def active_forward_weights(universe: pd.DataFrame) -> dict:
    """Weighted signals that have enough coverage in the eligible category."""
    active = {}
    n = len(universe)
    for sig, w in config.FORWARD_WEIGHTS.items():
        if not w or sig not in universe.columns:
            continue
        have = int(universe[sig].notna().sum())
        if have == 0:
            log.info(f"  (forward tilt: '{sig}' has no data -- ignored)")
            continue
        if have < max(3, config.FORWARD_MIN_COVERAGE * n):
            log.warning(f"forward tilt: '{sig}' has data for only {have} of {n} funds "
                        f"(< {config.FORWARD_MIN_COVERAGE:.0%} coverage); ignoring it.")
            continue
        active[sig] = w
    return active


def compute_forward_tilt(df: pd.DataFrame, universe: pd.DataFrame) -> tuple[pd.Series, dict]:
    """Weighted average of standardized signals (0 = category average).
    Returns (tilt Series, weights actually used). All-NaN if no usable signal."""
    weights = active_forward_weights(universe)
    if not weights:
        return pd.Series(np.nan, index=df.index), {}
    tilt = scoring.weighted_score(df, universe, weights, config.FORWARD_LOWER_IS_BETTER,
                                  scoring.should_use_percentile(len(universe)))
    return tilt, weights


def effective_blend(requested: float | None = None) -> float:
    b = config.FORWARD_BLEND if requested is None else requested
    if b > config.FORWARD_MAX_BLEND:
        log.warning(f"FORWARD_BLEND={b:.2f} exceeds FORWARD_MAX_BLEND={config.FORWARD_MAX_BLEND:.2f}; "
                    f"using {config.FORWARD_MAX_BLEND:.2f}.")
        return config.FORWARD_MAX_BLEND
    return max(0.0, b)


def apply_forward_tilt(ranked: pd.DataFrame, universe: pd.DataFrame, enabled: bool | None = None,
                       blend: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Adds `forward_tilt` to the ranked table. When enabled, also adds
    combined_score = (1-blend)*composite_score + blend*forward_tilt, re-ranks
    by it, and records rank_backward and rank_change (positive = moved up).
    When disabled, ranking and `rank` are untouched.
    Returns (table, info) where info describes what was used."""
    enabled = config.FORWARD_TILT_ENABLED if enabled is None else enabled
    out = ranked.copy()
    tilt, weights = compute_forward_tilt(out, universe)
    out["forward_tilt"] = tilt
    info = {"enabled": bool(enabled), "weights": weights, "blend": None, "reranked": False}

    if not enabled:
        return out, info
    if not weights:
        log.warning("forward tilt requested but no signal has usable data; ranking unchanged.")
        return out, info

    b = effective_blend(blend)
    info["blend"] = b
    out["rank_backward"] = out["rank"]
    out["combined_score"] = (1 - b) * out["composite_score"] + b * out["forward_tilt"].fillna(0.0)
    out = out.sort_values("combined_score", ascending=False, kind="mergesort").reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    out["rank_change"] = out["rank_backward"] - out["rank"]
    info["reranked"] = True
    return out, info
