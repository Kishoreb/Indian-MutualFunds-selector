# Entry-point reference

Audience: someone who needs to run one of the 15 scripts and wants to know the exact command, what it reads, what it writes, when it stops, and what the exit codes mean.

Evidence: 15 of 15 entry points read · 8 capabilities · 15 open unknowns · commit ef2fb5a · Surveyor 2.2.0 · 2026-10-24

Every entry point is a Python CLI script run as `python <script>.py`. There is no web server, no scheduler and no shared API. Parameters come from `argparse` unless noted otherwise.

---

## E001 shortlist.py (C01, High)

Shortlist and rank mutual funds in one or more categories.

### Command

```
python shortlist.py --category "small cap"
python shortlist.py --category "small cap" --category "mid cap"
python shortlist.py --all-categories
python shortlist.py funds.csv --output-dir out_smallcap
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional or `--category` | one of these | none | A category name (repeat `--category` for several), `--all-categories`, or a CSV path with a `scheme_code` column [S01/F001] |
| `--all-categories` | no | off | Rank every known category and produce an exploratory cross-category list [S01/F001] |
| `--output-dir` | no | `.` (current folder) | Folder for the four output files [S01/F001] |
| `--weights` | no | `weights.ini` | Path to a scoring weights file [S03/F001] |
| `--rolling-years` | no | `config.ROLLING_WINDOW_YEARS` (3) | Window for rolling-return metrics [S01/F001] |
| `--as-of-date` | no | today | Reference date for metrics [S01/F001] |
| `--top-n` | no | 15 | Number of funds to show in the ranking table [S04/F001] |
| `--refresh` | no | off | Force re-download of NAV history [S01/F001] |
| `--fetch-holdings` | no | off | Download portfolio files as part of the run [S01/F001] |

### Inputs

- AMFI scheme master from mfapi.in, cached in `data/_scheme_master.json` for 7 days [S01/F001].
- NAV history per candidate from mfapi.in, cached in `data/<code>.csv` for 1 day [S02/F001].
- Benchmark: local TRI CSV in `data/benchmarks/<category>.csv`, or pinned code, or auto-discovered index-fund proxy [S02/F001].
- Optional fund attributes CSV from `data/fund_attributes.csv` for AUM, tenure, turnover and cash filters [S01/F001].
- `weights.ini` for scoring policy and weights [S03/F001].

### Outputs

- `shortlisted_funds.csv` (82 columns, one row per ranked fund) [S14/F001].
- `shortlisted_funds.xlsx` (same data with formatting and colour scale) [S04/F001].
- `ranked_funds.md` (method, weights, ranking table, per-fund breakdowns, disclaimers) [S04/F001].
- `run_log.txt` (timestamps, exclusions, filter reasons, counts) [S04/F001].
- `shortlisted_exploratory.csv` when more than one category is ranked [S01/F001].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 0 | At least one fund was ranked | [S01/F001] |
| 1 | No fund could be ranked in any category | [S01/F001] |
| 2 | Bad weights file, bad `--rolling-years`, bad `--as-of-date`, missing CSV, unrecognised category, or no category given | [S01/F001] |

### Security

Uses only public web sources (mfapi.in) and local files. No credentials. The output contains fund names, scheme codes and public metric values [S01/F001].

---

## E002 rank_funds.py (C04, Medium)

Rank funds from a user-supplied metrics CSV, with no internet access.

### Command

```
python rank_funds.py --input metrics.csv
python rank_funds.py --input metrics.csv --units spec --category "small cap" --exploratory
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `--input` | yes | none | CSV with one row per fund [S08/F002] |
| `--weights` | no | `weights.ini` | Scoring weights file [S08/F002] |
| `--output-dir` | no | `output` | Output folder [S08/F002] |
| `--units` | no | `auto` | Column style: `auto`, `spec` (percents) or `toolkit` (fractions) [S08/F002] |
| `--category` | no | all in file | Restrict to one or more categories [S08/F002] |
| `--as-of-date` | no | none | Reference date; rows with dates after this are excluded [S08/F002] |
| `--include-all-plans` | no | off | Keep non-Direct-Growth rows [S08/F002] |
| `--ignore-category` | no | off | Rank all funds together, ignoring category [S08/F002] |
| `--exploratory` | no | off | Add a cross-category ranking [S08/F002] |
| `--top-n` | no | 15 | Funds shown in the Markdown table [S08/F002] |

### Inputs

