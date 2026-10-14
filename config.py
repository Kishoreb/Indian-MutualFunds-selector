"""
Central configuration for the Mutual Fund Shortlister.

Edit the values below to change filtering thresholds, scoring weights,
and general settings -- no need to touch the logic in the other files.
"""

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------
# Free NAV history API (no key required). Works for Indian mutual funds.
# https://www.mfapi.in/
MFAPI_BASE_URL = "https://api.mfapi.in/mf/{scheme_code}"

# Where raw NAV history CSVs are cached after download, so re-runs don't
# have to hit the network again the same day.
DATA_DIR = "data"

# Re-download NAV history if the cached file is older than this many days.
CACHE_MAX_AGE_DAYS = 1

# ---------------------------------------------------------------------------
# Category discovery (fetches the full AMFI scheme list and filters it)
# ---------------------------------------------------------------------------
# How long to keep the ~30,000-scheme master list cached before re-fetching.
SCHEME_MASTER_CACHE_DAYS = 7

# Only consider Direct plans (skip Regular plans, which carry distributor
# commission and therefore lower returns for the same underlying fund).
REQUIRE_DIRECT_PLAN = True

# Only consider Growth plans (skip IDCW/Dividend plans, whose NAV is
# depressed by payouts and so isn't comparable on a CAGR basis).
REQUIRE_GROWTH_PLAN = True

# Exclude passive index funds / ETFs -- set True if you want them included.
INCLUDE_INDEX_FUNDS = False

# Exclude fund-of-funds (funds that just invest in other funds).
INCLUDE_FUND_OF_FUNDS = False

# Safety cap on how many candidate funds get a full NAV fetch + metrics
# pass. Most single categories (small cap, midcap, large cap, etc.) have
# well under 40 Direct+Growth funds across all AMCs, so this typically
# won't trigger. It exists as a safety valve for broad/loosely-matched
# categories. If it does trigger, candidates are capped alphabetically
# (not by any quality measure) -- raise this value for an exhaustive scan.
MAX_FUNDS_TO_SCAN = 60

# ---------------------------------------------------------------------------
# Risk-free rate used for the risk-adjusted return (Sharpe-style) ratio.
# A reasonable proxy is the current short-term G-Sec / FD rate.
# ---------------------------------------------------------------------------
RISK_FREE_RATE = 0.065  # 6.5% annualized

# ---------------------------------------------------------------------------
# Minimum hard filters -- funds failing ANY of these are dropped before
# scoring/ranking. Set a value to None to disable that filter.
# ---------------------------------------------------------------------------
MIN_CAGR_1Y = 0.08     # at least 8% 1-year return
MIN_CAGR_3Y = 0.10     # at least 10% 3-year CAGR
MIN_CAGR_5Y = 0.10     # at least 10% 5-year CAGR
MAX_VOLATILITY = 0.35  # annualized volatility must be under 35%
MIN_RISK_RETURN_RATIO = 0.5  # (CAGR - risk free) / volatility must clear this
MIN_HISTORY_YEARS = 5.0  # fund must have at least this much NAV history

# Sortino ratio (downside-only risk-adjusted return) and rolling-return
# consistency filters. Left as None (disabled) by default since they need
# more history to compute reliably -- funds still get SCORED on these
# metrics below even if you don't hard-filter on them.
MIN_SORTINO_RATIO = None
MIN_ROLLING_POSITIVE_PCT = None  # e.g. 0.7 = at least 70% of rolling windows were positive

# ---------------------------------------------------------------------------
# SIP (systematic investment plan) simulation settings, used to compute
# sip_xirr -- the annualized return an investor doing a monthly SIP would
# actually have earned, which differs from lumpsum CAGR.
# ---------------------------------------------------------------------------
SIP_YEARS = 3.0            # simulate a SIP over the trailing N years
SIP_MONTHLY_AMOUNT = 1000  # amount invested each month (currency-agnostic; only the ratio matters)

# ---------------------------------------------------------------------------
# Rolling-return window used for the consistency metrics (rolling_avg,
# rolling_min, rolling_positive_pct, rolling_std, rolling_beat_benchmark_pct).
# ---------------------------------------------------------------------------
ROLLING_WINDOW_YEARS = 3.0

# ---------------------------------------------------------------------------
# Benchmark-relative metrics (benchmark.py):
#   benchmark_excess_return      fund CAGR minus benchmark CAGR, same dates
#   rolling_beat_benchmark_pct   % of rolling windows in which the fund beat
#                                the benchmark
#
# Benchmark data, first match wins per category:
#   1. CSV in BENCHMARK_DIR named after the category, e.g.
#      data/benchmarks/small_cap.csv, large_and_mid_cap.csv  (columns: date, nav)
#      -> drop real NSE Total Return Index history here for best accuracy.
#   2. "scheme_code" below, if you pin a specific index fund.
#   3. Auto-discovery: the Direct-Growth index fund tracking the index with the
#      longest NAV history. This is a PROXY: it runs slightly below the true TRI
#      (expense ratio + tracking error), so excess return is overstated by
#      roughly that gap (typically well under 1 point a year).
# A category with no entry (sectoral/thematic) gets no benchmark metrics.
# ---------------------------------------------------------------------------
BENCHMARK_ENABLED = True
BENCHMARK_EXCESS_YEARS = 3.0        # period for benchmark_excess_return
BENCHMARK_DIR = "data/benchmarks"
BENCHMARK_MAX_CANDIDATES = 6        # how many proxy funds to compare for history length
BENCHMARK_MAX_STALENESS_DAYS = 10   # benchmark data older than the fund by more than this -> metric left missing

