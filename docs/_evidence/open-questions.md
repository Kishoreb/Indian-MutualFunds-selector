# Open questions

Questions the code could not answer, grouped by who can answer them. Updated 2026-10-24 (phase 5 complete).

## For a developer

| ID | Question | Why it matters | From | Status |
|---|---|---|---|---|
| U01 (inventory) | Which tests does the owner actually run: pytest, or each test file as a script? Neither a pytest configuration nor a CI file exists. | Decides which of the 24 pytest-style functions and 421 `check(` lines count as running tests. | inventory | open |
| U02 (inventory) | What does `apply_docx_patch.py` do, and is it still used? | Its purpose is not clear from the name; it may be a one-off. | inventory | open |
| U03 (inventory) | Where does the file named by `FUND_ATTRIBUTES_CSV` (`config.py:59`) come from, and does it exist on this machine? It is not among the tracked files. | Fund filters on AUM, manager tenure and turnover depend on it. | inventory | open |
| U04 (inventory) | Which URL does `build_marketcap.py` download the AMFI market-cap list from? | The integration list has no address for it yet. | inventory | open |
| U05 (inventory) | Which Python version is intended? No file declares one; this machine has 3.14.3. | A newcomer needs a version that works. | inventory | open |
| U06 (inventory) | Are `data/` and `out_smallcap/` meant to stay outside git, and can they be rebuilt by the scripts? | Decides what a newcomer must fetch before running anything. | inventory | open |
| U07 (inventory) | Which source modules do `test_pipeline.py` and `test_new_metrics.py` target? The guess in the inventory is not confirmed. | Needed for the test exposure map. | inventory | open |
| U11 (S02) | Is there any test that checks `calculate_cagr`, `calculate_volatility` or `calculate_sip_xirr` against a known answer? | Decides the test result for the core return and risk numbers. | S02 | open |
| U12 (S02) | Which index fund is the benchmark proxy today for each of the 11 categories in `config.BENCHMARKS`, and are TRI files present in `data/benchmarks/`? | Benchmark metrics carry 20% of the shipped weights. | S02 | open |
| U13 (S03) | Does the test suite pass today? At least five assertions in `test_scoring.py`, `test_new_metrics.py` and `test_pipeline.py` expect values the current `weights.ini` no longer has (11 weighted metrics, `cagr_3y` 15, method `zscore`, alpha and beta at 0). Contradiction between tests and `weights.ini`. | A failing suite hides real faults. | S03 | open |
| U15 (S04) | Does any test exercise the real `report.export_to_excel` or `report_md.explain`? | `test_pipeline.py` fakes the Excel export. | S04 | open |
| U17 (S04) | `config.py` defines none of the `BACKTEST_*`, `FORWARD_*` or `MANIFEST_JSON` settings that `backtest.py`, `forward_signals.py` and `test_forward_signals.py` use, and nothing calls `manifest.write_manifest`. Is `config.py` an older copy, and does `backtest.py` run at all? Contradiction between `config.py` and these modules. | Decides whether capability C07 works. | S04 | open |
| U18 (S05) | What happens at a real run when AMFI blocks the `NAVAll.txt` download or changes its layout again? Nothing tests the download path. | The holdings screener cannot start without that file. | S05 | open |

## For the product owner or business

| ID | Question | Why it matters | From | Status |
|---|---|---|---|---|
| U10 (S01) | Are the hard-filter defaults (3-year and 5-year CAGR at least 10%, volatility at most 35%, history at least 5 years) your intended settings? | They decide which funds can appear in a ranking at all. | S01 | open |
| U14 (S03) | Are the shipped weights your intended current weights, including 5 points each on Jensen's alpha and beta? The comments in `weights.ini` still call those two "off by default", and the version number is still 2. | The weights decide the ranking. | S03 | open |
| U29 (doc-diff) | `HoldingToExcel.md` is a frozen copy of an older README that contradicts the current codebase in 10 places (weights location, missing-data policy, scoring method, output files, file table, drawdown window, ratio window, test count, and omits the screener entirely). Should it be removed, updated, or archived? | Someone reading only `HoldingToExcel.md` would have a wrong picture of how scoring, filtering and output work. All 10 contradictions affect High-importance capabilities. | doc-diff | open |

