"""
fund_filters.py
---------------
Optional hard filters that need data beyond NAV history (AUM, manager tenure, portfolio
turnover, average cash, top-10 concentration). All thresholds default to None (off) in config.py.

Attribute data comes from a CSV YOU supply (config.FUND_ATTRIBUTES_CSV), columns:
    scheme_code, aum_cr, manager_tenure_years, portfolio_turnover_pct, avg_cash_pct_12m
Any column may be left out or blank. A fund with no value for a filter is never dropped by that
filter; it gets a "no <attribute> data" flag instead, because nothing is guessed.
"""

import os

import pandas as pd

ATTRIBUTE_COLUMNS = ["aum_cr", "manager_tenure_years", "portfolio_turnover_pct", "avg_cash_pct_12m"]


def load_attributes(path: str) -> pd.DataFrame | None:
    if not path or not os.path.exists(path):
        return None
    raw = pd.read_csv(path, dtype={"scheme_code": str})
    raw.columns = [c.strip().lower() for c in raw.columns]
    if "scheme_code" not in raw.columns:
        raise ValueError(f"{path} needs a 'scheme_code' column")
    keep = ["scheme_code"] + [c for c in ATTRIBUTE_COLUMNS if c in raw.columns]
    raw = raw[keep].copy()
    raw["scheme_code"] = raw["scheme_code"].astype(str).str.strip()
    for c in keep[1:]:
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    return raw.drop_duplicates("scheme_code", keep="last")


def merge_attributes(df: pd.DataFrame, attrs: pd.DataFrame | None) -> pd.DataFrame:
    out = df.copy()
    for c in ATTRIBUTE_COLUMNS:
        if c not in out.columns:
            out[c] = float("nan")
    if attrs is None:
        return out
    idx = attrs.set_index("scheme_code")
    codes = out["scheme_code"].astype(str)
    for c in idx.columns:
        out[c] = codes.map(idx[c])
    return out


def _category_key(cat: str | None) -> str | None:
    import benchmark  # lazy; only needed for per-category AUM caps
    return benchmark.category_key(cat)


def apply_attribute_filters(df: pd.DataFrame, cfg) -> tuple[pd.DataFrame, dict, dict]:
    """Returns (survivors, reasons {scheme_code: [text]}, gaps {scheme_code: [text]}).
    `cfg` is the config module (read for the MIN_/MAX_ settings)."""
    reasons, gaps = {}, {}
    drop = set()

    def rule(label, attr, column, test, active):
        if not active or column not in df.columns:
            return
        for _, r in df.iterrows():
            v = r[column]
            code = str(r["scheme_code"])
            if pd.isna(v):
                gaps.setdefault(code, []).append(f"no {attr} data")
            elif test(v, r):
                reasons.setdefault(code, []).append(label)
                drop.add(code)

    rule("AUM below minimum", "AUM", "aum_cr", lambda v, r: v < cfg.MIN_AUM_CR, cfg.MIN_AUM_CR is not None)
    by_cat = getattr(cfg, "MAX_AUM_CR_BY_CATEGORY", {}) or {}
    if cfg.MAX_AUM_CR is not None or by_cat:
        def cap_for(r):
            key = _category_key(r.get("scheme_category")) if by_cat else None
            return by_cat.get(key, cfg.MAX_AUM_CR)
        for _, r in df.iterrows():
            cap, code, v = cap_for(r), str(r["scheme_code"]), r.get("aum_cr")
            if cap is None:
                continue
            if pd.isna(v):
                gaps.setdefault(code, []).append("no AUM data")
            elif v > cap:
                reasons.setdefault(code, []).append(f"AUM above {cap:g} cr")
                drop.add(code)
    rule("manager tenure too short", "manager tenure", "manager_tenure_years", lambda v, r: v < cfg.MIN_MANAGER_TENURE_YEARS,
         cfg.MIN_MANAGER_TENURE_YEARS is not None)
    rule("portfolio turnover too high", "portfolio turnover", "portfolio_turnover_pct", lambda v, r: v > cfg.MAX_PORTFOLIO_TURNOVER_PCT,
         cfg.MAX_PORTFOLIO_TURNOVER_PCT is not None)
    rule("average cash too high", "average cash", "avg_cash_pct_12m", lambda v, r: v > cfg.MAX_AVG_CASH_PCT,
         cfg.MAX_AVG_CASH_PCT is not None)
    rule("top-10 concentration too high", "top-10 concentration", "pq_top10_pct", lambda v, r: v > cfg.MAX_TOP10_PCT,
         cfg.MAX_TOP10_PCT is not None)
    kept = df[~df["scheme_code"].astype(str).isin(drop)].reset_index(drop=True)
    return kept, reasons, gaps