# Words that disqualify an index fund as a plain-vanilla benchmark proxy.
BENCHMARK_EXCLUDE_WORDS = [
    "momentum", "quality", "value", "alpha", "low vol", "equal weight",
    "enhanced", "etf", "fund of fund", "fof", "idcw", "dividend", "bonus",
    "next 50", "multifactor", "factor",
]

# keywords are matched against the scheme name with all spaces removed.
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
# NOTE: "value" and "BENCHMARK_EXCLUDE_WORDS" above also drop value-style *index*
# funds (e.g. Nifty 500 Value 50) from the proxy search, which is intended:
# the proxy should track the broad index, not a factor index.

# ---------------------------------------------------------------------------
# Portfolio quality (portfolio_quality.py, spec parameter 8)
# A 0-100 score from DISCLOSED monthly holdings. Where no holdings file is
# found for a fund the metric is simply missing (never guessed).
#   Put/auto-download AMC files under HOLDINGS_DIR (see holdings_fetch.py):
#       python shortlist.py "small cap" --fetch-holdings
# The sub-criteria thresholds below are this toolkit's DEFAULTS, not an
# industry standard: "worst" scores 0, "best" scores 100, linear in between.
# ---------------------------------------------------------------------------
PORTFOLIO_QUALITY_ENABLED = True
HOLDINGS_DIR = "data/holdings"
# Optional CSV (columns: isin, category = large/mid/small) built from AMFI's half-yearly
# stock categorisation list. Without it the liquidity sub-criterion is skipped.
AMFI_MARKETCAP_CSV = "data/amfi_market_cap.csv"

PQ_CRITERIA = {
    "top10_pct":      {"weight": 0.25, "worst": 65.0, "best": 25.0},  # % of NAV in top-10 equity holdings
    "n_holdings":     {"weight": 0.15, "worst": 15,   "best": 60},    # number of equity holdings
    "top_sector_pct": {"weight": 0.20, "worst": 45.0, "best": 20.0},  # % of NAV in the largest industry
    "largemid_pct":   {"weight": 0.25, "worst": 20.0, "best": 80.0},  # % of equity in large+mid caps (liquidity)
    "cash_pct":       {"weight": 0.15, "worst": 25.0, "best": 5.0},   # cash/TREPS/net receivables, % of NAV
}
PQ_MIN_COVERAGE = 0.6         # share of the criteria weights that must be measurable, else the score is missing
PQ_MIN_EQUITY_HOLDINGS = 10   # fewer equity holdings than this -> not an equity portfolio, no score
PQ_MIN_MCAP_MATCH = 0.9       # share of equity weight that must be found in the AMFI list to use it
PQ_SUM_TOLERANCE = (95.0, 105.0)  # statement weights (ex-derivatives) must add up to this many %
PQ_MAX_AGE_DAYS = 75          # statements older than this (when the as-on date is readable) are ignored; None = off
PQ_NAME_MATCH_RATIO = 0.95    # fuzzy scheme-name match threshold (exact normalised match is tried first)
HOLDINGS_MONTHS_TO_FETCH = 1  # auto-downloaders fetch the newest N month-end files

# ---------------------------------------------------------------------------
# Composite score weights (used to RANK funds that pass the hard filters).
# These should sum to 1.0 but the code will normalize automatically if not.
# Each metric is z-scored (standardized) across the shortlisted funds before
# weights are applied, so funds are compared on a level footing.
# Benchmark metrics that are missing for a fund (no benchmark / too little
# history, no holdings file) are treated as average (z=0), like every other missing metric.
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "cagr_1y": 0.05,
    "cagr_3y": 0.15,
    "cagr_5y": 0.15,
    "risk_return_ratio": 0.05,
    "sortino_ratio": 0.10,
    "rolling_positive_pct": 0.05,          # consistency: % of rolling windows that were positive
    "sip_xirr": 0.05,
    "max_drawdown": 0.10,                  # smaller (less negative) drawdown is better
    "benchmark_excess_return": 0.10,       # fund CAGR minus benchmark CAGR (matched dates)
    "rolling_beat_benchmark_pct": 0.10,    # % of rolling windows the fund beat its benchmark
    "portfolio_quality": 0.10,             # 0-100 from disclosed holdings; missing for most funds until files are supplied
}

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
TOP_N = 15  # how many funds to show in the final shortlist
OUTPUT_CSV = "shortlisted_funds.csv"

# Excel export (in addition to CSV). Set to False to skip.
EXPORT_EXCEL = True
OUTPUT_XLSX = "shortlisted_funds.xlsx"