- A CSV file in "spec style" (percent numbers: `return_3y`, `benchmark_excess_return`, etc.) or "toolkit style" (fractions: `cagr_3y`, `rolling_beat_benchmark_pct`, etc.), auto-detected from column names [S08/F002].
- `weights.ini` (default or `--weights`) [S08/F002].

### Outputs

- `ranked_funds.csv` (ranked funds with scores, flags and input values) [S08/F002].
- `ranked_funds.md` (Markdown report with top-n per category) [S08/F002].
- `run_log.txt` (decisions, warnings, excluded funds) [S08/F002].
- `ranked_funds_exploratory.csv` with `--exploratory` [S08/F002].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 0 | Ranking complete | [S08/F002] |
| 1 | Nothing could be ranked | [S08/F002] |
| 2 | Bad command line, weights file or input file (10+ specific `InputError` cases: file not found, empty, no fund name column, duplicate header, no metric columns, mixed styles with ambiguous `benchmark_excess_return`, no Direct-Growth rows, none of the weighted metrics in the file) | [S08/F002] |

### Security

No network access. Reads and writes local files only [S08/F002].

---

## E003 check_fund.py (C03, High)

Report on one mutual fund: metrics, peer ranking, screen verdict.

### Command

```
python check_fund.py "Axis Small Cap"
python check_fund.py 125354 --no-peers --format md
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | yes | none | Fund name (words) or AMFI scheme code [S07/F003] |
| `--navall` | no | download or cache | Path to a saved AMFI `NAVAll.txt` [S07/F003] |
| `--no-peers` | no | off | Skip category peer comparison (benchmark and absolute only) [S07/F003] |
| `--refresh` | no | off | Force re-download of NAV history [S07/F003] |
| `--weights` | no | `weights.ini` | Alternative weights file [S07/F003] |
| `--rolling-years` | no | `config.ROLLING_WINDOW_YEARS` | Rolling-return window [S07/F003] |
| `--workers` | no | 4 | Parallel NAV download threads [S07/F003] |
| `--output-dir` | no | `output` | Output folder [S07/F003] |
| `--no-file` | no | off | Print to stdout only, do not write a file [S07/F003] |
| `--format` | no | `docx` | Output format: `docx` or `md` [S07/F003] |

### Inputs

- AMFI `NAVAll.txt` (downloaded, cached, or from `--navall`) for fund lookup [S07/F003].
- NAV history for the target and its peers from mfapi.in [S07/F003].
- Benchmark via `BenchmarkProvider` [S07/F003].
- `weights.ini` for the scoring engine [S07/F003].

### Outputs

- Markdown report printed to stdout: fund identity, screen verdict (CONTINUE / WATCH / REVIEW / INSUFFICIENT DATA), 16-metric comparison table (fund value, peer median, "better than x% of peers", weight), benchmark used, shortlist filter result, top 5 in category, disclaimers [S07/F003].
- File: `<output-dir>/fund_check_<code>.docx` (default) or `.md` [S07/F003].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 0 | Report written | [S07/F003] |
| 1 | Fund found but NAV data could not be fetched (INSUFFICIENT DATA verdict) | [S07/F003] |
| 2 | Bad command line, bad weights file, fund not found, ambiguous match, AMFI file unavailable | [S07/F003] |

### Security

Downloads public NAV data from mfapi.in. No personal data in the output [S07/F003].

---

## E004 backtest.py (C07, Medium)

Back-test whether forward signals predict future returns. This script cannot run at the recorded commit: it calls `benchmark.resolve_benchmark` (does not exist in `benchmark.py`) and references config settings (`BACKTEST_*`, `FORWARD_*`) that `config.py` does not define [S12/F004, U26].

### Command

```
python backtest.py "mid cap"
python backtest.py "small cap" --horizon 1 3 --step-months 3 --window 3
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | yes | none | Category name or CSV path [S12/F004] |
| `--horizon` | no | undefined (in missing config) | Forward-return years to test [S12/F004] |
| `--step-months` | no | undefined | Months between as-of dates [S12/F004] |
| `--window` | no | undefined | History window per as-of date [S12/F004] |
| `--benchmark` | no | auto | Benchmark override [S12/F004] |
| `--refresh` | no | off | Re-download NAV data [S12/F004] |

### Inputs

