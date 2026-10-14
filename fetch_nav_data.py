"""
fetch_nav_data.py
------------------
Downloads historical NAV (Net Asset Value) data for a list of mutual fund
scheme codes from the free mfapi.in service, and caches each fund's history
as a CSV file under DATA_DIR so subsequent runs are fast and offline-capable.

Usage (standalone):
    python fetch_nav_data.py 120503 118989 100033

Usage (as a module):
    from fetch_nav_data import get_nav_history
    df = get_nav_history("120503")   # returns a pandas DataFrame
"""

import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

import config


def _cache_path(scheme_code: str) -> str:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    return os.path.join(config.DATA_DIR, f"{scheme_code}.csv")


def _cache_is_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))
    return age < timedelta(days=config.CACHE_MAX_AGE_DAYS)


def download_nav_history(scheme_code: str) -> pd.DataFrame:
    """Hits the mfapi.in API for a single scheme code and returns a
    DataFrame with columns: date (datetime64), nav (float). Raises
    requests.RequestException on network failure."""
    url = config.MFAPI_BASE_URL.format(scheme_code=scheme_code)
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    payload = resp.json()

    if "data" not in payload or not payload["data"]:
        raise ValueError(f"No NAV data returned for scheme {scheme_code}")

    df = pd.DataFrame(payload["data"])
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df = df.dropna(subset=["nav"]).sort_values("date").reset_index(drop=True)

    # Stash the scheme name/meta alongside, useful for display later.
    df.attrs["scheme_name"] = payload.get("meta", {}).get("scheme_name", "")
    df.attrs["fund_house"] = payload.get("meta", {}).get("fund_house", "")
    df.attrs["scheme_category"] = payload.get("meta", {}).get("scheme_category", "")
    return df


def get_nav_history(scheme_code: str, force_refresh: bool = False) -> pd.DataFrame:
    """Returns NAV history for a scheme, using the local cache when fresh,
    otherwise downloading and re-caching."""
    scheme_code = str(scheme_code)
    path = _cache_path(scheme_code)

    if not force_refresh and _cache_is_fresh(path):
        df = pd.read_csv(path, parse_dates=["date"])
        return df

    df = download_nav_history(scheme_code)
    meta_row = pd.DataFrame(
        [{"scheme_name": df.attrs.get("scheme_name", ""),
          "fund_house": df.attrs.get("fund_house", ""),
          "scheme_category": df.attrs.get("scheme_category", "")}]
    )
    df.to_csv(path, index=False)
    meta_row.to_csv(path.replace(".csv", "_meta.csv"), index=False)
    return df


def get_scheme_meta(scheme_code: str) -> dict:
    """Reads cached meta info (scheme name, fund house, category) for a code."""
    scheme_code = str(scheme_code)
    meta_path = _cache_path(scheme_code).replace(".csv", "_meta.csv")
    if os.path.exists(meta_path):
        row = pd.read_csv(meta_path).iloc[0]
        return row.to_dict()
    return {"scheme_name": "", "fund_house": "", "scheme_category": ""}


def fetch_many(scheme_codes, force_refresh: bool = False, pause: float = 0.3):
    """Fetches NAV history for many scheme codes, printing progress and
    skipping (with a warning) any that fail rather than aborting the batch."""
    results = {}
    for i, code in enumerate(scheme_codes, 1):
        code = str(code).strip()
        try:
            print(f"[{i}/{len(scheme_codes)}] Fetching NAV history for {code} ...")
            results[code] = get_nav_history(code, force_refresh=force_refresh)
            time.sleep(pause)  # be polite to the free API
        except Exception as exc:
            print(f"  WARNING: could not fetch {code}: {exc}")
    return results


if __name__ == "__main__":
    codes = sys.argv[1:]
    if not codes:
        print("Usage: python fetch_nav_data.py <scheme_code_1> <scheme_code_2> ...")
        sys.exit(1)
    fetch_many(codes, force_refresh=True)
    print("Done. NAV history cached under ./data/")
