# Mutual Fund Shortlister

A small Python toolkit that shortlists mutual funds **by category** —
just tell it "small cap", "midcap", "large cap", "flexi cap", "elss", etc.
It combines 1/3/5-year CAGR, volatility, Sharpe-style and Sortino ratios,
rolling 3-year consistency, simulated SIP XIRR, max drawdown and
**benchmark-relative skill** (alpha, beta, information ratio, up/down capture,
rolling beat %), using category-relative hard cut-offs and a weighted composite
score.

Everything is fetched live from the internet, no manual fund list needed:
- The full universe of mutual fund schemes comes from AMFI's scheme master
  (via [mfapi.in](https://www.mfapi.in/), a free mirror — no API key needed).
- NAV history for each candidate fund is pulled from the same source, in parallel.

## Files

| File                | Purpose                                                                |
|---------------------|-------------------------------------------------------------------------|
| `config.py`         | All tunable thresholds, score weights, risk-free rate, windows, output settings |
| `fund_universe.py`  | AMFI scheme master → candidates by category + plan type; AMFI-category verification |
| `fetch_nav_data.py` | Parallel NAV download with retries + local cache                      |
| `metrics.py`        | CAGR, volatility, Sharpe/Sortino, rolling returns, SIP XIRR, drawdown, benchmark stats, data-quality checks |
| `benchmark.py`      | Builds the benchmark: an index-fund proxy or the category average      |
| `report.py`         | Styled Excel workbook (Shortlist, Excluded, Run settings sheets)       |
| `logutil.py`        | Logging helper: readable console output, optional timestamped log file |
| `manifest.py`       | Writes `run_manifest.json` (audit trail for each run)                  |
| `shortlist.py`      | Main script: category → fetch → quality gate → benchmark → filter → score → rank |
| `test_pipeline.py`  | Offline synthetic-data tests (`python test_pipeline.py`)               |

## Setup

```bash
pip install -r requirements.txt     # needs Python 3.10+ and pandas >= 2.2
```

## Run it

```bash
python shortlist.py "small cap"
python shortlist.py midcap
python shortlist.py "large cap" --refresh              # force re-download instead of using cache
python shortlist.py "mid cap" --benchmark 123456       # pin a benchmark proxy by scheme code
python shortlist.py "flexi cap" --benchmark category   # use the category average as benchmark
python shortlist.py elss --benchmark none --top 10
python shortlist.py "small cap" --window 5 --filter-mode both
python shortlist.py my_funds.csv                       # CSV with a 'scheme_code' column
python shortlist.py "mid cap" --verbose                # debug-level console output
python shortlist.py "mid cap" --quiet --log-file run.log   # warnings only on screen, full log to a file
```

Supported categories (case/spacing/hyphens don't matter): `small cap`,
`mid cap`, `large cap`, `multi cap`, `flexi cap`, `large & mid cap`, `elss`,
`focused`, `value`, `contra`, `dividend yield`, `sectoral`.

Outputs: `shortlisted_funds.csv`, `shortlisted_funds.xlsx`,
`excluded_funds.csv` (every dropped fund and the reason) and
`run_manifest.json`.

### Reproducibility: `run_manifest.json`

Written on every run, even one that stops early or crashes (its `status` says
how far it got). It records when the run started and finished, the query and
CLI arguments, every UPPER_CASE setting in `config.py` plus a short
`config_hash` (two runs with the same hash used identical settings), library
versions, the benchmark used, fund counts after each stage, the latest NAV
date in the data, and the output files written. Together with
`excluded_funds.csv` this lets you explain any ranking after the fact.

## What the pipeline does

1. **Candidates** — every Direct + Growth fund whose name matches the category
   (with exclusions, so "mid cap" no longer picks up "Large & Mid Cap").
   Passive / smart-beta products (index, ETF, Nifty/Sensex, momentum, low-vol,
   equal-weight) and fund-of-funds are excluded. Dividend Yield *funds* are
   correctly recognised and not mistaken for dividend-payout plans.
   **No cap by default** (`MAX_FUNDS_TO_SCAN = None`); a cap, if you set one,
   takes a seeded random sample rather than an alphabetical prefix.
2. **Fetch** — parallel (`FETCH_WORKERS`), with retries and backoff.
3. **Data-quality gate** — drops funds whose AMFI `scheme_category` doesn't match
   the request, whose latest NAV is more than `MAX_NAV_STALENESS_DAYS` behind the
   freshest fund (merged / wound-up / broken feed), or that show a single-day NAV
   move above `NAV_JUMP_THRESHOLD` (data error / unadjusted split).
4. **Benchmark** — see below.
5. **Hard filters** — structural (history, volatility) plus category-relative
   performance cut-offs (default: at/above the category median on 3y and 5y
   CAGR, 40th percentile on Sortino). `FILTER_MODE` can also be `absolute`
   (fixed floors) or `both`.
6. **Score & rank** — weighted composite of robust, winsorized z-scores
   standardized against the whole eligible category (not just the survivors).

## Common measurement window

Volatility, downside deviation, max drawdown, the return leg of the
Sharpe/Sortino ratios, the rolling-return stats and every benchmark-relative
metric are measured over the **same trailing window for every fund**
(`RISK_WINDOW_YEARS`, default 5). Previously they used each fund's full
history, so a fund that lived through more market cycles was penalized for it.
A fund without enough history gets `None` for those metrics and is scored
neutrally on them.

## Benchmark-relative metrics

Measured on aligned month-end returns over the common window:

- **beta**, **alpha** (annualized Jensen's alpha, using the risk-free rate)
- **tracking_error** and **information_ratio** (active return per unit of active risk)
- **up_capture / down_capture** (geometric; lower down-capture is better)
- **excess_cagr** and **rolling_beat_pct** (share of rolling 3y windows in which the fund beat the benchmark)

The benchmark (`BENCHMARK_MODE`, or `--benchmark`):

- **`auto`** (default): an index-fund proxy for the category (Nifty 50/100,
  Midcap 150, Smallcap 250, Nifty 500 ... via `BENCHMARK_NAME_HINTS`, or pinned
  with `BENCHMARK_SCHEME_CODES`) if it has enough history; otherwise the
  **category average**. Index funds on newer indices (Midcap 150, Smallcap 250)
  may not have 5 years of history yet; they are rejected with a printed note
  rather than silently producing short-window numbers.
- **`category_average`**: equal-weight average of all eligible funds. Needs no
  external data. It includes the fund under test, a small self-reference that
  shrinks as the category grows.
- **`none`**: skip benchmark metrics; the score is renormalized over the
  remaining metrics.

## Scoring

Default weights (all configurable) are spread across different kinds of
evidence rather than five near-copies of "recent return":
3y CAGR 10%, 5y CAGR 15%, Sortino 20%, information ratio 15%, alpha 10%,
rolling beat % 10%, max drawdown 10%, down-capture 10%. `cagr_1y`,
`risk_return_ratio`, `sip_xirr`, `rolling_positive_pct` and
`rolling_above_hurdle_pct` are still computed and shown, just unweighted.
After scoring, the tool prints a warning if heavily-weighted metrics are
near-duplicates across the category (rank correlation ≥ 0.85).

`rolling_positive_pct` is almost always ~100% for equity funds, so it no longer
carries weight; `rolling_beat_pct` (vs benchmark) and `rolling_above_hurdle_pct`
(share of windows above `ROLLING_HURDLE`, default 12%) discriminate better.

## How the other metrics are computed

- **CAGR (1y/3y/5y)**: latest NAV vs the NAV N years ago (nearest prior
  trading day); `None` if the fund lacks that much history.
- **Volatility**: annualized std of monthly returns (`× √12`) over the window.
- **Risk-return ratio (Sharpe-style)**: `(window CAGR − risk-free) / volatility`,
  both over the same window.
- **Sortino**: `(window CAGR − risk-free) / downside deviation`, where downside
  deviation uses the *monthly risk-free rate* as the minimum acceptable return
  so numerator and denominator share one hurdle.
- **Rolling 3-year returns**: trailing 3y CAGR at each month-end; only windows
  *ending* inside the common window are used.
- **SIP XIRR**: simulated monthly SIP over the trailing `SIP_YEARS`.
- **Max drawdown**: largest peak-to-trough decline inside the window, stored as
  a *negative* fraction (−0.30 = 30% drawdown); closer to zero is better.

## Forward-looking signals (tilts, not predictions)

No signal reliably predicts future returns; expense ratio is the best-documented
exception (it is deducted from returns). So these are **off by default**: the
signal columns are always computed and shown, but they only change the ranking
with `--forward` (or `FORWARD_TILT_ENABLED = True`). The backward-looking
`composite_score` is never modified; with the tilt on, ranking uses
`combined_score = (1 - blend) x composite_score + blend x forward_tilt`
(blend default 0.20, hard-capped at 0.25) and the output shows `rank_change`
(positive = moved up) so you can see how much the ranking depends on soft signals.

**1. NAV-derived signals (no extra data)** -- `sharpe_stability` (worst-half Sharpe
over the common window), `rolling_p10` (10th-percentile rolling return),
`rolling_dispersion` (p90 - p10; lower is better), `beta_drift` and
`down_capture_drift` (std of rolling beta / down-capture vs the benchmark; lower =
steadier style).

**2. Signals from a CSV you maintain** -- mfapi only provides NAV, so run:

```bash
python shortlist.py "mid cap" --make-template     # writes fund_attributes.csv for the category, then exits
```

Fill `expense_ratio` (percent, 0.72 = 0.72%), `aum_cr`, `aum_cr_12m_ago`,
`manager_tenure_years`, optional `turnover_pct`, and `as_of` from AMFI / AMC
factsheets. Re-running the command adds new funds and never overwrites your values.
Rows older than `FORWARD_DATA_MAX_AGE_DAYS` (90) trigger a warning (or are ignored
with `FORWARD_IGNORE_STALE`); implausible values (e.g. expense ratio above
`EXPENSE_RATIO_MAX_PCT`) are rejected. `aum_strain` = (AUM / category median AUM) x
(1 + positive 12-month AUM growth), and `capacity_flag` marks funds at 2x the
median in small / mid cap, where capacity matters most.

**3. Weighting** -- `FORWARD_WEIGHTS` (inside the tilt) are normalized over the
signals that have data; missing values score neutrally. A signal is dropped, with
a warning, if fewer than `FORWARD_MIN_COVERAGE` (50%) of the category has data
(z-scoring 3 funds out of 40 is meaningless). `FORWARD_BLEND` above the cap is
clamped with a warning.

**4. Category valuation** -- a category-level P/E percentile is identical for every
fund, so it can't rank funds within a category. Put it in `category_valuation.csv`
(`category, pe_percentile, as_of`) and it appears as a rich / cheap note in the
log, manifest and Excel "Run settings" -- useful for deciding how much to allocate
to a category, never for ranking.

```bash
python shortlist.py "mid cap" --forward                  # let the tilt influence ranking
python shortlist.py "mid cap" --forward --forward-blend 0.10
python shortlist.py "mid cap" --no-forward               # force off even if enabled in config
```

**5. Back-test before trusting a weight** -- `python backtest.py "mid cap"`
(options: `--horizon 1 3 --step-months 3 --window 3`). At each past as-of date it
truncates every fund's NAV (no look-ahead), computes each NAV-derived signal as it
would have looked then, and measures the rank correlation (IC) with the realised
return over the next 1 and 3 years. Plain past performance (3y/5y CAGR, Sortino,
alpha) is tested as a yardstick: a forward signal that doesn't beat it hasn't earned
a weight. A signal is "supported" only if mean IC >= 0.10 and IC > 0 on >= 65% of
dates; results go to `signal_backtest.csv` with suggested weights.
Honest limits: overlapping horizons make the observations non-independent, a
10-year-old category yields only a handful of dates, and survivorship bias
flatters signals that reward past strength. The CSV signals can't be back-tested
(no dated history); expense ratio is justified by arithmetic, not by this test.

## Notes & caveats

- **Survivorship bias.** The universe is schemes that exist today in the AMFI
  master. Funds that were merged away or closed (disproportionately weak
  performers) are invisible, so category-relative statistics and "beats the
  median" cut-offs are somewhat flattering. Treat percentiles as relative to
  *surviving* funds.
- **Overlapping windows.** Monthly rolling 3-year windows overlap ~97%, so
  `rolling_*` statistics are strongly autocorrelated — read them as a
  consistency indicator, not as ~60 independent observations.
- The benchmark is a *proxy* (an index fund's NAV, which carries a small
  expense-ratio drag, or the category average), not the official TRI.
- This is a screening tool, not investment advice — always check exit
  loads, expense ratios, fund manager tenure, portfolio overlap, and your
  own risk profile before investing.
- Past returns (which is all this tool measures) don't guarantee future
  performance.
- The mfapi.in service is free/community-run; if it's ever unavailable,
  cached data under `data/` will still let you re-run `shortlist.py`
  without `--refresh`.

## Engineering notes

- **Requirements**: Python 3.10+ and pandas 2.2–3.x (see `requirements.txt`).
  `shortlist.py` checks this at start-up and exits with a clear message instead
  of failing deep inside a run.
- **Performance**: NAV downloads run in parallel with retry + backoff; the
  rolling-return, CAGR-lookup and SIP-date calculations use binary search /
  vectorised array operations rather than re-filtering the whole NAV table per
  month, so a full category scan is dominated by the network, not the maths.
- **Cache safety**: a cached NAV file is trusted only if it parses, is non-empty
  and its `_meta.csv` exists; otherwise it is re-downloaded. Cached and
  downloaded data are both de-duplicated and sorted by date.
- **Logging**: modules log through `logutil` (INFO to the console as plain
  lines; WARNING/ERROR prefixed). Used as a library, nothing is configured, so
  importing the modules never touches your own logging setup.
- **Tests**: `python test_pipeline.py` and `python test_forward_signals.py` (or `pytest`) runs offline against
  synthetic NAV data: known-answer checks (XIRR, drawdown, beta recovery),
  equivalence of the vectorised rolling returns with the original loop, edge
  cases (empty / single-row / NaN / constant NAV never raise), cache-corruption
  and retry behaviour, and full end-to-end runs with a patched network.
