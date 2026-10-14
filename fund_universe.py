"""
fund_universe.py
-----------------
Fetches AMFI's full mutual fund scheme master (via mfapi.in, which mirrors
AMFI) and filters it down to a list of candidate funds for a given category
input like "small cap", "midcap", "large cap", "multi cap", "flexi cap",
"elss", etc.

Only Direct + Growth plan variants are kept by default (configurable in
config.py) so that funds are compared on equal footing:
  - Direct plans avoid the distributor-commission drag that Regular plans
    carry, which otherwise makes Regular-plan CAGR look artificially lower.
  - Growth plans avoid the NAV being periodically knocked down by
    dividend/IDCW payouts, which would distort CAGR calculations.

This module does NOT know anything about fund performance -- it only
resolves "category name" -> "list of candidate scheme codes". Performance
metrics are computed later in metrics.py from each candidate's NAV history.
"""

import json
import os
from datetime import datetime, timedelta

import requests

import config

ALL_SCHEMES_URL = "https://api.mfapi.in/mf"
ALL_SCHEMES_CACHE = os.path.join(config.DATA_DIR, "_scheme_master.json")

# Maps many ways a user might type a category to one canonical category key.
CATEGORY_ALIASES = {
    "small cap": "small cap", "smallcap": "small cap", "small-cap": "small cap",
    "mid cap": "mid cap", "midcap": "mid cap", "mid-cap": "mid cap",
    "large cap": "large cap", "largecap": "large cap", "large-cap": "large cap",
    "bluechip": "large cap", "blue chip": "large cap",
    "multi cap": "multi cap", "multicap": "multi cap", "multi-cap": "multi cap",
    "flexi cap": "flexi cap", "flexicap": "flexi cap", "flexi-cap": "flexi cap",
    "large and mid cap": "large & mid cap", "large & mid cap": "large & mid cap",
    "large midcap": "large & mid cap", "large mid cap": "large & mid cap",
    "elss": "elss", "tax saver": "elss", "tax saving": "elss", "tax-saver": "elss",
    "focused": "focused", "focused fund": "focused",
    "value": "value", "value fund": "value",
    "contra": "contra", "contra fund": "contra",
    "dividend yield": "dividend yield",
    "sectoral": "sectoral", "thematic": "sectoral",
}

# Substrings (matched against the lowercased scheme name) that identify
# each canonical category. AMFI/AMC scheme names reliably contain these.
CATEGORY_KEYWORDS = {
    "small cap": ["small cap"],
    "mid cap": ["mid cap", "midcap"],
    "large cap": ["large cap", "bluechip", "blue chip"],
    "multi cap": ["multi cap", "multicap"],
    "flexi cap": ["flexi cap", "flexicap"],
    "large & mid cap": ["large & mid cap", "large and mid cap", "large midcap", "large & midcap"],
    "elss": ["elss", "tax saver", "tax saving"],
    "focused": ["focused"],
    "value": ["value fund"],
    "contra": ["contra"],
    "dividend yield": ["dividend yield"],
    "sectoral": ["sectoral", "thematic"],
}


def supported_categories():
    return sorted(set(CATEGORY_ALIASES.values()))


def resolve_category(user_input: str) -> str:
    """Turns free-form user input ('midcap', 'Mid-Cap', 'mid cap') into
    the canonical category key used to look up keywords."""
    key = user_input.strip().lower().replace("_", " ")
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]

    compact = key.replace(" ", "").replace("-", "")
    for alias, canon in CATEGORY_ALIASES.items():
        if alias.replace(" ", "").replace("-", "") == compact:
            return canon

    raise ValueError(
        f"Unrecognized category '{user_input}'.\nSupported categories: {', '.join(supported_categories())}"
    )


def _cache_fresh(path: str, max_age_days: int) -> bool:
    if not os.path.exists(path):
        return False
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))
    return age < timedelta(days=max_age_days)


def download_scheme_master(force_refresh: bool = False) -> list:
    """Downloads (or loads cached) the full list of ~30,000 mutual fund
    schemes: [{"schemeCode": int, "schemeName": str, ...}, ...]."""
    os.makedirs(config.DATA_DIR, exist_ok=True)

    if not force_refresh and _cache_fresh(ALL_SCHEMES_CACHE, config.SCHEME_MASTER_CACHE_DAYS):
        with open(ALL_SCHEMES_CACHE) as f:
            return json.load(f)

    resp = requests.get(ALL_SCHEMES_URL, timeout=60)
    resp.raise_for_status()
    schemes = resp.json()

    with open(ALL_SCHEMES_CACHE, "w") as f:
        json.dump(schemes, f)
    return schemes


def _is_preferred_plan(name: str) -> bool:
    """Applies the Direct/Growth/exclude-index/exclude-FoF rules from
    config.py to a scheme name."""
    n = name.lower()
    if config.REQUIRE_DIRECT_PLAN and "direct" not in n:
        return False
    if config.REQUIRE_GROWTH_PLAN and "growth" not in n:
        return False
    if any(bad in n for bad in ["idcw", "dividend", "bonus"]):
        return False
    if not config.INCLUDE_INDEX_FUNDS and ("index" in n or "etf" in n):
        return False
    if not config.INCLUDE_FUND_OF_FUNDS and "fund of fund" in n:
        return False
    return True


def find_candidates(category_input: str, force_refresh: bool = False):
    """Returns (canonical_category, [{"scheme_code":..., "scheme_name_hint":...}, ...])
    for every Direct+Growth fund whose name matches the requested category."""
    canonical = resolve_category(category_input)
    keywords = CATEGORY_KEYWORDS[canonical]
    schemes = download_scheme_master(force_refresh=force_refresh)

    seen = set()
    candidates = []
    for s in schemes:
        name = s.get("schemeName", "") or ""
        name_l = name.lower()
        if not any(kw in name_l for kw in keywords):
            continue
        if not _is_preferred_plan(name):
            continue

        code = str(s.get("schemeCode"))
        if code in seen:
            continue
        seen.add(code)
        candidates.append({"scheme_code": code, "scheme_name_hint": name})

    return canonical, candidates
