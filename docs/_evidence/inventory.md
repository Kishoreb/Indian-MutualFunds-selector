# Inventory

Commit ef2fb5a · Surveyor 2.2.0 · 2026-10-24 · Scope: whole repository, `.venv/` excluded (a Python environment, not project code)

Not seeded from a prior analysis. Searches covered the top-level `*.py` files only, because the repository has no subfolders with source code (`git ls-files` lists 57 tracked files, all at the top level; `data/` and `out_smallcap/` are untracked).

## Project type

| Part | Type | Stack and version | Evidence |
|---|---|---|---|
| repository root | batch / CLI scripts (data pipeline that ranks mutual funds) | Python with pandas, numpy, requests, openpyxl. Installed interpreter is 3.14.3 (from `python --version`); no file declares a Python version. | `requirements.txt:1` - `pandas>=2.2` (checked) |

No web server, route or UI framework was found. Evidence is the 15 runnable scripts below and the absence of Flask, FastAPI or Django patterns in the searches (see Counts).

## Counts

| Category | Count | Complete? | Search boundary (patterns and folders) |
|---|---|---|---|
| Entry points | 15 | yes | `__main__`, `sys.argv`, `ArgumentParser(`, `def main(` in `*.py` at the repository root, excluding `test_*.py`. Files with none of these (16 modules) are libraries, listed under "Library modules". |
| Configuration files | 3 | yes | `config.py`, `weights.ini`, `requirements.txt`. Searched for `.env*`, `pyproject.toml`, `setup.cfg`, `pytest.ini`, `tox.ini`, `conftest.py` at the root: none found. |
| External integrations | 3 kinds (see list) | incomplete: only top-level `*.py` searched for `requests.`, `urllib`, `https?://` | 1 NAV API, 1 AMFI file source, 25 AMC disclosure pages (see below) |
| Event consumers and producers | 0 | yes within boundary | Searched `celery`, `kafka`, `queue`, `schedule.`, `apscheduler`, `cron`, `threading`, `asyncio`, `multiprocessing`, `concurrent.futures` in `*.py` at the root. Only hit: `ThreadPoolExecutor` imported in `mf_holdings_screener.py:50` and `cdsl_holdings_to_xls.py:61` (parallel work inside a script, not events). |
| Test files | 11 | yes | `test_*.py` at the repository root |
| Tests | see Tests section | incomplete | Two styles exist (below). No single count is reliable. |
| Disabled tests | 0 | yes within boundary | Searched `skip`, `xfail`, `Skip`, `disabled`, `DISABLED` in `test_*.py` at the root. The 4 matches are test descriptions and variable names, not disabled tests. |
| CI/CD files | 0 | yes within boundary | No `.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml` at the root. `Dockerfile` also absent. |
| Python source size | 10,607 lines in `*.py` at the root | yes | `wc -l *.py` |

## Entry points

Every entry point is a command-line script. Each is started by `python <file>.py`.

| ID | Kind | Name or path | Location |
|---|---|---|---|
| E001 | CLI script | `shortlist.py` | `shortlist.py:469` (`__main__`), `shortlist.py:326` (`main`) |
| E002 | CLI script | `rank_funds.py` | `rank_funds.py:551`, `rank_funds.py:353` |
| E003 | CLI script | `check_fund.py` | `check_fund.py:529`, `check_fund.py:474` |
| E004 | CLI script | `backtest.py` | `backtest.py:304`, `backtest.py:235` |
| E005 | CLI script | `mf_holdings_screener.py` | `mf_holdings_screener.py:976`, `mf_holdings_screener.py:939` |
| E006 | CLI script | `cdsl_holdings_to_xls.py` | `cdsl_holdings_to_xls.py:1172`, `cdsl_holdings_to_xls.py:1106` |
| E007 | CLI script | `holdings_fetch.py` | `holdings_fetch.py:176` |
| E008 | CLI script | `holdings_import.py` | `holdings_import.py:119`, `holdings_import.py:103` |
| E009 | CLI script | `import_tri.py` | `import_tri.py:109`, `import_tri.py:51` |
| E010 | CLI script | `build_marketcap.py` | `build_marketcap.py:130`, `build_marketcap.py:100` |
| E011 | CLI script | `fetch_nav_data.py` | `fetch_nav_data.py:109` |
| E012 | CLI script | `live_check.py` | `live_check.py:174`, `live_check.py:150` |
| E013 | CLI script | `apply_docx_patch.py` | `apply_docx_patch.py:146`, `apply_docx_patch.py:134` |
| E014 | diagnostic script | `navall_diag.py` (no `__main__` guard; runs at import) | `navall_diag.py:8` |
| E015 | debug entry | `portfolio_quality.py` (also a library; `__main__` calls `_debug`) | `portfolio_quality.py:389` |

## Library modules (no entry point found)

`amc_registry.py`, `benchmark.py`, `config.py`, `data_checks.py`, `extra_metrics.py`, `forward_signals.py`, `fund_filters.py`, `fund_universe.py`, `logutil.py`, `manifest.py`, `metrics.py`, `report.py`, `report_docx.py`, `report_md.py`, `scoring.py`, `weights_loader.py`. These were identified by name and by the absence of the entry-point patterns. Their code has not been read.

## Configuration