- NAV history for all eligible funds from mfapi.in [S12/F004].
- Benchmark via `benchmark.resolve_benchmark` (missing function) [S12/F004].
- Config settings `BACKTEST_MIN_FUNDS`, `BACKTEST_MIN_MEAN_IC`, `BACKTEST_MIN_POSITIVE_SHARE`, `BACKTEST_MIN_DATES`, etc. (not defined in `config.py`) [S12/F004].

### Outputs

- Summary CSV to `config.BACKTEST_CSV` (undefined) [S12/F004].
- Detail CSV (one row per as-of date, horizon, signal) [S12/F004].
- Formatted table with verdicts ("supported", "inverted", "insufficient data") [S12/F004].

### Exit codes

Not defined. Exits early (no crash) for: no query, no candidates, too few funds, or no usable dates [S12/F004].

### Security

Same public mfapi.in data as the rest of the toolkit. No credentials [S12/F004].

### Status

Not runnable at commit ef2fb5a. Missing: `benchmark.resolve_benchmark`, all `BACKTEST_*` and `FORWARD_*` config settings, `MANIFEST_JSON`. See U26.

---

## E005 mf_holdings_screener.py (C02, High)

Screen each fund in the user's holdings file and say whether to keep holding it.

### Command

```
python mf_holdings_screener.py my_holdings.xls
python mf_holdings_screener.py my_holdings.xlsx --no-peers -o my_holdings-Screened.xlsx
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | yes | none | Holdings spreadsheet (.xls or .xlsx) [S05/F005] |
| `-o` | no | `<input>-Screened.<ext>` | Output file path [S05/F005] |
| `--navall` | no | download or cache | Path to a saved AMFI `NAVAll.txt` [S05/F005] |
| `--no-peers` | no | off | Skip peer ranking (absolute and benchmark only) [S05/F005] |
| `--refresh` | no | off | Force re-download of NAV history [S05/F005] |
| `--workers` | no | 4 | Parallel NAV download threads [S05/F005] |

### Inputs

- Holdings file with columns "Scheme Name" and "ISIN" (header row detected by finding "ISIN" in a cell). Optional columns: "Valuation (Rs)" [S05/F005].
- AMFI `NAVAll.txt` from `--navall`, cache (`data/NAVAll.txt`, 1-day TTL), or download from two AMFI URLs [S05/F005].
- NAV history per held scheme and peers from mfapi.in [S05/F005].
- Benchmark per category when `config.BENCHMARK_ENABLED` is true [S05/F005].

### Outputs

One workbook with three sheets [S05/F005]:

1. "Holdings Analysis": every original column plus 33 added columns (Verdict, Confidence, flags, metrics, benchmark, peer figures, total row).
2. "Summary": counts and value by verdict, REVIEW and WATCH funds, value by AMFI category.
3. "Method": every rule and threshold, benchmarks used, peer-group sizes, disclaimer.

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 1 (via `sys.exit(text)`) | No header row with "ISIN", missing required columns, no `NAVAll.txt` available, or `NAVAll.txt` has no scheme rows | [S05/F005] |

Per-fund failures (NAV download, unmapped ISIN) produce INSUFFICIENT DATA in the output row, not a program exit [S05/F005].

### Security

The input holds personal data: folio numbers, units, amounts invested and valuations. The screener copies all input columns into the output file. It sends only scheme codes to mfapi.in and a public-file request to AMFI. The repository tracks `my_review.xls` and `mfReview.xls` at its root; whether they contain personal data is unknown (U19, U28) [S05/F005].

---

## E006 cdsl_holdings_to_xls.py (C02, High)

Extract demat stock holdings and mutual fund holdings from a CDSL CAS PDF into Excel.

### Command

```
python cdsl_holdings_to_xls.py Statement.pdf
python cdsl_holdings_to_xls.py Statement.pdf --password ABCDE1234F --force-ocr --dpi 300
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | yes | none | CDSL CAS PDF path [S06/F006] |
| `-o` | no | `<pdf-stem>_holdings.xls` | Stock holdings output [S06/F006] |
| `--mf-output` | no | `<pdf-stem>-MF.XLS` | Mutual fund holdings output [S06/F006] |
| `--skip-mf` | no | off | Extract stocks only [S06/F006] |
| `--password` | no | none | PDF password (CDSL uses PAN in capitals) [S06/F006] |
| `--pages` | no | all | Restrict scan to specific pages [S06/F006] |
| `--dpi` | no | 300 | Render resolution for OCR [S06/F006] |
| `--force-ocr` | no | off | Use OCR even when a text layer exists [S06/F006] |
| `--workers` | no | 4 | Parallel OCR threads [S06/F006] |
| `--tesseract-cmd` | no | system default | Path to the Tesseract executable [S06/F006] |

