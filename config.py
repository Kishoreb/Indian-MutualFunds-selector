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

# Parallel download settings. Keep workers modest -- mfapi.in is a free,
# community-run service.
FETCH_WORKERS = 6
FETCH_RETRIES = 3            # attempts per scheme before giving up
FETCH_BACKOFF_SECONDS = 1.5  # sleep = backoff * attempt_number between retries

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

# Exclude passive / smart-beta products (index funds, ETFs, Nifty/Sensex
# trackers, momentum / low-vol / equal-weight factor funds) -- set True to
# include them.
INCLUDE_INDEX_FUNDS = False

# Exclude fund-of-funds (funds that just invest in other funds).
INCLUDE_FUND_OF_FUNDS = False

# After NAV data is fetched, each fund's AMFI `scheme_category` (returned by
# mfapi.in) is checked against the requested category and mismatches are
# dropped. This catches name-matching mistakes such as "Large & Mid Cap"
# funds showing up in a "mid cap" search. Set False to trust names only.
VERIFY_SCHEME_CATEGORY = True

# Optional safety cap on how many candidates get a full NAV fetch + metrics
# pass. None (default) = scan every match. Fetching is parallel, so a full
# scan of a category (typically 30-70 funds) takes well under a minute.
# If you set a cap and it triggers, a *seeded random* sample is taken (the
# old alphabetical truncation systematically dropped AMCs late in the
# alphabet), and a warning is printed.
MAX_FUNDS_TO_SCAN = None
SCAN_SAMPLE_SEED = 0

# ---------------------------------------------------------------------------
# Data-quality guards (applied before any ranking)
# ---------------------------------------------------------------------------
# A fund whose latest NAV is more than this many days older than the
# freshest fund in the scanned set is treated as stale (merged / wound up /
# feed broken) and excluded -- otherwise its CAGR is computed to an old date
# and looks perfectly normal.
MAX_NAV_STALENESS_DAYS = 7

# Any single-day NAV move larger than this (absolute) is flagged as a likely
# data error / unadjusted split / merger artifact.
NAV_JUMP_THRESHOLD = 0.20
EXCLUDE_ON_NAV_ANOMALY = True  # False = flag in the output but keep the fund

# ---------------------------------------------------------------------------
# Common measurement window
# ---------------------------------------------------------------------------
# Risk metrics (volatility, downside deviation, max drawdown), the return leg
# of the Sharpe/Sortino ratios, the rolling-return statistics, and all
# benchmark-relative metrics are computed over the SAME trailing window for
# every fund. Previously they used each fund's full history, so a fund that
# lived through more market cycles was penalized for it. A fund without this
# much history gets None for those metrics (scored neutrally).
RISK_WINDOW_YEARS = 5.0

# Risk-free rate used for Sharpe-style / Sortino ratios and for alpha.
# A reasonable proxy is the current short-term G-Sec / FD rate.
RISK_FREE_RATE = 0.065  # 6.5% annualized

# ---------------------------------------------------------------------------
# Benchmark-relative metrics (beta, alpha, information ratio, up/down capture,
# excess CAGR, % of rolling windows beating the benchmark)
# ---------------------------------------------------------------------------
# "auto"             : try an index-fund proxy for the category (see
#                      BENCHMARK_NAME_HINTS); if none with enough history is
#                      found, fall back to the category average
# "index"            : index proxy only (benchmark metrics are None if not found)
# "category_average" : equal-weight average of all scanned funds in the category
# "none"             : skip benchmark-relative metrics entirely
# Can be overridden per run with:  --benchmark <scheme_code|category|none>
BENCHMARK_MODE = "auto"

# Pin an exact benchmark proxy per category by scheme code (e.g. a Nifty 50 /
# Nifty Midcap 150 index fund or ETF whose NAV tracks the TRI). Takes
# priority over name-based discovery. Example: {"mid cap": "123456"}
BENCHMARK_SCHEME_CODES = {}