## For operations

| ID | Question | Why it matters | From | Status |
|---|---|---|---|---|

## For security

| ID | Question | Why it matters | From | Status |
|---|---|---|---|---|
| U19 (S05) | Do `my_review.xls` and `mfReview.xls` (tracked in git) hold real folio numbers and valuations, and is the repository pushed to a remote such as GitHub? | The holdings screener's input and output carry folio numbers and values. | S05 | open |

## For a developer (continued from S06-S10)

| ID | Question | Why it matters | From | Status |
|---|---|---|---|---|
| U20 (S06) | Do the hardcoded A4 column x-positions (measured from one CDSL statement layout) work for all CDSL statement versions, or do different versions use different column widths? | A layout change would silently misalign columns, putting numbers in the wrong fields. | S06 | open |
| U21 (S06) | Is there a reason no tests exist for a 1,174-line script with OCR, ISIN repair and numeric cross-checks? | The entire CDSL conversion is untested; any bug in ISIN repair or reconciliation would go unnoticed. | S06 | open |
| U22 (S07) | Does the test suite pass today? `test_check_fund.py` stubs `config.BENCHMARK_ENABLED = False` and `config.PORTFOLIO_QUALITY_ENABLED = False`, so those code paths are not exercised in that test. | If the flags are True in production, bugs in those paths would be invisible to this test. | S07 | open |
| U23 (S09) | Do the three picker regexes (`pick_nippon`, `pick_dsp`, `pick_baroda`) still match the links on the AMC websites today? The code says it has never been tested against live downloads. | A changed AMC page layout would silently break portfolio file downloads. | S09 | open |
| U24 (S10) | How consistent are the industry names across AMC workbooks? The `top_sector_pct` sub-criterion groups by the "Industry / Rating" column. If two AMCs spell the same sector differently, sector concentration is understated. | The sector concentration sub-score would be wrong for funds held across multiple AMCs. | S10 | open |

## For a developer (continued from S11-S14)

| ID | Question | Why it matters | From | Status |
|---|---|---|---|---|
| U25 (S11) | Does `import_tri.py`'s CSV parsing correctly handle all the NSE download formats the owner uses (column names, date formats, encodings)? No test exercises `import_tri.read_series` or `import_tri.main`. | A mismatch would silently drop rows or fail. The benchmark data quality depends on this script. | S11 | open |
| U26 (S12) | Are the missing imports (`_run_end_to_end`, `make_nav`, `bench_returns`, `fund_returns` from `test_pipeline`), the missing config settings (`BACKTEST_*`, `FORWARD_*`, `RISK_WINDOW_YEARS`, `MANIFEST_JSON`, etc.), and the missing function (`benchmark.resolve_benchmark`) in a branch not yet merged, or were they removed? `backtest.py` and `test_forward_signals.py` cannot run at the recorded commit. | Decides whether capability C07 works and whether the forward-signal features (--forward, --make-template) are available. Strengthens U17 from S04. | S12 | open |
| U27 (S13) | Is the 0.3-second sleep between mfapi.in calls sufficient to avoid rate-limiting, and does the cache logic handle concurrent runs? | A rate-limit error would silently drop funds from a category run. | S13 | open |
| U28 (S14) | Do `my_review.xls` and `mfReview.xls` contain real folio numbers, ISIN holdings, or valuations? (Overlaps with U19 from S05.) | These files are tracked in git. If they contain personal financial data and the repo is pushed to a remote, that data is exposed. | S14 | open |

## Answered

| ID | Answer | Source (role, date) | Documents updated |
|---|---|---|---|
| U08 | `my_review.xls` and `mfReview.xls` are the owner's own reviews of the outcome of some runs on some funds. Whether `mf_holdings_screener.py` reads them as input is not yet checked. | product owner, 2026-10-24 | none yet |
| U09 | `out_smallcap/` is a sample run and is to be documented as one. | product owner, 2026-10-24 | none yet |
| U16 | Yes, `report_docx.py` is tested: `test_check_fund.py`'s CLI test writes a `.docx` file and checks it exists, with table-presence and no-raw-markdown assertions when `python-docx` is installed at test time (skipped otherwise). | S07, 2026-10-25 | 09-test-exposure-map.md |