### Inputs

- A CDSL Consolidated Account Statement (CAS) PDF. Two sections parsed: the demat "HOLDING STATEMENT" tables and the "MUTUAL FUND UNITS HELD AS ON" table [S06/F006].
- When a page has fewer than 50 characters of text (or `--force-ocr`), it is rendered and OCR'd with Tesseract [S06/F006].

### Outputs

Two Excel files [S06/F006]:

1. `<name>_holdings.xls`: stocks/ETFs with ISIN, Security, balances, Market Price, Value, Demat Account (DP), PDF Page, Check. TOTAL row with SUM formula. Reconciliation sheet per demat account.
2. `<name>-MF.XLS`: mutual funds with Scheme Name, ISIN, Folio No., Units, NAV, Invested, Valuation, Profit/Loss, Profit/Loss %, PDF Page, Check. TOTAL row with SUM formulas. Reconciliation sheet against Grand Total.

Rows failing cross-checks are highlighted yellow [S06/F006].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 1 (via `sys.exit(text)`) | No holding rows found, OCR needed but Tesseract not installed, or output format's writer library not installed | [S06/F006] |

### Security

The CDSL statement contains personal financial data (BO IDs, folio numbers, holdings, market values). All of this is copied into the output. The `--password` argument (typically PAN) is visible on the command line. No data leaves the machine [S06/F006].

---

## E007 holdings_fetch.py (C05, Medium)

Download the newest portfolio files from automated AMC websites.

### Command

