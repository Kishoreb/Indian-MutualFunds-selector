"""
data_checks.py
--------------
Data-quality checks on the per-fund metrics table (spec section 7): duplicates, stale NAVs,
inconsistent values and non-comparable categories. Checks only FLAG; deciding what to do
(e.g. EXCLUDE_STALE_FUNDS) is up to the caller. Nothing is repaired or guessed.

Flags added to each fund (data_flags column, '; '-separated):
    DUPLICATE_CODE        same scheme_code appears more than once (extra rows are dropped)
    DUPLICATE_NAME        another fund has the same scheme name
    STALE_NAV(n d)        last NAV is n days older than the newest NAV in the group
    INCONSISTENT: ...     e.g. 5y CAGR with under 5y of history, drawdown outside -100%..0%
    CATEGORY_MISMATCH     the fund's AMFI category differs from the group's most common one
    NO_NAV_DATE           no usable NAV date
"""

import pandas as pd


def _norm_category(text) -> str:
    """AMFI/mfapi spell the same category 'Equity Scheme - Small Cap Fund' and 'Equity Schemes - Small Cap Fund'
    (plural, spacing); compare them in one normalised form so that is not reported as a mismatch."""
    t = str(text or "").lower().replace("schemes", "scheme")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in t).split())


def drop_duplicate_codes(df: pd.DataFrame):
    dup = df["scheme_code"].astype(str).duplicated(keep="first")
    return df[~dup].reset_index(drop=True), int(dup.sum())


def check_table(df: pd.DataFrame, stale_days: int = 10, reference_date=None):
    """Returns (flags, group_info). flags: list of lists of strings, one per row.
    group_info: {'as_of': newest NAV date or None, 'warnings': [...]}."""
    warnings = []
    n = len(df)
    flags = [[] for _ in range(n)]
    if n == 0:
        return flags, {"as_of": None, "warnings": warnings}

    dates = pd.to_datetime(df.get("last_nav_date"), errors="coerce") if "last_nav_date" in df.columns else pd.Series([pd.NaT] * n)
    as_of = reference_date if reference_date is not None else (dates.max() if dates.notna().any() else None)
    as_of = None if as_of is None or pd.isna(as_of) else pd.Timestamp(as_of)

    names = df["scheme_name"].fillna("").str.strip().str.lower() if "scheme_name" in df.columns else pd.Series([""] * n)
    dup_names = names.duplicated(keep=False) & (names != "")
    cats = (df["scheme_category"].fillna("") if "scheme_category" in df.columns else pd.Series([""] * n)).map(_norm_category)
    common_cat = cats[cats != ""].mode().iloc[0] if (cats != "").any() else None

    for i in range(n):
        row = df.iloc[i]
        f = flags[i]
        if dup_names.iloc[i]:
            f.append("DUPLICATE_NAME")
        d = dates.iloc[i]
        if pd.isna(d):
            f.append("NO_NAV_DATE")
        elif as_of is not None and (as_of - d).days > stale_days:
            f.append(f"STALE_NAV({(as_of - d).days}d)")
        if common_cat and cats.iloc[i] and cats.iloc[i] != common_cat:
            f.append("CATEGORY_MISMATCH")
        bad = []
        hist = row.get("history_years")
        if pd.notna(row.get("cagr_5y")) and pd.notna(hist) and hist < 4.9:
            bad.append("5y CAGR with <5y history")
        if pd.notna(row.get("cagr_3y")) and pd.notna(hist) and hist < 2.9:
            bad.append("3y CAGR with <3y history")
        dd = row.get("max_drawdown")
        if pd.notna(dd) and not (-1.0 <= dd <= 0.0):
            bad.append("max drawdown outside -100%..0%")
        vol = row.get("volatility")
        if pd.notna(vol) and vol < 0:
            bad.append("negative volatility")
        rp = row.get("rolling_positive_pct")
        if pd.notna(rp) and not (0.0 <= rp <= 1.0):
            bad.append("rolling % outside 0..100%")
        if bad:
            f.append("INCONSISTENT: " + ", ".join(bad))

    stale_n = sum(any(x.startswith("STALE_NAV") for x in f) for f in flags)
    if stale_n:
        warnings.append(f"{stale_n} fund(s) have a NAV older than {stale_days} days versus the newest NAV in the group")
    today = pd.Timestamp.now().normalize()
    if as_of is not None and (today - as_of).days > stale_days:
        warnings.append(f"newest NAV in the data is dated {as_of.date()}, {(today - as_of).days} days ago -- "
                        f"this run is not current")
    return flags, {"as_of": as_of, "warnings": warnings}