# Name-based discovery of an index proxy from the AMFI scheme master. Each
# category has an ordered list of keyword-sets; a scheme matches a set when
# its (lowercased) name contains ALL keywords. Direct + Growth only. Among
# matches the one with the longest NAV history wins.
_NIFTY_500 = [["nifty 500 index"], ["nifty 500"]]
BENCHMARK_NAME_HINTS = {
    "large cap": [["nifty 100 index"], ["nifty 50 index"], ["sensex index"]],
    "mid cap": [["nifty midcap 150 index"], ["midcap 150 index"], ["midcap 100 index"]],
    "small cap": [["nifty smallcap 250 index"], ["smallcap 250 index"], ["smallcap 100 index"]],
    "large & mid cap": [["nifty largemidcap 250 index"]] + _NIFTY_500,
    "multi cap": _NIFTY_500,
    "flexi cap": _NIFTY_500,
    "elss": _NIFTY_500,
    "focused": _NIFTY_500,
    "value": _NIFTY_500,
    "contra": _NIFTY_500,
    "dividend yield": _NIFTY_500,
    "sectoral": _NIFTY_500,
}
# Names containing any of these are never used as a benchmark proxy
# (smart-beta variants track a different index).
BENCHMARK_NAME_EXCLUDE = ["next 50", "equal weight", "momentum", "quality",
                          "alpha", "low vol", "value", "enhanced", "factor",
                          "idcw", "dividend", "bonus", "etf"]
BENCHMARK_MAX_CANDIDATES = 6  # how many name matches to fetch when choosing

# The benchmark must cover at least this fraction of RISK_WINDOW_YEARS or it
# is rejected (auto mode then falls back to the category average).
BENCHMARK_MIN_COVERAGE = 0.9

# Minimum funds contributing to a month for the category-average benchmark.
CATEGORY_AVG_MIN_FUNDS = 5

# ---------------------------------------------------------------------------
# Hard filters -- funds failing ANY active filter are dropped before
# scoring/ranking. Set a value to None to disable that filter.
# ---------------------------------------------------------------------------
# Always on (structural sanity checks, independent of market conditions):
MIN_HISTORY_YEARS = 5.0   # fund must have at least this much NAV history
MAX_VOLATILITY = 0.35     # annualized volatility must be under 35%

# FILTER_MODE decides how performance is screened:
#   "relative" : fund must rank at/above a percentile of ITS CATEGORY on the
#                metrics in RELATIVE_MIN_PERCENTILES. Market-regime proof: in
#                a bad year the category isn't wiped out, in a boom everything
#                doesn't pass.  (default)
#   "absolute" : the fixed MIN_* floors below (original behaviour)
#   "both"     : must pass both
FILTER_MODE = "relative"

# metric -> minimum percentile within the scanned category (0.5 = at or above
# the category median, 0.75 = top quartile). None disables that metric.
RELATIVE_MIN_PERCENTILES = {
    "cagr_1y": None,          # 1y is mostly noise; scored lightly, not filtered
    "cagr_3y": 0.5,
    "cagr_5y": 0.5,
    "sortino_ratio": 0.4,
}

# Absolute floors (used when FILTER_MODE is "absolute" or "both")
MIN_CAGR_1Y = 0.08
MIN_CAGR_3Y = 0.10
MIN_CAGR_5Y = 0.10
MIN_RISK_RETURN_RATIO = 0.5
MIN_SORTINO_RATIO = None
MIN_ROLLING_POSITIVE_PCT = None  # e.g. 0.7 = at least 70% of rolling windows positive

# Optional benchmark-relative floors (applied whenever benchmark metrics exist)
MIN_ALPHA = None              # e.g. 0.0 = must have non-negative annualized alpha
MIN_ROLLING_BEAT_PCT = None   # e.g. 0.5 = beat the benchmark in >= 50% of rolling windows
MAX_DOWN_CAPTURE = None       # e.g. 1.0 = must not fall more than the benchmark in down months

# ---------------------------------------------------------------------------
# SIP (systematic investment plan) simulation settings, used to compute
# sip_xirr -- the annualized return an investor doing a monthly SIP would
# actually have earned, which differs from lumpsum CAGR.
# ---------------------------------------------------------------------------
SIP_YEARS = 3.0            # simulate a SIP over the trailing N years
SIP_MONTHLY_AMOUNT = 1000  # amount invested each month (currency-agnostic; only the ratio matters)

