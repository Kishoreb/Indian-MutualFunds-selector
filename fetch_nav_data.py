"""
fetch_nav_data.py
------------------
Downloads historical NAV (Net Asset Value) data for a list of mutual fund
scheme codes from the free mfapi.in service, and caches each fund's history
as a CSV file under DATA_DIR so subsequent runs are fast and offline-capable.

Downloads run in parallel (config.FETCH_WORKERS) with retry + backoff.

Usage (standalone):
    python fetch_nav_data.py 120503 118989 100033

Usage (as a module):
    from fetch_nav_data import get_nav_history
    df = get_nav_history("120503")   # returns a pandas DataFrame
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd
import requests

import config
from logutil import get_logger

log = get_logger(__name__)


def _cache_path(scheme_code: str) -> str:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    return os.path.join(config.DATA_DIR, f"{scheme_code}.csv")


def _meta_path(scheme_code: str) -> str:
    return _cache_path(scheme_code).replace(".csv", "_meta.csv")


def _cache_is_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))
    return age < timedelta(days=config.CACHE_MAX_AGE_DAYS)


def _http_get_json(url: str):
    """GET with retries and linear backoff. Raises the last error."""
    last_exc = None
    for attempt in range(1, config.FETCH_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < config.FETCH_RETRIES:
                time.sleep(config.FETCH_BACKOFF_SECONDS * attempt)
    raise last_exc


def download_nav_history(scheme_code: str) -> pd.DataFrame:
    """Hits the mfapi.in API for a single scheme code and returns a
    DataFrame with columns: date (datetime64), nav (float). Raises
    requests.RequestException on network failure (after retries)."""
    url = config.MFAPI_BASE_URL.format(scheme_code=scheme_code)
    payload = _http_get_json(url)

    if "data" not in payload or not payload["data"]:
        raise ValueError(f"No NAV data returned for scheme {scheme_code}")

    df = pd.DataFrame(payload["data"])
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df = (df.dropna(subset=["nav"])
            .drop_duplicates(subset="date", keep="last")
            .sort_values("date").reset_index(drop=True))

    # Stash the scheme name/meta alongside, useful for display later.
    df.attrs["scheme_name"] = payload.get("meta", {}).get("scheme_name", "")
    df.attrs["fund_house"] = payload.get("meta", {}).get("fund_house", "")
    df.attrs["scheme_category"] = payload.get("meta", {}).get("scheme_category", "")
    return df


def _read_cached(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    return (df.dropna(subset=["date", "nav"])
              .drop_duplicates(subset="date", keep="last")
              .sort_values("date").reset_index(drop=True))


def get_nav_history(scheme_code: str, force_refresh: bool = False) -> pd.DataFrame:
    """Returns NAV history for a scheme, using the local cache when fresh
    (and valid), otherwise downloading and re-caching."""
    scheme_code = str(scheme_code)
    path = _cache_path(scheme_code)

    # The cache is only trusted if BOTH the NAV file and the meta file exist
    # (the meta file carries the AMFI category used to verify the fund).
    if not force_refresh and _cache_is_fresh(path) and os.path.exists(_meta_path(scheme_code)):
        try:
            df = _read_cached(path)
            if not df.empty:
                return df
        except Exception:
            pass  # corrupt cache -> fall through and re-download

    df = download_nav_history(scheme_code)
    meta_row = pd.DataFrame(
        [{"scheme_name": df.attrs.get("scheme_name", ""),
          "fund_house": df.attrs.get("fund_house", ""),
          "scheme_category": df.attrs.get("scheme_category", "")}]
    )
    df.to_csv(path, index=False)
    meta_row.to_csv(_meta_path(scheme_code), index=False)
    return df


def get_scheme_meta(scheme_code: str) -> dict:
    """Reads cached meta info (scheme name, fund house, category) for a code."""
    meta_path = _meta_path(str(scheme_code))
    if os.path.exists(meta_path):
        try:
            row = pd.read_csv(meta_path).iloc[0]
            return {k: ("" if pd.isna(v) else v) for k, v in row.to_dict().items()}
        except Exception:
            pass
    return {"scheme_name": "", "fund_house": "", "scheme_category": ""}


def fetch_many(scheme_codes, force_refresh: bool = False, workers: int | None = None) -> dict:
    """Fetches NAV history for many scheme codes in parallel, printing
    progress and skipping (with a warning) any that fail rather than
    aborting the batch. Returns {scheme_code: DataFrame} for the successes."""
    codes = [str(c).strip() for c in scheme_codes]
    workers = workers or config.FETCH_WORKERS
    results = {}
    total = len(codes)
    done = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(get_nav_history, c, force_refresh): c for c in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            done += 1
            try:
                results[code] = fut.result()
                log.info(f"[{done}/{total}] fetched {code}")
            except Exception as exc:
                log.warning(f"[{done}/{total}] could not fetch {code}: {exc}")
    # Preserve the caller's ordering.
    return {c: results[c] for c in codes if c in results}


if __name__ == "__main__":
    codes = sys.argv[1:]
    if not codes:
        print("Usage: python fetch_nav_data.py <scheme_code_1> <scheme_code_2> ...")
        sys.exit(1)
    fetch_many(codes, force_refresh=True)
    print("Done. NAV history cached under ./data/")
