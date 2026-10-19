#!/usr/bin/env python3
"""
holdings_import.py
------------------
Most AMCs publish their monthly portfolio on pages that cannot be scraped safely (script-rendered, behind a
form, or not found; see `python holdings_fetch.py --list`). Download the files in your browser, then run:

    python holdings_import.py ~/Downloads/*.xls* ~/Downloads/*.zip
    python holdings_import.py --check                     # parse everything under data/holdings and report

For each file it reads the title rows of the sheets, finds which AMC they belong to (amc_registry.py aliases),
and copies the file to data/holdings/<amc_key>/ (or data/holdings/unsorted/ if the AMC cannot be told). It then
reports how many portfolio sheets parsed and how many scored, so a bad download is caught straight away.
Nothing is modified or invented; files are only copied.
"""

import argparse
import os
import shutil
import sys
import zipfile

import pandas as pd

import amc_registry
import config
import portfolio_quality as pq


def _titles(path: str) -> str:
    """Lower-cased text from the first rows of every sheet (for AMC detection)."""
    out = []
    try:
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object, nrows=12)
    except Exception:
        return ""
    for df in sheets.values():
        for v in df.astype(str).values.ravel():
            if v and v != "nan":
                out.append(v)
    return " ".join(out).lower()


def detect_amc(path: str):
    text = _titles(path) or os.path.basename(path).lower()
    best, best_len = None, 0
    for amc in amc_registry.AMCS:
        for alias in amc["aliases"]:
            if alias in text and len(alias) > best_len:
                best, best_len = amc, len(alias)
    if best is None:
        best = amc_registry.amc_for_fund_house(os.path.basename(path))
    return best


def import_files(paths, dest_root=None, log=print):
    dest_root = dest_root or config.HOLDINGS_DIR
    done = []
    for p in paths:
        low = p.lower()
        if not os.path.isfile(p):
            log(f"  skipped (not a file): {p}")
            continue
        if low.endswith(".zip"):
            amc = amc_registry.amc_for_fund_house(os.path.basename(p))
            if amc is None:
                try:
                    with zipfile.ZipFile(p) as z:
                        amc = amc_registry.amc_for_fund_house(" ".join(z.namelist()))
                except zipfile.BadZipFile:
                    log(f"  skipped (not a valid zip): {p}")
                    continue
        elif low.endswith(pq.EXCEL_EXT):
            amc = detect_amc(p)
        else:
            log(f"  skipped (not an Excel or zip file): {p}")
            continue
        folder = os.path.join(dest_root, amc["key"] if amc else "unsorted")
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, os.path.basename(p))
        if os.path.exists(target):
            log(f"  already imported: {target}")
        else:
            shutil.copy2(p, target)
            log(f"  copied to {target}" + ("" if amc else "   (AMC not recognised -- move it if you know which one)"))
        done.append(target)
    return done


def report(root=None, log=print):
    idx = pq.PortfolioIndex(root)
    scored = sum(1 for e in idx.entries if e["quality"]["score"] is not None)
    log(f"\n{idx.files_read} workbook(s) read, {len(idx.entries)} portfolio sheet(s) parsed, {scored} scored.")
    for w in idx.warnings:
        log(f"  WARNING: {w}")
    for e in idx.entries:
        q = e["quality"]
        if q["score"] is None:
            log(f"  not scored: [{e['source']} / {e['sheet']}] {q['reason']}")
    return idx


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sort downloaded AMC portfolio files into data/holdings and check them.")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--check", action="store_true", help="only parse and report what is already under data/holdings")
    a = ap.parse_args(argv)
    if not a.files and not a.check:
        print("ERROR: give files to import, or --check", file=sys.stderr)
        return 2
    if a.files:
        if not import_files(a.files):
            print("Nothing imported.", file=sys.stderr)
            return 1
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