```
python holdings_fetch.py
python holdings_fetch.py dsp nippon_india
python holdings_fetch.py --list
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | no | all automated AMCs | Named AMC keys to fetch [S09/F007] |
| `--list` | no | off | Print every AMC, its mode (auto/manual/gated/not_found) and page URL [S09/F007] |

### Inputs

- AMC portfolio-disclosure web pages (3 automated: Nippon India, DSP, Baroda BNP Paribas). The remaining 29 AMCs print a manual checklist [S09/F007].
- `amc_registry.py` defines 32 AMCs with aliases, mode and page URL [S09/F007].

### Outputs

- Excel or zip files saved to `data/holdings/<amc_key>/` [S09/F007].
- Status message per AMC. Manual-checklist URLs for non-automated AMCs [S09/F007].

### Exit codes

None defined. The script's `__main__` block does not return a status [S09/F007].

### Security

Downloads from HTTPS fund-house pages with user-agent `mf-shortlister/1.0`. Does not leak local data. Gated AMCs (requiring folio/PAN) are deliberately not automated [S09/F007].

---

## E008 holdings_import.py (C05, Medium)

Sort downloaded portfolio files into `data/holdings/<amc>/` and report scores.

### Command

```
python holdings_import.py ~/Downloads/*.xls* ~/Downloads/*.zip
python holdings_import.py --check
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | no (if `--check`) | none | Excel or zip files to import [S09/F008] |
| `--check` | no | off | Parse and report what is already under `data/holdings/` [S09/F008] |

### Inputs

- One or more `.xls`, `.xlsx` or `.zip` files on the command line, or the existing `data/holdings/` folder with `--check` [S09/F008].

### Outputs

- Files copied (not moved) to `data/holdings/<amc_key>/` or `data/holdings/unsorted/` [S09/F008].
- Printed report of parsed portfolio sheets and their quality scores [S09/F008].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 0 | Import complete | [S09/F008] |
| 1 | Nothing was imported | [S09/F008] |
| 2 | No files given and no `--check` | [S09/F008] |

### Security

Files are copied, not executed. Zip members are extracted with path-traversal defence (`os.path.basename` on member names), tested in `test_portfolio_quality.py` [S09/F008].

---

## E009 import_tri.py (C06, Medium)

Import a Total Return Index history CSV as a benchmark for a category.

### Command

```
python import_tri.py --category "small cap" nifty_smallcap_250_tri.csv
python import_tri.py --list
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `--category` | yes (unless `--list`) | none | Which benchmark category this history replaces [S11/F009] |
| positional | yes (unless `--list`) | none | One or more CSV files with date and index-value columns [S11/F009] |
| `--list` | no | off | Print categories and their expected indexes [S11/F009] |

### Inputs

- CSV files with a date column and a value column (auto-detected: "close", "tri", "total return", "value", "nav" or "index" in the column name) [S11/F009].

### Outputs

- `data/benchmarks/<category>.csv` with columns `date` (YYYY-MM-DD) and `nav` [S11/F009].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 0 | Import complete | [S11/F009] |
| 1 | Fewer than 250 usable rows after merging | [S11/F009] |
| 2 | Missing `--category`, no input files, unknown category, or unreadable input | [S11/F009] |

Warnings (non-fatal) for gaps greater than 10 days, staleness, and history shorter than 5 years [S11/F009].

### Security

Reads local CSV files and writes to a local directory. No credentials or network access [S11/F009].

---

## E010 build_marketcap.py (C05, Medium)

Build the AMFI large/mid/small company list for the liquidity sub-criterion of portfolio quality.

### Command

```
python build_marketcap.py AMFI_list.xlsx
python build_marketcap.py AMFI_list.pdf -o data/amfi_market_cap.csv
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | yes | none | AMFI categorisation list (`.xlsx`, `.xls`, `.csv` or `.pdf`) [S09/F010] |
| `-o` | no | `config.AMFI_MARKETCAP_CSV` | Output CSV path [S09/F010] |

### Inputs

- AMFI's half-yearly "Average Market Capitalisation" categorisation list, downloaded manually [S09/F010].

### Outputs

- CSV with columns `isin` and `category` (large/mid/small) [S09/F010].
- Printed counts by category and duplicates removed [S09/F010].
- Warnings for suspicious counts (fewer than 500 total, large-cap not 80-130, mid-cap not 120-180) [S09/F010].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 0 | Success | [S09/F010] |
| 1 | No ISIN + category rows found | [S09/F010] |
| 2 | Input file cannot be read or unsupported type | [S09/F010] |

### Security

Public AMFI data in, local CSV out. No personal data [S09/F010].

---

## E011 fetch_nav_data.py (C08, Low)

Download and cache NAV history for one or more scheme codes.

### Command

```
python fetch_nav_data.py 120503 118989 100033
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | yes | none | One or more AMFI scheme codes [S13/F011] |

### Inputs

- mfapi.in JSON API for each scheme code [S13/F011].
- Existing cache in `data/<code>.csv` reused if fresher than 1 day [S13/F011].

### Outputs

- `data/<code>.csv` with columns `date` and `nav` [S13/F011].
- `data/<code>_meta.csv` with scheme name, fund house and category [S13/F011].
- Progress printed per fund with a 0.3-second pause between requests [S13/F011].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 1 | No scheme codes given | [S13/F011] |

Per-fund download failures are caught and warned; the batch continues [S13/F011].

### Security

Unauthenticated HTTPS GET to mfapi.in with a 20-second timeout. No API key [S13/F011].

---

## E012 live_check.py (C08, Low)

First-run diagnostic: checks that the live services the toolkit depends on are reachable.

### Command

```
python live_check.py
python live_check.py --holdings --category "mid cap"
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `--holdings` | no | off | Also test the AMC portfolio downloaders [S13/F012] |
| `--category` | no | `small cap` | Category to use for candidate and NAV checks [S13/F012] |

### Inputs

None on disk. Uses live mfapi.in, AMFI scheme master, benchmark provider, NAVAll.txt, and optionally AMC pages [S13/F012].

### Outputs

PASS / WARN / FAIL per step (6 steps). Changes nothing except the cache under `data/` [S13/F012].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 0 | No step failed | [S13/F012] |
| 1 | Any step failed | [S13/F012] |

Each step is independently guarded: a failure or `SystemExit` is caught and reported, then the next step runs [S13/F012].

### Security

Same unauthenticated HTTPS calls as the toolkit itself. No credentials [S13/F012].

---

## E013 apply_docx_patch.py (C08, Low)

One-time migration script: changes `check_fund.py` from Markdown-only to Word-by-default output.

### Command

```
python apply_docx_patch.py
```

### Parameters

None [S13/F013].

### Inputs

Reads `check_fund.py`, `test_check_fund.py`, `requirements.txt` and `README.md` from the same folder. Checks that `report_docx.py` is present [S13/F013].

### Outputs

Modifies the four files in place. Creates `.bak` backups before changing. Prints OK/SKIP/FAIL per file. Safe to re-run (idempotent) [S13/F013].

### Exit codes

| Code | Meaning | Evidence |
|---|---|---|
| 0 | All patches applied or already present | [S13/F013] |
| 1 | Any file's expected text not found | [S13/F013] |
| 2 | `report_docx.py` not present | [S13/F013] |

### Security

Local file edits only [S13/F013].

---

## E014 navall_diag.py (C08, Low)

Debugging aid: shows why NAVAll.txt parsing found no open-ended Direct-Growth schemes.

### Command

```
python navall_diag.py
python navall_diag.py path/to/NAVAll.txt
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | no | `data/NAVAll.txt` | Path to the AMFI file to diagnose [S13/F014] |

### Inputs

A `NAVAll.txt` file. Imports `mf_holdings_screener` for the parsing function [S13/F014].

### Outputs

Prints to stdout: first 8 non-empty lines, category-header regex matches, unrecognised bracket lines, parsed scheme counts (total, open-ended, Direct-Growth) [S13/F014].

### Exit codes

None defined. A missing file or import error raises an unhandled exception (deliberate for a diagnostic tool) [S13/F014].

### Security

Reads one local file. No network, no credentials [S13/F014].

---

## E015 portfolio_quality.py (C05, Medium)

Debug entry: parse portfolio holdings under a folder and print every sheet's quality score.

### Command

```
python portfolio_quality.py data/holdings
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| positional | no | `config.HOLDINGS_DIR` | Root folder to scan for AMC workbooks [S10/F015] |

### Inputs

- All `.xls`, `.xlsx`, `.xlsm` files under the root folder (recursively). Zips are extracted to `_extracted/` [S10/F015].
- Optional `data/amfi_market_cap.csv` for the large+mid-cap sub-criterion [S10/F015].

### Outputs

Prints every parsed sheet's portfolio-quality score (0-100), coverage and reason when the score is None [S10/F015].

### Exit codes

None defined (the `__main__` block calls `_debug` which prints and returns) [S10/F015].

### Security

Reads AMC-published portfolio files (public disclosure data). No personal data handled [S10/F015].

---

## Entry points not read

None. All 15 entry points in the inventory have been read.

---

## Unknowns and next probes

| ID | Unknown | Relevant entry point | Next probe |
|---|---|---|---|
| U10 | Are the hard-filter defaults the owner's intended settings? | E001 | Ask the product owner |
| U12 | Which index fund is the benchmark proxy today for each category, and do TRI files exist? | E001 | List `data/benchmarks/` and read `run_log.txt` |
| U13 | Does the test suite pass today? Tests expect weights that `weights.ini` no longer has. | E001 | Run the test suite |
| U14 | Are the shipped weights the intended current weights? Comments contradict the values. | E001 | Ask the product owner |
| U17 | Is `manifest.py` used by anything? | E001, E004 | Ask a developer |
| U19 | Do tracked spreadsheets hold personal data, and is the repo pushed to a remote? | E005 | Ask the product owner |
| U20 | Do hardcoded A4 column positions work for all CDSL statement versions? | E006 | Test with several real PDFs |
| U21 | Why are there no tests for a 1,174-line script? | E006 | Ask the product owner |
| U25 | Does `import_tri.py`'s CSV parsing handle all NSE download formats? | E009 | Test with a sample NSE download |
| U26 | Are the missing imports, config settings and `resolve_benchmark` in an unmerged branch? | E004 | Ask a developer or check `git log --all` |
| U27 | Is 0.3s between API calls sufficient, and does caching handle concurrent runs? | E011 | Ask whether rate-limit errors have occurred |
| U28 | Do `my_review.xls` and `mfReview.xls` contain personal financial data? | E005 | Ask the owner to list column headers |
| U11 | Is there any test for CAGR, volatility or SIP XIRR against a known answer? | E001 | Search `test_*.py` for those function names |
| U15 | Does any test exercise the real Excel export or the explain function? | E001 | Search `test_*.py` for `export_to_excel` |
| U16 | Is the Word report conversion tested? | E003 | Search `test_*.py` for `report_docx` |

---

## Related documents

- [01-overview.md](01-overview.md): capabilities table and system context.
- [03-request-to-response-flow.md](03-request-to-response-flow.md): detailed flow diagrams per capability.
- [04-shortlist-and-rank.md](04-shortlist-and-rank.md): the core scoring capability in depth.
- [06-runtime-and-deployment.md](06-runtime-and-deployment.md): stack, versions and configuration (not yet written).
- [08-developer-onboarding.md](08-developer-onboarding.md): how to run the scripts (not yet written).