# ---------------------------------------------------------------------------
# Rolling-return window used for the consistency metrics (rolling_avg,
# rolling_min, rolling_positive_pct, rolling_above_hurdle_pct, rolling_std).
# NOTE: monthly 3-year windows overlap ~97%, so they are strongly
# autocorrelated -- treat rolling_* stats as a consistency indicator, not as
# ~60 independent observations.
# ---------------------------------------------------------------------------
ROLLING_WINDOW_YEARS = 3.0
ROLLING_MIN_WINDOWS = 24      # fewer rolling windows than this -> rolling stats are None
ROLLING_HURDLE = 0.12         # rolling_above_hurdle_pct = share of windows with CAGR above this

# ---------------------------------------------------------------------------
# Composite score weights (used to RANK funds that pass the hard filters).
# These should sum to 1.0 but the code will normalize automatically if not.
#
# The weights are deliberately spread across *different* kinds of evidence
# (long-run return, downside-adjusted return, benchmark-relative skill,
# consistency, worst-case behaviour) instead of five near-copies of "recent
# return" (1y/3y/5y CAGR, SIP XIRR and the numerator of Sortino/Sharpe are
# highly correlated). cagr_1y, risk_return_ratio and sip_xirr are still
# computed and shown; set a weight > 0 to score on them again.
# A correlation check after scoring warns if heavily-weighted metrics are
# near-duplicates (see CORR_WARN_THRESHOLD).
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "cagr_3y": 0.10,
    "cagr_5y": 0.15,
    "sortino_ratio": 0.20,
    "information_ratio": 0.15,   # benchmark-relative return per unit of active risk
    "alpha": 0.10,               # annualized Jensen's alpha vs benchmark
    "rolling_beat_pct": 0.10,    # % of rolling windows in which the fund beat the benchmark
    "max_drawdown": 0.10,        # max_drawdown is negative: a smaller (less negative) value scores higher
    "down_capture": 0.10,        # lower is better (see LOWER_IS_BETTER)
    # Computed but unweighted by default:
    "cagr_1y": 0.0,
    "risk_return_ratio": 0.0,
    "sip_xirr": 0.0,
    "rolling_positive_pct": 0.0,
    "rolling_above_hurdle_pct": 0.0,
}

# Metrics where a LOWER value is better (their sign is flipped when scoring).
# Do NOT list max_drawdown here: it is stored as a negative fraction, so a
# less-negative number is already "higher = better".
LOWER_IS_BETTER = {"down_capture", "volatility", "downside_deviation", "tracking_error"}

# How metrics are standardized for scoring:
#   "zscore"     : robust z-score (median / 1.4826*MAD, so one extreme fund
#                  can't flatten everyone else), winsorized at +/- SCORE_WINSORIZE_Z
#   "percentile" : percentile rank within the category (robust to outliers)
# Standardization statistics are taken from the WHOLE eligible category
# (before hard filters) rather than only the handful of survivors, so a
# 10-fund shortlist doesn't get re-normalized against itself. With fewer than
# SCORE_MIN_FUNDS_FOR_ZSCORE eligible funds, percentile ranks are used anyway.
SCORING_METHOD = "zscore"
SCORE_WINSORIZE_Z = 2.5
SCORE_MIN_FUNDS_FOR_ZSCORE = 8

# After scoring, warn about weighted metric pairs whose rank correlation
# (across the eligible category) exceeds this.
CORR_WARN_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
TOP_N = 15  # how many funds to show in the final shortlist
OUTPUT_CSV = "shortlisted_funds.csv"
EXCLUDED_CSV = "excluded_funds.csv"  # every dropped fund and why
MANIFEST_JSON = "run_manifest.json"  # settings, versions, benchmark and counts for each run (audit trail)

# Excel export (in addition to CSV). Set to False to skip.
EXPORT_EXCEL = True
OUTPUT_XLSX = "shortlisted_funds.xlsx"

# ---------------------------------------------------------------------------
# Forward-looking signals (tilts, NOT return predictions)
# ---------------------------------------------------------------------------
# No signal below reliably predicts future returns; expense ratio is the best-
# documented exception. They are therefore OFF by default: the signal columns
# are always computed and shown (so you can look at them), but they only
# influence the ranking when FORWARD_TILT_ENABLED is True (or --forward is
# passed). The backward-looking composite_score is never modified; ranking
# with the tilt uses combined_score and the output shows rank_change.
FORWARD_TILT_ENABLED = False

