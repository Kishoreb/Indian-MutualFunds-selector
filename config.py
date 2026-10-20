"""
Central configuration for the Mutual Fund Shortlister.

Edit the values below to change filtering thresholds and general settings.
SCORE WEIGHTS and the scoring policy now live in weights.ini (see weights_loader.py).
"""

import os

import weights_loader

_HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------
MFAPI_BASE_URL = "https://api.mfapi.in/mf/{scheme_code}"
DATA_DIR = "data"
CACHE_MAX_AGE_DAYS = 1

# ---------------------------------------------------------------------------
# Category discovery
# ---------------------------------------------------------------------------
SCHEME_MASTER_CACHE_DAYS = 7
REQUIRE_DIRECT_PLAN = True
REQUIRE_GROWTH_PLAN = True
INCLUDE_INDEX_FUNDS = False
INCLUDE_FUND_OF_FUNDS = False
MAX_FUNDS_TO_SCAN = 60

# ---------------------------------------------------------------------------
# Risk-free rate used for the risk-adjusted return (Sharpe-style) ratio.
# ---------------------------------------------------------------------------
RISK_FREE_RATE = 0.065  # 6.5% annualized

# ---------------------------------------------------------------------------
# Minimum hard filters -- funds failing ANY of these are dropped before
# scoring/ranking. Set a value to None to disable that filter.
# ---------------------------------------------------------------------------
# MIN_CAGR_1Y and MIN_RISK_RETURN_RATIO are OFF (None) by default: after a weak year they removed almost
# every established fund from a category, leaving a handful of survivors. Both are still scored
# (1y CAGR 5%, Sharpe-style ratio 5% in weights.ini). Set a number to bring a filter back.
MIN_CAGR_1Y = None
MIN_CAGR_3Y = 0.10
MIN_CAGR_5Y = 0.10
MAX_VOLATILITY = 0.35
MIN_RISK_RETURN_RATIO = None
MIN_HISTORY_YEARS = 5.0
MIN_SORTINO_RATIO = None
MIN_ROLLING_POSITIVE_PCT = None

# ---------------------------------------------------------------------------
# Optional hard filters that need data beyond NAV history. ALL OFF by default (None).
# They use data/fund_attributes.csv (columns: scheme_code, aum_cr, manager_tenure_years,
# portfolio_turnover_pct, avg_cash_pct_12m -- you supply it; nothing is guessed) and the
# portfolio-quality holdings values. A fund with no value for a filter is NOT dropped by
# it; the gap is flagged in data_flags instead.
# ---------------------------------------------------------------------------
FUND_ATTRIBUTES_CSV = "data/fund_attributes.csv"
MIN_AUM_CR = None                  # drop funds with assets below this (Rs crore)
MAX_AUM_CR = None                  # drop funds above this (liquidity drag); or per category below
MAX_AUM_CR_BY_CATEGORY = {}        # e.g. {"small cap": 25000, "mid cap": 50000}; overrides MAX_AUM_CR
MIN_MANAGER_TENURE_YEARS = None    # e.g. 3.0
MAX_PORTFOLIO_TURNOVER_PCT = None  # e.g. 100
MAX_AVG_CASH_PCT = None            # e.g. 10 (12-month average cash share)
MAX_TOP10_PCT = None               # e.g. 60; uses pq_top10_pct from the holdings files

# ---------------------------------------------------------------------------
# Data-quality checks
# ---------------------------------------------------------------------------
STALE_NAV_DAYS = 10          # a fund whose last NAV is this many days older than the newest NAV in its group is stale
EXCLUDE_STALE_FUNDS = True   # stale funds are usually merged/closed; they are listed in the run log

# ---------------------------------------------------------------------------
# SIP simulation / rolling windows
# ---------------------------------------------------------------------------
SIP_YEARS = 3.0
SIP_MONTHLY_AMOUNT = 1000
# Rolling-return window for rolling_positive_pct, rolling_beat_benchmark_pct and quartile_consistency.
# 3 (default) or 5; also settable per run with --rolling-years 5. A 5-year window needs more history:
# a fund (or benchmark) needs 6+ years of NAVs to have the 12 rolling windows these metrics require,
# so with 5 years some younger funds will show those metrics as missing (handled by the missing-data policy).
ROLLING_WINDOW_YEARS = 3.0

# The Sharpe-style and Sortino ratios divide a return (3y CAGR, else 5y, else 1y) by a risk figure.
# True: that risk figure is measured over the SAME trailing period as the return. False: over the
# fund's whole history (old behaviour; penalises funds old enough to contain the 2020 crash).
RATIO_ALIGN_WINDOW = True

# Maximum drawdown window. 3 = the worst fall inside the last 3 years, the same window for every fund,
# so an older fund is not marked down for a crash a younger fund never lived through. A fund with less
# history than this gets no drawdown (left missing, never estimated). None = whole NAV history (old behaviour).
# The whole-history figure is still saved in the max_drawdown_all column.
DRAWDOWN_WINDOW_YEARS = 3.0

# Beta and Jensen's alpha (jensen_alpha, beta metrics; weights default to 0 in weights.ini): regression of
# the fund's monthly excess returns on the benchmark's, over the last ALPHA_BETA_YEARS years of month-end
# returns. Fewer than ALPHA_BETA_MIN_MONTHS common months -> left missing.
ALPHA_BETA_YEARS = 3.0
ALPHA_BETA_MIN_MONTHS = 24

