#!/usr/bin/env python3
"""
build_marketcap.py
------------------
Builds data/amfi_market_cap.csv (columns isin,category = large/mid/small) from AMFI's half-yearly
"Average Market Capitalisation of listed companies" categorisation list, which you download
yourself from amfiindia.com (Research & Information / market capitalisation section). The file
may be an Excel sheet (.xlsx/.xls), a CSV, or the PDF.

Switching this file on enables the large+mid-cap (liquidity) criterion of the portfolio-quality score.

    python build_marketcap.py AMFI_list.xlsx
    python build_marketcap.py AMFI_list.pdf -o data/amfi_market_cap.csv

It does not guess: rows without a valid ISIN or without a clear Large/Mid/Small label are skipped
and counted, and it warns if the result does not look like AMFI's list (AMFI classes the top 100
companies by market cap as large, the next 150 as mid, the rest small).
"""

import argparse
import os
import re
import sys

import pandas as pd

ISIN = re.compile(r"\bIN[EF][0-9A-Z]{9}\b")
CAT = re.compile(r"\b(large|mid|small)\s*[- ]?cap\b", re.I)


def _norm_cat(text) -> str | None:
    m = CAT.search(str(text))
    return m.group(1).lower() if m else None


def from_text_lines(lines) -> pd.DataFrame:
    """PDF/text: a row is a line holding an ISIN and a 'Large/Mid/Small Cap' label (the last one wins)."""
    rows = []
    for line in lines:
        i = ISIN.search(line)
        c = list(CAT.finditer(line))
        if i and c:
            rows.append({"isin": i.group(0), "category": c[-1].group(1).lower()})
    return pd.DataFrame(rows, columns=["isin", "category"])


def from_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Excel/CSV read with header=None: finds the ISIN column and the column holding Large/Mid/Small Cap."""
    best = None
    for col in raw.columns:
        s = raw[col].astype(str)
        n_isin = int(s.str.fullmatch(r"\s*IN[EF][0-9A-Z]{9}\s*", case=False).sum())
        n_cat = int(s.map(lambda x: _norm_cat(x) is not None).sum())
        best = best or {"isin": (None, 0), "cat": (None, 0)}
        if n_isin > best["isin"][1]:
            best["isin"] = (col, n_isin)
        if n_cat > best["cat"][1]:
            best["cat"] = (col, n_cat)
    if not best or best["isin"][0] is None or best["cat"][0] is None:
        return pd.DataFrame(columns=["isin", "category"])
    out = pd.DataFrame({"isin": raw[best["isin"][0]].astype(str).str.strip().str.upper(),
                        "category": raw[best["cat"][0]].map(_norm_cat)})
    out = out[out["isin"].str.fullmatch(r"IN[EF][0-9A-Z]{9}") & out["category"].notna()]
    return out.reset_index(drop=True)


def read_any(path: str) -> pd.DataFrame:
    low = path.lower()
    if low.endswith(".pdf"):
        import pdfplumber
        lines = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                lines += (page.extract_text() or "").splitlines()
        return from_text_lines(lines)
    if low.endswith((".xlsx", ".xlsm", ".xls")):
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
        parts = [from_table(df) for df in sheets.values()]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["isin", "category"])
    if low.endswith((".csv", ".txt")):
        return from_table(pd.read_csv(path, header=None, dtype=object, on_bad_lines="skip"))
    raise ValueError(f"unsupported file type: {path}")


def validate(df: pd.DataFrame) -> list[str]:
    notes = []
    counts = df["category"].value_counts().to_dict()
    if len(df) < 500:
        notes.append(f"only {len(df)} companies found; AMFI's list has several thousand -- is this the full list?")
    if counts.get("large", 0) and not 80 <= counts["large"] <= 130:
        notes.append(f"{counts['large']} large-cap rows; AMFI normally has about 100")
    if counts.get("mid", 0) and not 120 <= counts["mid"] <= 180:
        notes.append(f"{counts['mid']} mid-cap rows; AMFI normally has about 150")
    for c in ("large", "mid", "small"):
        if not counts.get(c):
            notes.append(f"no '{c}' rows found")
    return notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build amfi_market_cap.csv from AMFI's categorisation list.")
    ap.add_argument("input", help="AMFI list (.xlsx/.xls/.csv/.pdf) saved on disk")
    ap.add_argument("-o", "--output", default=None, help="output CSV (default: config.AMFI_MARKETCAP_CSV)")
    a = ap.parse_args(argv)
    out = a.output
    if out is None:
        import config
        out = config.AMFI_MARKETCAP_CSV
    try:
        df = read_any(a.input)
    except Exception as exc:
        print(f"ERROR: cannot read {a.input}: {exc}", file=sys.stderr)
        return 2
    n_raw = len(df)
    df = df.drop_duplicates("isin", keep="first").reset_index(drop=True)
    if df.empty:
        print("ERROR: no ISIN + Large/Mid/Small Cap rows were found in the file.", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    df.to_csv(out, index=False)
    counts = df["category"].value_counts().to_dict()
    print(f"Wrote {len(df)} companies to {out} "
          f"(large {counts.get('large', 0)}, mid {counts.get('mid', 0)}, small {counts.get('small', 0)}); "
          f"{n_raw - len(df)} duplicate ISIN row(s) removed.")
    for n in validate(df):
        print(f"WARNING: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
