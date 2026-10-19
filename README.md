# Mutual Fund Shortlister

A small Python toolkit that shortlists mutual funds **by category** —
just tell it "small cap", "midcap", "large cap", "flexi cap", "elss", etc.
It scores funds on:

- 1/3/5-year CAGR, volatility, a Sharpe-style risk-return ratio, a Sortino
  ratio (downside-only risk), rolling 3-year return consistency, simulated
  SIP XIRR and max drawdown;
- **benchmark-relative** performance: excess return over, and rolling
  win-rate against, the category benchmark (`benchmark.py`);
- a **portfolio-quality** score (0–100) built from the AMC's disclosed
  monthly holdings (`portfolio_quality.py`);
- two optional extras, **off by default**: downside capture and quartile
  consistency (`extra_metrics.py`).

Hard cutoffs filter funds out first; a weighted score ranks the rest. **The
weights live in `weights.ini`** (a plain text file you edit; no code changes).
Expense ratio is deliberately not scored.

The toolkit also includes a separate utility, `cdsl_holdings_to_xls.py`, that
extracts **your own** stock and mutual fund holdings from a CDSL Consolidated
Account Statement (CAS) PDF into Excel (see "Extracting your holdings from a
CDSL CAS PDF" below), and `mf_holdings_screener.py` that screens each fund in
that file and says whether to keep holding it (see "Screening the funds you
already hold" below). The second one reuses the shortlisting modules.

Data sources:
- The universe of mutual fund schemes and each fund's NAV history come from
  AMFI's scheme master via [mfapi.in](https://www.mfapi.in/) (free, no API key).
- Benchmark series: a local TRI CSV you supply (`import_tri.py`), or an index
  fund tracking the benchmark index (also from mfapi.in) as a proxy.
- Holdings: monthly portfolio Excel files published by each AMC (see
  "Portfolio quality" below for what is and isn't automated).
- Optional fund facts (AUM, manager tenure, turnover, average cash): a CSV you
  supply; nothing is guessed.
- Your own holdings (CDSL extractor only): the CAS PDF you supply.

## Files

| File                       | Purpose                                                                 |
|----------------------------|--------------------------------------------------------------------------|
| `weights.ini`              | **Score weights and scoring policy** (edit this to change the ranking)   |
| `weights_loader.py`        | Reads and validates `weights.ini`; refuses to run on a bad file          |
| `config.py`                | Thresholds, benchmark map, portfolio-quality rubric, output names, optional filters |
| `scoring.py`               | The scoring engine: per-metric scores, missing-data policy, coverage floor, ranks (pure pandas, no network) |
| `fund_universe.py`         | Fetches the AMFI scheme master and filters it by category + plan type    |
| `fetch_nav_data.py`        | Downloads & caches NAV history per scheme code                           |
| `metrics.py`               | CAGR, volatility, risk-return ratio, Sortino, rolling returns, SIP XIRR, max drawdown |
| `benchmark.py`             | Benchmark data (CSV / pinned code / auto-discovered index-fund proxy), excess return, rolling beat-benchmark % |
| `extra_metrics.py`         | Downside capture ratio and quartile consistency (off by default)         |
| `portfolio_quality.py`     | Parses AMC portfolio workbooks and computes the 0–100 portfolio-quality score |
| `holdings_fetch.py`        | Downloads monthly portfolio files for the AMCs that can be automated     |
| `amc_registry.py`          | Per-AMC knowledge: disclosure page, whether it can be automated, notes   |
| `data_checks.py`           | Duplicate / stale / inconsistent / non-comparable data flags             |
| `fund_filters.py`          | Optional AUM / manager-tenure / turnover / cash / concentration filters  |
| `report.py`                | Formats the ranked shortlist as a styled Excel workbook                  |
| `report_md.py`             | `ranked_funds.md` (why each fund scored as it did) and the run log        |
| `shortlist.py`             | Main script: categories → candidates → fetch → metrics → checks → filter → score → rank → CSV + Excel + Markdown + log |
| `build_marketcap.py`       | Builds `data/amfi_market_cap.csv` from AMFI's categorisation list you download |
| `import_tri.py`            | Turns NSE TRI downloads into `data/benchmarks/<category>.csv`            |
| `holdings_import.py`       | Sorts AMC portfolio files you downloaded into `data/holdings/<amc>/` and checks they parse |
| `live_check.py`            | One-time check of the live services (mfapi.in, AMFI, benchmarks, optionally AMC downloads) |
| `cdsl_holdings_to_xls.py`  | Standalone: CDSL CAS PDF → stock `.xls` + mutual fund `-MF.XLS` of your own holdings |
| `mf_holdings_screener.py`  | Screens each fund in your `-MF.XLS` (metrics, benchmark, peer rank) → `-Screened.XLS` with a keep/review verdict. Uses `config.py`, `metrics.py`, `benchmark.py`, `fetch_nav_data.py`, `shortlist.py` |
| `test_*.py`                | Offline tests (synthetic data, no network); see "Tests"                   |
| `requirements.txt`         | Python dependencies                                                      |

Keep all `.py` files and `weights.ini` in one folder. Data is created under `./data/`.

## Setup

```bash
pip install -r requirements.txt
```

`xlrd` is only needed for old `.xls` portfolio files (Nippon India and Baroda
BNP Paribas publish those). `pdfplumber` and `xlwt` are needed only by
`cdsl_holdings_to_xls.py`; `pytesseract` plus the Tesseract program are needed
only if your CAS PDF has no text layer (see the CDSL section).
`mf_holdings_screener.py` reads the holdings `.xls` with `xlrd` and writes `.xls`
with `xlwt`; both are in `requirements.txt`.

**First run:** on a computer with internet access, run `python live_check.py`
once. It checks mfapi.in, AMFI and the benchmark proxies and tells you what
works (see "Things not yet proven against live services").

## 1. Run it — just name a category

```bash
python shortlist.py "small cap"
python shortlist.py midcap
python shortlist.py "flexi cap" --refresh          # force re-download instead of using cache
python shortlist.py "small cap" --fetch-holdings   # also try the AMC portfolio downloaders first
python shortlist.py --category "small cap" --category "mid cap"   # each ranked separately
python shortlist.py --all-categories                # every supported category, plus an exploratory list
python shortlist.py "small cap" --weights my_weights.ini --output-dir out --top-n 20
python shortlist.py "small cap" --as-of-date 2026-10-09
python shortlist.py my_funds.csv                    # CSV with a 'scheme_code' column
```

Supported categories (case/spacing/hyphens don't matter): `small cap`,
`mid cap`, `large cap`, `multi cap`, `flexi cap`, `large & mid cap`, `elss`,
`focused`, `value`, `contra`, `dividend yield`, `sectoral`. Run
`python shortlist.py` with no arguments to see this list any time.

| Option | Meaning |
|---|---|
| `--category NAME` | A category to rank (repeat for several). Each is ranked **separately**. |
| `--all-categories` | Rank every supported category separately, then add a clearly labelled **exploratory** cross-category list |
| `--weights FILE` | Use another weights file (default: `weights.ini` next to `config.py`) |
| `--output-dir DIR` | Folder for all output files (default: current folder) |
| `--as-of-date YYYY-MM-DD` | Reference date for the stale-NAV check (default: the newest NAV in each group) |
| `--top-n N` | Funds shown per category in the printed table and Markdown report (default 15) |
| `--refresh` | Re-download NAV/scheme data instead of using the cache |
| `--fetch-holdings` | Try the AMC portfolio downloaders first |

**Exit status:** `0` finished and wrote output · `1` nothing could be ranked / no
candidate funds · `2` bad command line, bad or missing weights file, bad date, or
another fatal input error (the message says which).

This will:
1. Fetch (or load cached) AMFI's full scheme list and filter it to every
   **Direct + Growth** plan fund whose name matches the category
2. Download (or load cached) NAV history for each candidate fund
3. Compute the performance, risk and consistency metrics
4. Add benchmark-relative metrics (benchmark per fund category, see below)
5. Add the portfolio-quality score where a matching, fresh portfolio file exists
6. Check data quality (duplicates, stale NAVs, inconsistent values) and drop
   funds that fail the hard filters
7. Score the rest with the weights in `weights.ini` and rank them
8. Print the top funds and write the outputs below

**Output files** (in `--output-dir`):

| File | Contents |
|---|---|
| `shortlisted_funds.csv` | Every fund, one row each: rank, status, `final_score_0_100`, `composite_score`, `score_coverage`, `score_missing`, `confidence`, `data_flags`, every raw metric, and `score_<metric>` (0–100) and `contrib_<metric>` (points) per scored metric |
| `shortlisted_funds.xlsx` | The same, formatted, with a colour scale on the final score |
| `ranked_funds.md` | Method, weights file and version, ranking tables per category, and for the top funds each metric's raw value, 0–100 score, weight and points, plus a short rule-based explanation (strengths, weak spots, gaps, risks). No LLM is involved. Ends with the risk disclaimer |
| `run_log.txt` | Everything that happened: weights used, funds per category, exclusions with reasons, warnings |
| `shortlisted_exploratory.csv` | Only with several categories: the cross-category list (labelled exploratory) |

## 2. Tune it

### Score weights: `weights.ini`

```ini
[meta]
version = 2
missing_data_policy = renormalize_available   ; or: average
minimum_coverage_percent = 70
scoring_method = zscore                       ; or: percentile
min_group_size = 8

[weights_percent]
cagr_1y = 5
cagr_3y = 15
cagr_5y = 15
risk_return_ratio = 5
sortino_ratio = 10
rolling_positive_pct = 5
sip_xirr = 5
max_drawdown = 10
benchmark_excess_return = 10
rolling_beat_benchmark_pct = 10
portfolio_quality = 10
downside_capture = 0          ; new, off by default (lower is better)
quartile_consistency = 0      ; new, off by default
```

Edit the numbers and save. The program **refuses to run** (exit status 2, with a
message saying what is wrong) if the file is missing, a metric is missing or
unknown, a weight is non-numeric or negative, or the weights do not add up to
100. Nothing is silently replaced. List every metric; use `0` to switch one off.
To use a different file for one run: `--weights other.ini`. The file's `version`,
its path and the weights actually used are printed in the run log and
`ranked_funds.md`.

**What the settings mean**

- `missing_data_policy = renormalize_available` — a fund's score is the weighted
  average over the metrics it **has**; the weights of the others are rescaled so
  they still sum to 100%. Example: a fund with no benchmark history is missing two
  metrics worth 20%; its score is built from the other 80%, each weight divided by 0.8
  (a 15% weight counts as 18.75%). This is *renormalization*. The alternative,
  `average`, counts a missing metric as an average score (the toolkit's original behaviour).
- `minimum_coverage_percent` — the share of the total weight that must be measured
  before a fund gets a rank. Below it the fund is listed as `INSUFFICIENT_DATA`
  with no rank (under either policy). Set it to `0` with `average` to rank every
  fund, as the toolkit used to.
- `scoring_method` — `zscore` standardises each metric across the funds being
  ranked (the toolkit's original method); `percentile` uses percentile ranks (0–100,
  ties share the average rank), which one extreme fund cannot distort. Whichever you
  pick, `final_score_0_100` is always the percentile-based 0–100 score and the
  per-metric `score_` / `contrib_` columns always explain it.
- `min_group_size` — a ranking built from fewer funds than this is flagged
  **LOW CONFIDENCE** (in the CSV `confidence` column and the report).

`score_coverage` (CSV/Excel) shows how much of each fund's score rests on real
data (100% = nothing missing) and `score_missing` names what was missing. Nothing
is ever estimated to fill a gap, and a real value of zero is never treated as missing.

### Hard filters and other settings: `config.py`

- **Hard filters** (`MIN_CAGR_1Y/3Y/5Y`, `MAX_VOLATILITY`, `MIN_RISK_RETURN_RATIO`,
  `MIN_HISTORY_YEARS`, optional `MIN_SORTINO_RATIO`, `MIN_ROLLING_POSITIVE_PCT`): a
  fund failing any is dropped. Set to `None` to disable. **`MIN_CAGR_1Y` and
  `MIN_RISK_RETURN_RATIO` are off by default**: after a weak year they removed almost every
  established small-cap fund (5 of 53 candidates survived the first live run). Both metrics are
  still scored through `weights.ini`. Set a number to bring either filter back.
- **`RATIO_ALIGN_WINDOW`** (default `True`): see "Risk-return ratio" below.
- **Data-quality checks** (`STALE_NAV_DAYS`, `EXCLUDE_STALE_FUNDS`): see below.
- **Optional fund-fact filters** (all off by default): `MIN_AUM_CR`, `MAX_AUM_CR`
  (or per category in `MAX_AUM_CR_BY_CATEGORY`), `MIN_MANAGER_TENURE_YEARS`,
  `MAX_PORTFOLIO_TURNOVER_PCT`, `MAX_AVG_CASH_PCT`, `MAX_TOP10_PCT`. They read
  `data/fund_attributes.csv` (columns `scheme_code, aum_cr, manager_tenure_years,
  portfolio_turnover_pct, avg_cash_pct_12m`; any column may be left out or blank),
  which **you** supply — the toolkit has no source for these. A fund with no value for
  an active filter is *not* dropped; the gap is flagged in `data_flags`. `MAX_TOP10_PCT`
  uses the top-10 share from the holdings files instead.
- **Benchmark settings** (`BENCHMARK_*`, `BENCHMARKS`) and the **portfolio-quality
  rubric** (`PQ_*`, `HOLDINGS_DIR`, `AMFI_MARKETCAP_CSV`): see below.
- `RISK_FREE_RATE`, `TOP_N`, `OUTPUT_*`, `MAX_FUNDS_TO_SCAN`, `QUARTILE_MIN_PEERS`, and
  the plan-type switches (`REQUIRE_DIRECT_PLAN`, `REQUIRE_GROWTH_PLAN`,
  `INCLUDE_INDEX_FUNDS`, `INCLUDE_FUND_OF_FUNDS`).

### Data-quality flags (`data_flags` column and run log)

| Flag | Meaning |
|---|---|
| `DUPLICATE_CODE` | The same scheme code appeared twice; extra rows are dropped (and counted in the log) |
| `DUPLICATE_NAME` | Another fund has the same name |
| `STALE_NAV(nd)` | Last NAV is *n* days older than the newest NAV in its group; such funds are excluded and listed (set `EXCLUDE_STALE_FUNDS = False` to keep them flagged only) |
| `INCONSISTENT: …` | e.g. a 5y CAGR with under 5y of history, a drawdown outside −100%…0% |
| `CATEGORY_MISMATCH` | The fund's AMFI category differs from its group's most common one |
| `NO_NAV_DATE` | No usable NAV date |
| `no <attribute> data` | An active optional filter had no value for this fund |

The run also warns if the newest NAV in the data is itself older than `STALE_NAV_DAYS`
(the data is not current), and every group shows its as-of date.

## How the metrics are computed

- **CAGR (1y/3y/5y)**: latest NAV vs the NAV N years ago (nearest trading day).
  Not enough history → `None`.
- **Volatility**: annualised std-dev of month-over-month NAV returns (`× √12`).
- **Risk-return ratio (Sharpe-style)**: `(3y CAGR − risk-free rate) / volatility`, where the
  volatility is measured over the **same 3 years** as the return (the last 36 monthly returns).
  If a fund has no 3y return the 5y, then the 1y return is used with a 60- or 12-month window
  (`ratio_window_years` in the CSV says which). With `RATIO_ALIGN_WINDOW = False` the volatility
  covers the fund's whole history instead (the old behaviour, which penalised funds old enough
  to contain the 2020 crash). The plain `volatility` and `downside_deviation` columns, and the
  `MAX_VOLATILITY` filter, still use the whole history.
- **Sortino ratio**: same, divided by downside deviation over the same window.
- **Rolling 3-year returns**: trailing 3-year CAGR at every month-end; summarised
  as average, minimum, std-dev and `rolling_positive_pct` (share of windows > 0).
- **SIP XIRR**: monthly SIP simulated over the trailing `SIP_YEARS`.
- **Max drawdown**: largest peak-to-trough NAV decline over the fund's history
  (stored negative; a smaller fall scores higher).
- **Downside capture** (`extra_metrics.py`, off by default): over the months the
  benchmark fell, the fund's average monthly return divided by the benchmark's
  (below 1.00 = lost less than the benchmark; **lower is better**; negative = the
  fund rose on average when the benchmark fell). Needs the benchmark and at least 6
  down months.
- **Quartile consistency** (`extra_metrics.py`, off by default): the share of
  month-end rolling-return dates on which the fund was in the top half of the funds
  being ranked (the share in the top quarter is saved as `q1_share`). Dates with fewer
  than `QUARTILE_MIN_PEERS` funds are skipped; needs 12+ usable dates. The "peer group"
  is only the funds in that run, so it is as good as that universe.

### Benchmark-relative metrics (`benchmark.py`)

- **`benchmark_excess_return`**: fund CAGR minus benchmark CAGR over the *same*
  dates (`BENCHMARK_EXCESS_YEARS`, default 3).
- **`rolling_beat_benchmark_pct`**: share of rolling windows in which the fund's
  trailing CAGR beat the benchmark's (this is the spec's "rolling consistency").

Each fund is benchmarked by its own AMFI category (`BENCHMARKS` in `config.py`;
sectoral/thematic funds have none). Benchmark data, first match wins:

1. a CSV in `data/benchmarks/` named after the category (`small_cap.csv`,
   `large_and_mid_cap.csv`, …) with columns `date` and `nav` (or `tri`/`close`) —
   **use `import_tri.py` to create these from NSE downloads** (below);
2. a scheme code pinned in `BENCHMARKS[...]["scheme_code"]`;
3. **auto-discovery**: the plain Direct-Growth index fund tracking that index
   with the longest NAV history (momentum/quality/ETF/Regular-plan variants excluded).

Option 3 is only a **proxy**: an index fund's NAV runs slightly below the true
TRI (expense ratio + tracking error), so excess return is overstated by roughly
that gap. The run prints which proxy was used and every output row records it.
A benchmark that is missing, stale (`BENCHMARK_MAX_STALENESS_DAYS`) or too short
leaves the metrics empty.

**Real TRI data — `import_tri.py`.** Download Total Return Index history from NSE
(NSE limits the date range per download, so there may be several files), then:

```bash
python import_tri.py --list                      # categories and the index each one expects
python import_tri.py --category "small cap" smallcap250_tri_2015_2020.csv smallcap250_tri_2020_2026.csv
```

It merges the files, removes duplicate dates, checks that dates and values parse, looks
for large gaps, reports the history length and how recent the last date is, and writes
`data/benchmarks/small_cap.csv` (the file name `benchmark.py` expects). Use the **TRI**,
not the price index, so the fund (which reinvests dividends) is compared like for like.

### Portfolio quality (`portfolio_quality.py`)

A 0–100 score from the equity holdings in the AMC's monthly portfolio
disclosure, from five sub-criteria, each mapped linearly between a "worst" and
a "best" value (`PQ_CRITERIA` in `config.py`):

| Sub-criterion    | Meaning                                              | Better |
|------------------|------------------------------------------------------|--------|
| `top10_pct`      | % of NAV in the ten largest equity holdings          | lower  |
| `n_holdings`     | number of equity holdings                            | higher |
| `top_sector_pct` | % of NAV in the largest industry                     | lower  |
| `largemid_pct`   | % of equity in large+mid caps (liquidity proxy)      | higher |
| `cash_pct`       | cash, TREPS, net receivables as % of NAV             | lower  |

The score is the weighted average of the sub-criteria that could be measured,
and is left **missing** if less than `PQ_MIN_COVERAGE` of the weight is
measurable. It is also left missing for: no matching file, a non-equity scheme
(fewer than `PQ_MIN_EQUITY_HOLDINGS` equity holdings), weights that don't add
up to ~100%, or a statement older than `PQ_MAX_AGE_DAYS`. `pq_note` in the CSV
says why. The thresholds are this toolkit's defaults, **not an industry
standard** — tune them. Concentrated-by-design funds (focused, sectoral) score
lower on concentration by construction; compare within a category.

**Market-cap list — `build_marketcap.py`.** `largemid_pct` needs
`data/amfi_market_cap.csv` (columns `isin,category`, category = large/mid/small). Without
it that criterion is skipped, and the portfolio-quality score is built from the other
criteria (coverage tops out at 75%). Download AMFI's half-yearly "Average Market
Capitalisation of listed companies" categorisation list from amfiindia.com (Excel, CSV
or PDF), then:

```bash
python build_marketcap.py AMFI_list.xlsx
python build_marketcap.py AMFI_list.pdf -o data/amfi_market_cap.csv
```

It does not guess: rows without a valid ISIN or a clear Large/Mid/Small label are skipped
and counted, and it warns if the result does not look like AMFI's list (top 100 companies
large, next 150 mid, the rest small). Exit status 1 if nothing usable is found, 2 for an
unreadable file type.

**Where the holdings files come from.** Drop `.xls/.xlsx` (or `.zip` of them)
anywhere under `data/holdings/`; every sheet that looks like a SEBI-style
portfolio statement is parsed and matched to funds by scheme name. For the AMCs
that cannot be automated, download the files in your browser, then:

```bash
python holdings_import.py ~/Downloads/*.xls* ~/Downloads/*.zip   # sort into data/holdings/<amc>/ and check
python holdings_import.py --check                                # parse everything already there and report
python portfolio_quality.py data/holdings                        # lower-level debug listing
```

`holdings_import.py` finds which AMC each file belongs to (from the title rows or the file
name), copies it to `data/holdings/<amc>/` (or `unsorted/` and says so), and reports how
many portfolio sheets parsed and scored, so a bad download is caught straight away. Files
are only copied, never modified, and importing the same file twice does not duplicate it.

Automation per AMC is limited (`amc_registry.py`, `python holdings_fetch.py --list`):

| Mode                 | AMCs | Meaning |
|----------------------|------|---------|
| `auto` (3)           | Nippon India, DSP, Baroda BNP Paribas | `holdings_fetch.py` scrapes the page for the file link. **Not tested against live downloads** (`python live_check.py --holdings` tries it) |
| `manual` (12)        | SBI, HDFC, Aditya Birla Sun Life, Axis, Mirae, Tata, Motilal Oswal, LIC, Mahindra Manulife, Samco, Abakkus, JioBlackRock | Official page found, but the file list is script-rendered/filtered; download in a browser and use `holdings_import.py` |
| `manual_unconfirmed` (3) | ICICI Prudential, UTI, Invesco | Candidate page only |
| `gated` (2)          | Edelweiss, PPFAS | Behind a folio/PAN/citizenship form with restrictions on reuse — deliberately **not** automated |
| `not_found` (12)     | Kotak, Bandhan, Canara Robeco, Franklin Templeton, HSBC, Quant, Bank of India, WhiteOak, 360 ONE, Groww, Bajaj Finserv, AlphaGrep | No official monthly-portfolio page located |

AMC sites change; if a scraper finds no matching link it says so rather than
guessing. Funds from AMCs not in this registry (e.g. IDBI, ITI, Union,
Sundaram, PGIM India) simply have no portfolio score.

## 3. Extracting your holdings from a CDSL CAS PDF

`cdsl_holdings_to_xls.py` is a standalone script (it does not use the other
modules or `config.py`). It reads a CDSL Consolidated Account Statement PDF and
writes **two Excel files** next to the PDF:

| Output file | Contents |
|---|---|
| `<input-file-name>_holdings.xls` | Every stock / ETF in the demat "HOLDING STATEMENT" tables |
| `<input-file-name>-MF.XLS` | Every mutual fund in the "MUTUAL FUND UNITS HELD AS ON ..." table |

For `Kiran_2026-06.pdf` that gives `Kiran_2026-06_holdings.xls` and
`Kiran_2026-06-MF.XLS`. NPS sections are ignored. It reports what is printed in
the statement; it does not fetch prices or give advice.

```bash
pip install pdfplumber xlwt                       # xlwt only for .xls output
python cdsl_holdings_to_xls.py Kiran_2026-06.pdf
python cdsl_holdings_to_xls.py Kiran_2026-06.pdf -o my_holdings.xls     # -> my_holdings.xls + my_holdings-MF.xls
python cdsl_holdings_to_xls.py Kiran_2026-06.pdf --mf-output funds.xlsx
python cdsl_holdings_to_xls.py Kiran_2026-06.pdf --skip-mf              # stocks only
python cdsl_holdings_to_xls.py cas.pdf --password ABCDE1234F            # CDSL password = PAN in capitals
python cdsl_holdings_to_xls.py cas.pdf --pages 17-29 --force-ocr
```

| Flag | Default | Meaning |
|---|---|---|
| `-o`, `--output` | `<pdf name>_holdings.xls` | Stock file (`.xls` or `.xlsx`) |
| `--mf-output` | `<pdf name>-MF.XLS`, or `<-o name>-MF.<ext>` when `-o` is given | Mutual fund file (`.xls` or `.xlsx`) |
| `--skip-mf` | off | Stocks only |
| `--password` | — | PDF password |
| `--pages` | all | Restrict the scan, e.g. `17-29` |
| `--dpi`, `--workers` | 300, 4 | OCR render resolution and parallelism |
| `--force-ocr` | off | Ignore any text layer and OCR the page images |
| `--tesseract-cmd` | — | Full path to the tesseract executable (Windows) |

**Stock file** — sheet *Holdings*: ISIN, Security, Current Bal, Frozen Bal,
Pledge Bal, Pledge Setup Bal, Free Bal, Market Price / Face Value, Value (Rs),
Demat Account (DP), PDF Page, Check, and a TOTAL row. Sheet *Reconciliation*
compares each demat account's sum with the "Portfolio Value" printed in the
statement.

**Mutual fund file** — sheet *Mutual Funds*, one row per scheme and folio:
Scheme Name (as printed, including the leading scheme code), ISIN, Folio No.,
Closing Bal (Units), NAV (Rs), Cumulative Amount Invested (INR), Valuation (Rs),
Unrealised Profit/Loss, Unrealised Profit/Loss (%), PDF Page, Check, and a TOTAL
row. Sheet *Reconciliation* compares the sum of invested and valuation with the
statement's "Grand Total" row.

**Accuracy safeguards**

- Every ISIN is validated with its check digit. Look-alike characters
  (O/0, I/1/L, S/5, B/8 …) are corrected only if the check digit then passes;
  if several corrections fit equally well the ISIN is kept as read and flagged.
- Stock rows: Current Bal × Price = Value. Mutual fund rows: Units × NAV =
  Valuation, Valuation − Invested = Profit/Loss, Profit/Loss ÷ Invested =
  Profit/Loss %.
- Rows that fail a check, or whose ISIN was corrected, are marked in the
  *Check* column and shaded yellow; the console lists them too.

Tested on one statement with a text layer (`Kiran_2026-06.pdf`): 48 stock rows
and 75 mutual fund rows, with all totals matching the statement.

**Limitations**

- Scanned PDFs (no text layer) are read with OCR (needs `pytesseract` and the
  Tesseract program). Numbers read well, but ISINs and folio numbers are
  noticeably less reliable — check every flagged row.
- A scanner's text layer can contain misread characters that are copied through
  (e.g. a scheme code `162` came out as `16Z`). Scheme names are not
  spell-checked.
- A printed ISIN can itself fail the check digit; it is then kept as printed and
  flagged.
- Mutual funds held *in demat form* appear in the stock file; the MF file covers
  only the folio-based table.
- Column positions are measured from the current CDSL CAS layout; if CDSL changes
  it, the layout constants near the top of the script need adjusting.

## 4. Screening the funds you already hold

`mf_holdings_screener.py` takes the `-MF.XLS` file from section 3 and, for every
fund in it, says whether the numbers support **continuing to hold** it. It writes
a copy of your file with extra columns (`<input name>-Screened.XLS`).

```bash
python mf_holdings_screener.py Kiran_2026-06-MF.XLS
python mf_holdings_screener.py Kiran_2026-06-MF.XLS -o my_review.xls
python mf_holdings_screener.py Kiran_2026-06-MF.XLS --no-peers            # faster, no peer ranking
python mf_holdings_screener.py Kiran_2026-06-MF.XLS --navall NAVAll.txt   # AMFI file saved by you
python mf_holdings_screener.py Kiran_2026-06-MF.XLS --refresh             # ignore cached NAV data
```

Run it in the toolkit folder, on a computer with internet access (it needs
mfapi.in for NAV history and AMFI's `NAVAll.txt` for ISIN → scheme code; if the
AMFI download is blocked, save that file in a browser and pass `--navall`). The
first run downloads NAV history for your funds **and** every Direct-Growth peer in
their categories (a few hundred small downloads, cached for a day under `data/`).

**What it does for each holding**

1. Maps the ISIN to an AMFI scheme code and category (by scheme name, flagged
   "verify", if the ISIN isn't found).
2. Computes the usual metrics from NAV history: 1/3/5-year CAGR, volatility, max
   drawdown, Sortino, rolling 3-year consistency, SIP XIRR (`metrics.py`).
3. Compares with the category benchmark: 3-year excess return and the share of
   rolling 3-year windows the fund beat it (`benchmark.py`, same proxy caveat as above).
4. Ranks it against all Direct-Growth peers of the same AMFI category with at
   least 3 years of history, using `shortlist.py`'s scoring engine and the weights
   in `weights.ini` (hard filters are *not* applied, so you see where it really
   stands). Metrics the screener does not compute — portfolio quality, downside
   capture, quartile consistency — are left out and, under the default policy, the
   other weights are rescaled. A peer (or one of your funds) whose measured weight is
   below the coverage floor is **not ranked**: it gets no peer rank, the verdict says
   so, and the other evidence still counts.
5. Turns the evidence into flags and a verdict, and adds portfolio notes.

**Verdicts**

| Verdict | Meaning |
|---|---|
| `CONTINUE` | No red flag, and at most one amber |
| `CONTINUE - WATCH` | Red in one evidence type, or amber in two |
| `REVIEW` | Red in two or more evidence types, or red plus two ambers, or a closed/stale scheme (last NAV too old, or valuation Rs 0) |
| `INSUFFICIENT DATA` | ISIN not mapped, NAV not available, or under 3 years of history |

The three **evidence types** are absolute return (3-year CAGR below the risk-free
rate), benchmark (3-year excess return, rolling beat-rate) and peers (rank
percentile, drawdown vs peers). The verdict counts types, not individual flags, so
two flags that measure the same gap never count twice. A **Confidence** column
says how much evidence there was: High (benchmark + peers), Medium (one), Low
(absolute only - index funds, fund-of-funds, thematic and debt funds have no
like-for-like peer group here).

**Added columns** (after your original ones): Verdict, Confidence, Why (summary),
Red flags, Amber flags, Positives, Portfolio Notes, Data Notes, Portfolio Weight %,
AMFI category / scheme code / matched name / match method, 1Y/3Y/5Y CAGR,
volatility, max drawdown, Sortino, rolling 3Y positive %, SIP XIRR, benchmark and
excess return, rolling beat %, peer group size / rank / percentile / medians, NAV
history, last NAV date. The **Summary** sheet lists verdict counts, the REVIEW and
WATCH funds by size, and your category concentration; the **Method** sheet lists
every rule and threshold used in that run, including the weights file and version.

**Portfolio notes** (informational; they do not change the verdict): one fund
above 15% of your mutual fund money, three or more of your funds in one category
(with which of them ranks best by peer rank), the same fund held in several
folios, a Regular-plan ISIN, an IDCW option.

**Tuning.** All thresholds are in `REVIEW_RULES` at the top of
`mf_holdings_screener.py` (not in `config.py`); `PEER_CATEGORY_KEYWORDS` lists the
categories treated as fair peer groups. The risk-free rate, SIP and rolling-window
settings, benchmark map and score weights come from `config.py` / `weights.ini`.

**Limits - please read.** This is a rules-based screen of *past* NAV data, not
advice. It does not know your goals, holding period, tax position or exit load, and
selling can trigger tax and exit load - check current rules before acting on a
verdict. Expense ratio, fund-manager changes, AUM and portfolio holdings are not
used. For index funds the things that matter (tracking error, expense ratio) are
not in NAV data. Percentile is relative to the funds in the same AMFI category, not
an absolute measure of quality. Verdicts are only as good as the data: check
rows whose Match Method says "Name match" and any `Check` flags carried over from
the CAS extraction.

## Tests

```bash
python test_scoring.py                # 94 checks: weights.ini, scoring engine, extra metrics, data checks, filters, build_marketcap, import_tri
python test_pipeline.py               # 51 checks: shortlist.py end to end (CLI, multi-category, filters, outputs, exit codes) and holdings_import
python test_screener_peers.py         # 17 checks: peer ranking when some funds are left unranked
python test_metrics_window.py         # 18 checks: the aligned 3-year ratio window and the relaxed default filters
python test_benchmark.py
python test_portfolio_quality.py
python test_mf_holdings_screener.py
```

All run offline on synthetic data (the portfolio test builds SEBI-style
workbooks, including fraction-style weights, a zip, stale and malformed files).
They check the logic; they have **not** been run against real AMC files or the live
mfapi.in / AMFI services. `test_pipeline.py` replaces the data layer (scheme list,
NAV download, benchmark, holdings) with a simulation, so it proves the plumbing
and the outputs, not the live integrations. `test_mf_holdings_screener.py` uses
synthetic NAV series and a synthetic AMFI file; it checks the ISIN/name mapping, the
verdict rules, the peer ranking and the output file, and says nothing about real
funds. `cdsl_holdings_to_xls.py` has no automated tests; it was checked by running it
on one real statement and reconciling against the printed totals.

## Things not yet proven against live services

These have only ever run on synthetic data. Run `python live_check.py` once on a
computer with internet access (add `--holdings` to try the AMC downloaders); it prints
PASS / WARN / FAIL per step and exits non-zero on a failure:

- mfapi.in scheme master, category lookup and NAV download
- the benchmark proxy search for every category in `config.BENCHMARKS`
- AMFI's `NAVAll.txt` (used by `mf_holdings_screener.py`)
- the three `auto` AMC portfolio downloaders
- `holdings_import.py` and `build_marketcap.py` on real files
- `shortlist.py`, `mf_holdings_screener.py` and `cdsl_holdings_to_xls.py` on a real first run — check the
  first real output (benchmark names, Match Method, Peer Group Size, `data_flags`) before trusting it

**First live check (Oct 2026):** mfapi.in, category lookup, NAV download and all benchmark proxies
worked. Two warnings: the *large & mid cap* proxy has only ~4.9 years of history and the *multi cap*
proxy ~2.2 years, so multi-cap funds get no benchmark metrics (a 3-year window does not fit) until you
supply a TRI csv with `import_tri.py`. AMFI's NAVAll.txt had changed: Plan and Option are now separate
columns, which `parse_navall` now reads from the header row (`navall_diag.py` shows how a file is parsed).

## Mapping to `mutual_fund_scoring_specification.md`

| Spec item | Status |
|---|---|
| 1. 3-year return | ✅ `cagr_3y` |
| 2. 5-year return | ✅ `cagr_5y` |
| 3. Rolling consistency vs benchmark | ✅ `rolling_beat_benchmark_pct` (benchmark = index-fund proxy unless you supply a TRI csv with `import_tri.py`) |
| 4. Benchmark excess return | ✅ `benchmark_excess_return` (same caveat) |
| 5. Risk-adjusted return | ✅ Sharpe-style ratio + Sortino, as two separate weights (computed from 3y CAGR and monthly volatility, not from a full monthly excess-return series) |
| 6. Maximum drawdown | ✅ `max_drawdown` |
| 7. Expense ratio | ⛔ not implemented (excluded on request) |
| 8. Portfolio quality | ✅ needs holdings files (see above); missing for funds without one |
| External weights file, validated, version recorded | ✅ `weights.ini` (INI instead of JSON), `--weights` option |
| Percentile scoring | ✅ `scoring_method = percentile` (default stays `zscore`); `final_score_0_100` is always percentile-based |
| Renormalise over available metrics + minimum coverage + `INSUFFICIENT_DATA` | ✅ `missing_data_policy`, `minimum_coverage_percent` |
| Low-confidence flag for small groups | ✅ `min_group_size` |
| Stale / duplicate / inconsistent / non-comparable data flags, as-of dates | ✅ `data_checks.py`, `--as-of-date` |
| Categories ranked separately; labelled exploratory cross-category list | ✅ `--category`, `--all-categories` |
| `ranked_funds.csv`-style output | ✅ `shortlisted_funds.csv` (the toolkit's existing name) with per-metric raw value, score, points |
| `ranked_funds.md`, run log | ✅ `ranked_funds.md`, `run_log.txt` |
| Non-zero exit on fatal errors | ✅ 1 = nothing ranked, 2 = bad input/config |
| Automated tests for the scoring engine | ✅ `test_scoring.py`, `test_pipeline.py` |

**Not done from the spec:** the spec's CSV-input command line (`rank_funds.py --input funds.csv`
with pre-computed metric values) — the toolkit computes metrics from NAV history itself;
`scoring.py` has no network or config dependency, so it can be driven from such a file if you
want one. A single blended `risk_adjusted_return` parameter (Sharpe/Sortino average) — they are
two weights here.

**From the older blueprint document** (`mutual_fund_agent_architecture_prompting_blueprint.md`):
downside capture and quartile consistency are implemented (off by default); AUM, manager-tenure,
turnover, cash and top-10 filters are implemented but need your own `data/fund_attributes.csv`
and are off by default; per-fund written summaries are rule-based text in `ranked_funds.md`
(no LLM call); expense ratio is excluded on request.

## Notes & caveats

- This is a screening tool, not investment advice — check exit loads, expense
  ratios, fund manager tenure, portfolio overlap and your own risk profile
  before investing.
- Past returns (which is mostly what this measures) don't guarantee future
  performance. Short horizons (1–3 years) carry substantial equity risk.
- Percentile and z-scores are relative to the funds in the run, not an absolute
  measure of quality or safety.
- mfapi.in is free/community-run; if it's unavailable, cached data under
  `data/` still lets you re-run `shortlist.py` without `--refresh`.