# Quartile consistency (quartile_consistency metric): needs at least this many funds
# with a rolling return on a date for that date to count.
QUARTILE_MIN_PEERS = 8

# ---------------------------------------------------------------------------
# Benchmark-relative metrics (benchmark.py)
# ---------------------------------------------------------------------------
BENCHMARK_ENABLED = True
BENCHMARK_EXCESS_YEARS = 3.0
BENCHMARK_DIR = "data/benchmarks"
BENCHMARK_MAX_CANDIDATES = 6
BENCHMARK_MAX_STALENESS_DAYS = 10

BENCHMARK_EXCLUDE_WORDS = [
    "momentum", "quality", "value", "alpha", "low vol", "equal weight",
    "enhanced", "etf", "fund of fund", "fof", "idcw", "dividend", "bonus",
    "next 50", "multifactor", "factor",
]

BENCHMARKS = {
    "small cap":       {"label": "Nifty Smallcap 250 TRI", "keywords": ["nifty smallcap 250 index"], "scheme_code": None},
    "mid cap":         {"label": "Nifty Midcap 150 TRI",   "keywords": ["nifty midcap 150 index"],   "scheme_code": None},
    "large cap":       {"label": "Nifty 100 TRI",          "keywords": ["nifty 100 index"],          "scheme_code": None},
    "large & mid cap": {"label": "Nifty LargeMidcap 250 TRI", "keywords": ["largemidcap 250 index"], "scheme_code": None},
    "multi cap":       {"label": "Nifty 500 Multicap 50:25:25 TRI",
                        "keywords": ["multicap 50:25:25 index"], "scheme_code": None},
    "flexi cap":       {"label": "Nifty 500 TRI", "keywords": ["nifty 500 index"], "scheme_code": None, "exclude": ["multicap"]},
    "elss":            {"label": "Nifty 500 TRI", "keywords": ["nifty 500 index"], "scheme_code": None, "exclude": ["multicap"]},
    "focused":         {"label": "Nifty 500 TRI", "keywords": ["nifty 500 index"], "scheme_code": None, "exclude": ["multicap"]},
    "value":           {"label": "Nifty 500 TRI", "keywords": ["nifty 500 index"], "scheme_code": None, "exclude": ["multicap"]},
    "contra":          {"label": "Nifty 500 TRI", "keywords": ["nifty 500 index"], "scheme_code": None, "exclude": ["multicap"]},
    "dividend yield":  {"label": "Nifty 500 TRI", "keywords": ["nifty 500 index"], "scheme_code": None, "exclude": ["multicap"]},
    # "sectoral": intentionally absent -- no single fair benchmark.
}

# ---------------------------------------------------------------------------
# Portfolio quality (portfolio_quality.py, spec parameter 8)
# ---------------------------------------------------------------------------
PORTFOLIO_QUALITY_ENABLED = True
HOLDINGS_DIR = "data/holdings"
AMFI_MARKETCAP_CSV = "data/amfi_market_cap.csv"

PQ_CRITERIA = {
    "top10_pct":      {"weight": 0.25, "worst": 65.0, "best": 25.0},
    "n_holdings":     {"weight": 0.15, "worst": 15,   "best": 60},
    "top_sector_pct": {"weight": 0.20, "worst": 45.0, "best": 20.0},
    "largemid_pct":   {"weight": 0.25, "worst": 20.0, "best": 80.0},
    "cash_pct":       {"weight": 0.15, "worst": 25.0, "best": 5.0},
}
PQ_MIN_COVERAGE = 0.6
PQ_MIN_EQUITY_HOLDINGS = 10
PQ_MIN_MCAP_MATCH = 0.9
PQ_SUM_TOLERANCE = (95.0, 105.0)
PQ_MAX_AGE_DAYS = 75
PQ_NAME_MATCH_RATIO = 0.95
HOLDINGS_MONTHS_TO_FETCH = 1

# ---------------------------------------------------------------------------
# Score weights + policy: loaded from weights.ini (validated; the program stops with a
# clear error if the file is missing or invalid). Use `shortlist.py --weights other.ini`
# to try a different file.
# ---------------------------------------------------------------------------
WEIGHTS_FILE = os.path.join(_HERE, "weights.ini")


def apply_weights(path: str):
    """(Re)loads a weights file into the module-level settings below."""
    global SCORE_WEIGHTS, MISSING_DATA_POLICY, MIN_SCORE_COVERAGE, SCORING_METHOD
    global MIN_GROUP_SIZE, WEIGHTS_VERSION, WEIGHTS_FILE
    w = weights_loader.load(path)
    WEIGHTS_FILE = w["path"]
    SCORE_WEIGHTS = w["weights"]            # fractions summing to 1.0; every metric present, 0 = off
    MISSING_DATA_POLICY = w["policy"]
    MIN_SCORE_COVERAGE = w["min_coverage"]
    SCORING_METHOD = w["method"]
    MIN_GROUP_SIZE = w["min_group_size"]
    WEIGHTS_VERSION = w["version"]
    return w


apply_weights(WEIGHTS_FILE)

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
TOP_N = 15
OUTPUT_DIR = "."
OUTPUT_CSV = "shortlisted_funds.csv"
OUTPUT_MD = "ranked_funds.md"
OUTPUT_LOG = "run_log.txt"
EXPORT_EXCEL = True
OUTPUT_XLSX = "shortlisted_funds.xlsx"
