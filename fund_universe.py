"""
fund_universe.py
-----------------
Fetches AMFI's full mutual fund scheme master (via mfapi.in, which mirrors
AMFI) and filters it down to a list of candidate funds for a given category
input like "small cap", "midcap", "large cap", "multi cap", "flexi cap",
"elss", etc.

Matching happens in two stages:
  1. A cheap NAME pre-filter here (keywords + exclusions), so we only
     download NAV history for plausible candidates.
  2. A post-fetch check of the AMFI `scheme_category` string that mfapi.in
     returns with each NAV payload (`category_matches`), which is the
     authoritative label and catches name-matching mistakes.

Only Direct + Growth plan variants are kept by default (configurable in
config.py) so that funds are compared on equal footing.

This module does NOT know anything about fund performance -- it only
resolves "category name" -> "list of candidate scheme codes".
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timedelta

import requests

import config
from logutil import get_logger

log = get_logger(__name__)

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

# Substrings (matched against the NORMALIZED scheme name, see _normalize)
# that identify each canonical category.
CATEGORY_KEYWORDS = {
    "small cap": ["small cap", "smallcap"],
    "mid cap": ["mid cap", "midcap"],
    "large cap": ["large cap", "largecap", "bluechip", "blue chip"],
    "multi cap": ["multi cap", "multicap"],
    "flexi cap": ["flexi cap", "flexicap"],
    "large & mid cap": ["large and mid cap", "large and midcap", "large midcap",
                        "large mid cap", "largemidcap"],
    "elss": ["elss", "tax saver", "tax saving"],
    "focused": ["focused"],
    "value": ["value fund"],
    "contra": ["contra"],
    "dividend yield": ["dividend yield"],
    "sectoral": ["sectoral", "thematic"],
}

# Names containing any of these (normalized) are NOT counted as the
# category even if a keyword matches -- e.g. "mid cap" is a substring of
# "Large & Mid Cap", which is a different SEBI category.
CATEGORY_NAME_EXCLUDES = {
    "mid cap": ["large and mid", "large mid", "largemidcap", "large and midcap"],
    "large cap": ["large and mid", "large mid", "largemidcap", "large and midcap"],
}

# What mfapi.in's `scheme_category` looks like for each category, e.g.
# "Equity Scheme - Mid Cap Fund". (keywords any-of, excludes none-of),
# matched against the normalized string.
CATEGORY_API_RULES = {
    "small cap": (["small cap"], []),
    "mid cap": (["mid cap"], ["large and mid"]),
    "large cap": (["large cap"], ["large and mid"]),
    "multi cap": (["multi cap"], []),
    "flexi cap": (["flexi cap"], []),
    "large & mid cap": (["large and mid cap"], []),
    "elss": (["elss"], []),
    "focused": (["focused"], []),
    "value": (["value fund"], []),
    "contra": (["contra fund"], []),
    "dividend yield": (["dividend yield"], []),
    "sectoral": (["sectoral", "thematic"], []),
}

# Passive / smart-beta markers. Word-boundary regexes so e.g. "index" doesn't
# match inside an unrelated word.
_PASSIVE_RE = re.compile(
    r"\b(index|etfs?|nifty|sensex|momentum|low vol(atility)?|equal weight|"
    r"alpha low vol|quality 30|nifty next 50)\b"
)
_FOF_RE = re.compile(r"\b(fof|fund of funds?)\b")
# Payout / bonus options. "dividend yield" is a fund CATEGORY, not an option,
# so it is stripped before testing for the word "dividend".
_PAYOUT_RE = re.compile(r"\b(idcw|dividend|payout|bonus|reinvest(ment)?)\b")


def _normalize(text: str) -> str:
    """Lowercase; '&' -> 'and'; hyphens/underscores -> spaces; collapse spaces."""
    t = (text or "").lower().replace("&", " and ")
    t = re.sub(r"[-_/]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


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
        try:
            with open(ALL_SCHEMES_CACHE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass  # corrupt cache -> re-download below

    resp = requests.get(ALL_SCHEMES_URL, timeout=60)
    resp.raise_for_status()
    schemes = resp.json()

    with open(ALL_SCHEMES_CACHE, "w") as f:
        json.dump(schemes, f)
    return schemes


def _is_preferred_plan(name: str) -> bool:
    """Applies the Direct/Growth/exclude-passive/exclude-FoF rules from
    config.py to a scheme name."""
    n = _normalize(name)
    if config.REQUIRE_DIRECT_PLAN and "direct" not in n:
        return False
    if config.REQUIRE_GROWTH_PLAN and "growth" not in n:
        return False
    # Strip the "dividend yield" category name before looking for payout
    # options, otherwise the Dividend Yield category could never match.
    if _PAYOUT_RE.search(n.replace("dividend yield", "")):
        return False
    if not config.INCLUDE_INDEX_FUNDS and _PASSIVE_RE.search(n):
        return False
    if not config.INCLUDE_FUND_OF_FUNDS and _FOF_RE.search(n):
        return False
    return True


def name_matches_category(canonical: str, scheme_name: str) -> bool:
    """Cheap name-based pre-filter: any category keyword present and no
    category exclusion present."""
    n = _normalize(scheme_name)
    if not any(kw in n for kw in CATEGORY_KEYWORDS[canonical]):
        return False
    return not any(bad in n for bad in CATEGORY_NAME_EXCLUDES.get(canonical, []))


def category_matches(canonical: str, scheme_category: str) -> bool | None:
    """Authoritative check against the AMFI `scheme_category` label that
    mfapi.in returns (e.g. 'Equity Scheme - Mid Cap Fund').

    Returns True / False, or None when the label is missing so the caller
    can decide what to do about an unverifiable fund."""
    if not scheme_category or not str(scheme_category).strip() or str(scheme_category).lower() == "nan":
        return None
    n = _normalize(str(scheme_category))
    any_of, none_of = CATEGORY_API_RULES[canonical]
    if not any(kw in n for kw in any_of):
        return False
    return not any(bad in n for bad in none_of)


def find_candidates(category_input: str, force_refresh: bool = False):
    """Returns (canonical_category, [{"scheme_code":..., "scheme_name_hint":...}, ...])
    for every Direct+Growth fund whose name matches the requested category.
    Candidates are returned in scheme-master order; if config.MAX_FUNDS_TO_SCAN
    is set and exceeded, a seeded random sample (not an alphabetical prefix) is
    taken -- see config.py."""
    canonical = resolve_category(category_input)
    schemes = download_scheme_master(force_refresh=force_refresh)

    seen = set()
    candidates = []
    for s in schemes:
        name = s.get("schemeName", "") or ""
        if not name_matches_category(canonical, name):
            continue
        if not _is_preferred_plan(name):
            continue

        code = str(s.get("schemeCode"))
        if code in seen:
            continue
        seen.add(code)
        candidates.append({"scheme_code": code, "scheme_name_hint": name})

    return canonical, candidates


def cap_candidates(candidates: list) -> list:
    """Applies config.MAX_FUNDS_TO_SCAN (if set) using a seeded random
    sample, so the cap isn't biased against AMCs late in the alphabet."""
    cap = config.MAX_FUNDS_TO_SCAN
    if cap is None or len(candidates) <= cap:
        return candidates
    rng = random.Random(config.SCAN_SAMPLE_SEED)
    sampled = rng.sample(candidates, cap)
    log.warning(f"{len(candidates)} candidates but MAX_FUNDS_TO_SCAN={cap}. Scanning a seeded "
          f"RANDOM sample of {cap} (seed={config.SCAN_SAMPLE_SEED}); results are NOT exhaustive. "
          f"Set MAX_FUNDS_TO_SCAN = None in config.py to scan every match.")
    return sampled