# combined_score = (1 - FORWARD_BLEND) * composite_score + FORWARD_BLEND * forward_tilt
FORWARD_BLEND = 0.20
FORWARD_MAX_BLEND = 0.25   # hard cap; a larger FORWARD_BLEND is clamped with a warning

# Relative importance of each signal INSIDE the tilt (normalized to sum to 1
# over the signals that have data). Direction is set by FORWARD_LOWER_IS_BETTER.
# Suggested starting weights -- run backtest.py to see which NAV-derived
# signals actually ranked funds in your category, and zero out those that didn't.
FORWARD_WEIGHTS = {
    # derived from NAV data (always available):
    "sharpe_stability": 0.20,     # worst-half Sharpe over the common window (persistence)
    "rolling_p10": 0.20,          # 10th-percentile rolling return (worst-case entry points)
    "rolling_dispersion": 0.10,   # p90 - p10 of rolling returns (lower = more predictable)
    "beta_drift": 0.10,           # std of rolling beta vs benchmark (lower = steadier style)
    "down_capture_drift": 0.10,   # std of rolling down-capture (lower = steadier protection)
    # from fund_attributes.csv (manual data entry):
    "expense_ratio": 0.20,        # lower is better
    "aum_strain": 0.05,           # lower is better (see CAPACITY_* below)
    "manager_tenure_years": 0.05,
    "turnover_pct": 0.0,          # optional column; unweighted by default
}
FORWARD_LOWER_IS_BETTER = {"rolling_dispersion", "beta_drift", "down_capture_drift",
                           "expense_ratio", "aum_strain", "turnover_pct"}

# A signal is only used when at least this share of the eligible category has
# data for it; otherwise (e.g. you filled the CSV for 3 funds of 40) its
# weight is dropped with a warning, since z-scoring 3 funds is meaningless.
FORWARD_MIN_COVERAGE = 0.5

# NAV-derived signal settings
BETA_DRIFT_WINDOW_MONTHS = 24      # rolling regression window for beta
CAPTURE_DRIFT_WINDOW_MONTHS = 36   # rolling window for down-capture
SHARPE_STABILITY_MIN_MONTHS = 12   # each half of the window needs at least this many months

# --- Manually maintained fund attributes (python shortlist.py "<cat>" --make-template) ---
# Columns: scheme_code, expense_ratio (percent, 0.72 = 0.72%), aum_cr, aum_cr_12m_ago,
# manager_tenure_years, turnover_pct (optional), as_of (YYYY-MM-DD).
FUND_ATTRIBUTES_CSV = "fund_attributes.csv"
FORWARD_DATA_MAX_AGE_DAYS = 90     # rows older than this trigger a warning
FORWARD_IGNORE_STALE = False       # True = treat stale rows as missing data
EXPENSE_RATIO_MAX_PCT = 5.0        # values above this are rejected as entry errors

# AUM strain = (AUM / category median AUM) x (1 + max(12m AUM growth, 0)).
# `capacity_flag` is set when the fund is in a capacity-sensitive category and its
# AUM is at least CAPACITY_RATIO_FLAG x the category median.
CAPACITY_SENSITIVE_CATEGORIES = ["small cap", "mid cap"]
CAPACITY_RATIO_FLAG = 2.0

# --- Category valuation note (category-level, never used to rank funds) ---
# Optional CSV: category, pe_percentile (0-100, where today's category P/E sits in its own
# history), as_of. Shown as a note in the log, manifest and Excel "Run settings".
CATEGORY_VALUATION_CSV = "category_valuation.csv"
PE_RICH_PERCENTILE = 80
PE_CHEAP_PERCENTILE = 20

# ---------------------------------------------------------------------------
# Signal back-test (python backtest.py "<category>")
# ---------------------------------------------------------------------------
BACKTEST_HORIZONS_YEARS = [1.0, 3.0]
BACKTEST_STEP_MONTHS = 6
BACKTEST_MIN_FUNDS = 8              # skip as-of dates with fewer funds than this
BACKTEST_MIN_DATES = 4              # fewer dates than this -> verdict "insufficient data"
BACKTEST_MIN_MEAN_IC = 0.10         # mean rank-IC needed to call a signal "supported"
BACKTEST_MIN_POSITIVE_SHARE = 0.65  # and share of dates with IC > 0
BACKTEST_CSV = "signal_backtest.csv"