| File | Purpose | Keys of note (names only) |
|---|---|---|
| `config.py` | Python constants: data location, fund filters, metric windows, benchmark and portfolio-quality switches, output paths | `DATA_DIR`, `REQUIRE_DIRECT_PLAN`, `REQUIRE_GROWTH_PLAN`, `RISK_FREE_RATE`, `MIN_HISTORY_YEARS`, `ROLLING_WINDOW_YEARS`, `BENCHMARK_ENABLED`, `PORTFOLIO_QUALITY_ENABLED`, `FUND_ATTRIBUTES_CSV`, `WEIGHTS_FILE`, `TOP_N`, `OUTPUT_DIR` (about 60 constants in total, `config.py:17-193`) |
| `weights.ini` | Score weights and scoring policy for `shortlist.py` | `[meta]` `version`, `missing_data_policy`, `minimum_coverage_percent`, `scoring_method`, `min_group_size`; `[weights_percent]` per metric |
| `requirements.txt` | Third-party packages | `pandas`, `numpy`, `requests`, `openpyxl`, `xlrd`, `pdfplumber`, `xlwt`, `python-docx` (`pytesseract` commented out) |

## External integrations

| ID | System | Kind (database, queue, service, file) | Where it is configured |
|---|---|---|---|
| I001 | mfapi.in (scheme list and NAV history) | web service | `config.py:17` `MFAPI_BASE_URL`; `fund_universe.py:29` `ALL_SCHEMES_URL` |
| I002 | AMFI `NAVAll.txt` | web file | `mf_holdings_screener.py:90-91` (two URLs); `navall_diag.py` reads a local copy |
| I003 | AMFI market-cap categorisation list | web file, via `build_marketcap.py` | URL not located; `build_marketcap.py:101` describes it. Next probe: read `build_marketcap.py`. |
| I004 | 25 AMC portfolio-disclosure web pages (Nippon India, DSP, Baroda BNP Paribas, SBI, HDFC, Aditya Birla, Axis, Mirae, Tata, Motilal Oswal, LIC, Mahindra Manulife, Samco, Abakkus, Jio BlackRock, ICICI Pru, UTI, Invesco, Edelweiss, PPFAS, Kotak, Groww, Bajaj, Alphagrep and others) | web pages | `amc_registry.py:30-121`; fetched in `holdings_fetch.py:110,124` |
| I005 | CDSL CAS statement (PDF supplied by the user) | local file | `cdsl_holdings_to_xls.py` (input via command line; format not yet read) |
| I006 | Tesseract OCR program | local program, optional | `cdsl_holdings_to_xls.py:40`, `requirements.txt` (commented) |
| I007 | Local data folder | files | `data/`: 60 NAV CSVs, 60 `_meta.csv` files, 1 `_scheme_master.json` (121 files, untracked by git) |
| I008 | TRI (benchmark index) history files supplied by the user | local files | `import_tri.py`, `config.py:111` `BENCHMARK_DIR` |

The integrations list comes from `requests.` and URL searches in `*.py` at the root. Other libraries such as `urllib`, `httpx` and `sqlite3` returned no hits that were opened. The count is therefore `incomplete`.

## Tests

Two styles are in use, so the tests cannot be counted with one pattern.

| Test file | Tests | Disabled | Appears to target |
|---|---|---|---|
| `test_forward_signals.py` | 18 `def test_` functions | none found | `forward_signals.py` |
| `test_mf_holdings_screener.py` | 6 `def test_` functions, plus 55 `check(` lines | none found | `mf_holdings_screener.py` |
| `test_scoring.py` | 95 `check(` lines | none found | `scoring.py`, `weights_loader.py` |
| `test_pipeline.py` | 48 `check(` lines | none found | pipeline scripts (`shortlist.py`, `holdings_*`; not confirmed) |
| `test_portfolio_quality.py` | 52 `check(` lines | none found | `portfolio_quality.py` |
| `test_check_fund.py` | 46 `check(` lines | none found | `check_fund.py` |
| `test_benchmark.py` | 41 `check(` lines | none found | `benchmark.py` |
| `test_rank_funds.py` | 25 `check(` lines | none found | `rank_funds.py` |
| `test_new_metrics.py` | 24 `check(` lines | none found | `extra_metrics.py` or `metrics.py` (not confirmed) |
| `test_metrics_window.py` | 18 `check(` lines | none found | `metrics.py` |
| `test_screener_peers.py` | 17 `check(` lines | none found | `mf_holdings_screener.py` (peer logic) |

Totals: 24 pytest-style test functions, 421 `check(` lines in 10 files. A `check(` line may run several times in a loop, and a test file may stop at its first crash, so 421 is a count of assertion lines, not of executed tests. Which files pytest would collect is `unknown`: no pytest configuration exists, and `.pytest_cache/` is present, so pytest was run at least once on this machine.

## Needs a human look

| Marker | Times used | Declared in this repository? | Example location |
|---|---|---|---|
| `check(name, cond)` helper (a homegrown assertion that prints pass or fail) | defined in 9 test files | yes, each file defines its own copy | `test_scoring.py:26`, `test_rank_funds.py:15` |
| `weights.ini` read by `weights_loader.py` (custom scoring policy file) | 1 | yes | `weights.ini:1` |
| `FUND_ATTRIBUTES_CSV` (a fund attributes file such as AUM, manager tenure, turnover) | referenced in `config.py:59` | file not found in tracked files | `config.py:59` |
| `apply_docx_patch.py` (purpose not clear from its name) | 1 | yes | `apply_docx_patch.py:134` |
| `out_smallcap/` (output folder of a small-cap run, untracked) | 1 | not tracked by git | `out_smallcap/` |
| `my_review.xls`, `mfReview.xls` (spreadsheets at the root; `my_review.xls` is modified in git status) | 2 | tracked | root |

## Surprising zeros

- No web framework, routes, scheduler, CI or container files. Expected for a local script toolkit. Searched: root-level `*.py` for `__main__`, `argparse`; root for `.github/`, `Dockerfile`, `pyproject.toml`.
- No Python version is declared anywhere searched. The version above is the one installed on this machine.
