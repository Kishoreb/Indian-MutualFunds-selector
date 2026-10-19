"""
live_check.py
-------------
First-run check of the parts of the toolkit that have only ever been tested on synthetic data.
Run it ONCE on a computer with normal internet access, in the toolkit folder:

    python live_check.py                 # mfapi.in, AMFI, benchmarks
    python live_check.py --holdings      # also try the AMC portfolio downloaders (writes to data/holdings)
    python live_check.py --category "mid cap"

It prints PASS / WARN / FAIL for each step and exits 0 only if nothing FAILED. Paste the output
back if something fails - the message says which step and why. It changes nothing except the cache
under data/ (and data/holdings with --holdings).

What each step proves
  1 scheme master      mfapi.in is reachable and returns the AMFI scheme list
  2 category lookup    fund_universe finds Direct-Growth candidates for the category
  3 NAV history        a real NAV series downloads, is recent, and parses to date/nav
  4 benchmarks         every category in config.BENCHMARKS resolves a proxy (or your TRI csv)
  5 AMFI NAVAll.txt    the file mf_holdings_screener.py needs downloads and parses; ISIN coverage
  6 holdings           (--holdings) holdings_fetch.fetch_all() and what it left in data/holdings
"""

import argparse
import os
import sys
import time

import pandas as pd

results = []


def report(status, step, detail=""):
    results.append(status)
    print(f"{status:<5} {step}" + (f" -- {detail}" if detail else ""))


def guarded(step):
    def wrap(fn):
        def run(*a, **k):
            t0 = time.time()
            try:
                return fn(*a, **k)
            except (Exception, SystemExit) as exc:   # a failed check must not stop the others
                # (some toolkit functions call sys.exit(message) on fatal problems)
                text = str(exc).replace("\n", " ")[:200]
                report("FAIL", step, f"{type(exc).__name__}: {text} ({time.time() - t0:.0f}s)")
                return None
        return run
    return wrap


@guarded("1 scheme master")
def check_scheme_master():
    import fund_universe
    schemes = fund_universe.download_scheme_master(force_refresh=True)
    n = len(schemes)
    if n < 5000:
        report("FAIL", "1 scheme master", f"only {n} schemes returned (expected tens of thousands)")
    else:
        report("PASS", "1 scheme master", f"{n} schemes")


@guarded("2 category lookup")
def check_category(category):
    import fund_universe
    canonical, cands = fund_universe.find_candidates(category, force_refresh=False)
    if not cands:
        report("FAIL", "2 category lookup", f"no Direct-Growth candidates for '{category}'")
        return None
    report("PASS", "2 category lookup", f"'{canonical}': {len(cands)} candidates")
    return cands


@guarded("3 NAV history")
def check_nav(cands):
    from fetch_nav_data import get_nav_history
    code = str(cands[0]["scheme_code"])
    df = get_nav_history(code, force_refresh=True)
    if df is None or df.empty or not {"date", "nav"} <= set(df.columns):
        report("FAIL", "3 NAV history", f"scheme {code}: empty or wrong columns")
        return
    last = pd.to_datetime(df["date"]).max()
    age = (pd.Timestamp.now().normalize() - last).days
    years = (last - pd.to_datetime(df["date"]).min()).days / 365.25
    status = "PASS" if age <= 10 else "WARN"
    report(status, "3 NAV history", f"scheme {code}: {len(df)} rows, {years:.1f} years, last NAV {last.date()} ({age} days old)")


@guarded("4 benchmarks")
def check_benchmarks():
    import benchmark
    import config
    prov = benchmark.BenchmarkProvider(force_refresh=False)
    bad = []
    for key in config.BENCHMARKS:
        b = prov.get(key)
        if b is None:
            bad.append(key)
            continue
        years = (b["df"]["date"].max() - b["df"]["date"].min()).days / 365.25
        age = (pd.Timestamp.now().normalize() - b["df"]["date"].max()).days
        status = "PASS" if years >= 5 and age <= 10 else "WARN"
        report(status, f"4 benchmark '{key}'",
               f"{b['label']} via {b['source']} [{b['proxy_name']}] {years:.1f}y, last {age} days ago")
    if bad:
        report("FAIL", "4 benchmarks", "no benchmark found for: " + ", ".join(bad) +
               " (drop a TRI csv in data/benchmarks/ or run import_tri.py)")


@guarded("5 AMFI NAVAll.txt")
def check_navall():
    import mf_holdings_screener as mfs
    text = mfs.load_navall(None, True)
    recs = mfs.parse_navall(text)
    if len(recs) < 5000:
        report("FAIL", "5 AMFI NAVAll.txt", f"only {len(recs)} scheme rows parsed")
        return
    with_isin = sum(1 for r in recs if r["isins"])
    dg_all = sum(1 for r in recs if mfs.is_direct_growth(r["name"]))
    dg = sum(1 for r in recs if r["open_ended"] and mfs.is_direct_growth(r["name"]))
    cats = len({r["category"] for r in recs if r["category"]})
    detail = (f"{len(recs)} rows, {with_isin} with ISIN, {dg_all} Direct-Growth names, "
              f"{dg} of them open-ended, {cats} categories read")
    if dg == 0 or cats == 0:
        report("FAIL", "5 AMFI NAVAll.txt", detail + " -- category headers or Direct-Growth names are not being "
               "recognised, so peer ranking in mf_holdings_screener.py would find no peers. Run: "
               "python navall_diag.py")
        return
    report("PASS", "5 AMFI NAVAll.txt", detail)


@guarded("6 holdings")
def check_holdings():
    import config
    import holdings_fetch
    before = _count_files(config.HOLDINGS_DIR)
    holdings_fetch.fetch_all()
    after = _count_files(config.HOLDINGS_DIR)
    status = "PASS" if after > before else "WARN"
    report(status, "6 holdings", f"{after - before} new file(s) under {config.HOLDINGS_DIR}/ "
           f"({after} total). Run `python holdings_import.py --check` to see which parsed.")


def _count_files(root):
    return sum(len(files) for _, _, files in os.walk(root)) if os.path.isdir(root) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check the toolkit against the live services (run once, with internet).")
    ap.add_argument("--category", default="small cap", help="category to look up (default: small cap)")
    ap.add_argument("--holdings", action="store_true", help="also run the AMC portfolio downloaders")
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    print("Checking the live services (this can take a few minutes) ...\n")
    check_scheme_master()
    cands = check_category(a.category)
    if cands:
        check_nav(cands)
    check_benchmarks()
    check_navall()
    if a.holdings:
        check_holdings()

    fails, warns = results.count("FAIL"), results.count("WARN")
    print(f"\n{results.count('PASS')} passed, {warns} warning(s), {fails} failed.")
    if fails:
        print("Fix the FAIL lines first (a firewall or proxy blocking mfapi.in / amfiindia.com is the usual cause).")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
