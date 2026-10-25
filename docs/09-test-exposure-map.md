# Test exposure map

Audience: a developer or test lead who needs to know, for each capability and flow, which tests exist, what they actually check, and whether that is enough to trust a change.
Evidence: 15 of 15 entry points read · 15 of 15 flows read · 8 capabilities · 11 open unknowns · commit ef2fb5a · Surveyor 2.2.0 · 2026-10-25

Every one of the 15 flows was read in full during phase 4 [run-log.md, phase 4]. None of the test results below is `scan only, not read`. Test result states follow the vocabulary in the Surveyor rules: `well tested`, `tested on the surface`, `not tested`, `switched off`, `unknown`, or `scan only, not read`.

Across the repository, 11 test files hold two styles: 24 pytest-style `def test_` functions (18 in `test_forward_signals.py`, 6 in `test_mf_holdings_screener.py`) and 421 `check(name, cond)` assertion lines spread across 10 files [inventory, 02-module-architecture.md]. A `check()` line can run more than once inside a loop, and a file can stop at its first crash, so 421 counts assertion lines, not executed tests [inventory].

## C01 Shortlist and rank funds in a category (High)

| Flow | Entry point | Tests found | What they check | Test result | Code read |
|---|---|---|---|---|---|
| F001 Shortlist and rank funds for one or more categories | E001 `shortlist.py` | `test_pipeline.py` (48 `check()` lines), `test_metrics_window.py` (18), `test_new_metrics.py` (24), `test_benchmark.py` (41), `test_scoring.py` (95) | See breakdown below | tested on the surface | yes [S01-S04] |

F001 is read across four slices, and its test coverage differs by sub-part:

- **Wiring, filters and output files** (`test_pipeline.py`): runs `shortlist.main` end to end with fake `fund_universe`, `fetch_nav_data`, `metrics`, `benchmark`, `portfolio_quality`, `holdings_fetch`, `report` and `amc_registry` modules. It asserts duplicate-code collapsing, stale-fund exclusion, a hard-filter exclusion, rank order, and exit codes 1 and 2 for the right conditions. The real candidate lookup, the real metric calculation and the real Excel export are never exercised, because all three are replaced by fakes [S01].
- **Scoring engine** (`test_scoring.py`): well tested against hand-computed answers, including percentile direction, tied values, the coverage floor, the `renormalize_available` and `average` policies, and 10 weights-loader error cases [S03].
- **Metrics** (`test_metrics_window.py`, `test_new_metrics.py`, `test_benchmark.py`): well tested for the 3-year drawdown window, the aligned risk-return ratio, Jensen's alpha and beta, benchmark excess return, rolling beat, downside capture and quartile consistency, each with a known-answer assertion. `unknown` for 1, 3 and 5-year CAGR, volatility and SIP XIRR: no assertion on these three was found in the test files read (U11).
- **Reports** (`test_pipeline.py`): the Markdown report is checked for specific phrases (method, weights, ranking, disclaimer, the "expense ratio not scored" line). The real `report.export_to_excel` formatting is faked, so it has no assertion in the files read (U15).

A further complication: at least five assertions in `test_scoring.py`, `test_new_metrics.py` and `test_pipeline.py` expect `weights.ini` values the committed file no longer has (for example, `test_scoring.py:61` expects `cagr_3y` to be 15; `weights.ini:35` has 10), so whether this test file currently passes at all is open (U13) [S03].

The sample run under `out_smallcap/` was produced by this flow; its output files match what `test_pipeline.py` asserts about file presence and content, but the sample itself was not additionally read against the test file line by line [S14].

## C02 Screen funds you already hold (High)

| Flow | Entry point | Tests found | What they check | Test result | Code read |
|---|---|---|---|---|---|
| F005 Screen holdings and say keep or review | E005 `mf_holdings_screener.py` | `test_mf_holdings_screener.py` (6 `def test_` + 55 `check()`), `test_screener_peers.py` (17 `check()`) | Row-level verdicts, confidence levels, notes, totals and sheet names in a written workbook; rule-by-rule verdict cases (stale, zero value, young fund, unmapped scheme); peer ranking | well tested | yes [S05] |
| F006 Convert a CDSL statement PDF to holdings spreadsheets | E006 `cdsl_holdings_to_xls.py` | none found | nothing | not tested | yes [S06] |

F005's known gaps: no test calls `load_navall` directly (so the download, same-day cache and two-URL fallback are not exercised), no test drives any of the four `sys.exit` stop conditions, and no test asserts the 60-fund peer cap (U18) [S05].

F006 has no test file at all: a search for `cdsl` (case-insensitive) across all 11 `test_*.py` files at the repository root found no match. ISIN check-digit validation, the OCR fallback and its confusable-character repair, the numeric cross-checks, and the reconciliation against statement totals are all untested (U20, U21) [S06].

## C03 Check one fund (High)

| Flow | Entry point | Tests found | What they check | Test result | Code read |
|---|---|---|---|---|---|
| F003 Report on one fund | E003 `check_fund.py` | `test_check_fund.py` (46 `check()` lines) | Name resolution (6 cases, including ambiguous and stale-twin names), peer pool construction, end-to-end evaluation with verdict and rank, report content, CLI exit codes, both output formats (`.docx` and `.md`), error paths | well tested | yes [S07] |

Known gaps: `report_docx.markdown_to_docx` content fidelity is checked only when `python-docx` is installed at test time, and is skipped otherwise; no test covers a fund that also has portfolio-quality data [S07]. The test stubs `config.BENCHMARK_ENABLED = False` and `config.PORTFOLIO_QUALITY_ENABLED = False`, so if those flags are `True` in a real run, the benchmark and portfolio-quality code paths inside `check_fund.py` are not exercised by this test (U22) [S07].

This also answers an earlier open question from reading `report.py` and `report_md.py` in isolation (S04): whether the Word report conversion is tested at all (U16). It is, through `test_check_fund.py`'s CLI test, with the installed-library caveat above [S04, S07].

## C04 Rank funds from a supplied metrics file (Medium)

| Flow | Entry point | Tests found | What they check | Test result | Code read |
|---|---|---|---|---|---|
| F002 Rank funds from a metrics CSV | E002 `rank_funds.py` | `test_rank_funds.py` (25 `check()` lines) | Ranking correctness, unit conversion (percent to fraction, drawdown sign), invalid and missing values, duplicates, plan filter, staleness, category separation, insufficient data, unit-style detection and override, bad-input error paths | well tested | yes [S08] |

Known gaps: no test for the `--exploratory` cross-category output, and no test for the Markdown report's content [S08].

## C05 Collect fund portfolio files and score portfolio quality (Medium)

| Flow | Entry point | Tests found | What they check | Test result | Code read |
|---|---|---|---|---|---|
| F007 Download newest portfolio files from fund houses | E007 `holdings_fetch.py` | `test_portfolio_quality.py` lines 236-270 | Link extraction, date parsing from file names, all three AMC picker regexes, newest-file selection, download validation (magic bytes, minimum size, stubbed HTTP), registry completeness (32 AMCs, unique keys), fund-house name matching for 8 AMCs | tested on the surface | yes [S09] |
| F008 Sort and check downloaded portfolio files | E008 `holdings_import.py` | `test_portfolio_quality.py` (same file) | AMC detection via fund-house name matching, zip extraction with path-traversal defence, the `PortfolioIndex` parsing and scoring that `--check` calls | tested on the surface | yes [S09] |
| F010 Build the AMFI large/mid/small company list | E010 `build_marketcap.py` | `test_portfolio_quality.py` (downstream use only) | `largemid_pct` computed correctly from a synthetic ISIN-to-category map | tested on the surface | yes [S09] |
| F015 Debug portfolio-quality parsing for a holdings folder | E015 `portfolio_quality.py` | `test_portfolio_quality.py` (lines 92-233, 35 `check()` lines) | Exact rubric re-computation against an independent calculation, every sub-criterion input, every failure path (too few holdings, bad weights sum, stale statement, unmatched scheme, below coverage floor), the market-cap sub-criterion, name normalisation, row classification, and the `shortlist.py` integration with partial data | well tested | yes [S10] |

F007's gap: nothing exercises a live AMC page; the module's own docstring says it was "written from the AMCs' public pages but NOT tested against live downloads" (U23) [S09]. F008's gap: the import-and-copy workflow itself (copy to `data/holdings/<amc>/`, skip already-imported files) is not tested, only the AMC-detection and parsing pieces it depends on [S09]. F010's gap: `build_marketcap.py`'s own PDF, Excel and CSV parsing, column auto-detection and validation warnings have no test; only the downstream use of the CSV it produces is tested [S09]. F015's gap: every test workbook is synthetic; no real AMC workbook was read, and the sector sub-criterion depends on AMC-supplied industry labels whose spelling may differ between fund houses (U24) [S10].

## C06 Provide benchmark index history (Medium)

| Flow | Entry point | Tests found | What they check | Test result | Code read |
|---|---|---|---|---|---|
| F009 Import index (TRI) history as a benchmark | E009 `import_tri.py` | `test_benchmark.py` (41 `check()` lines) | The benchmark calculation engine and all three benchmark-loading paths (local CSV, pinned code, auto-discovery), with synthetic data | tested on the surface | yes [S11] |

The 41 assertions test `benchmark.py`, not `import_tri.py` itself: no test calls `import_tri.main` or `import_tri.read_series`, so the CSV parsing, merging, deduplication and the gap/staleness validation warnings this script performs are untested (U25) [S11].

## C07 Back-test the forward signals (Medium)

| Flow | Entry point | Tests found | What they check | Test result | Code read |
|---|---|---|---|---|---|
| F004 Back-test forward signals for a category | E004 `backtest.py` | `test_forward_signals.py` (18 `def test_` functions) | Would cover NAV-derived signals, `fund_attributes.csv` loading and validation, stale-data handling, template writing, forward tilt and re-ranking, CLI end-to-end behaviour, forward-return grid logic, and persistent-skill detection, if it ran | unknown | yes [S12] |

`test_forward_signals.py` cannot execute: it imports `_run_end_to_end`, `make_nav`, `bench_returns` and `fund_returns` from `test_pipeline.py`, and none of those four names exist there (`test_pipeline.py`, 319 lines, read in full and searched) (U26) [S12]. The import fails before any of the 18 test functions run, so none of what they check has actually been exercised at this commit, even though the test code itself is well structured and uses synthetic data with edge cases. This is the same issue noted in [07-error-handling-and-observability.md](07-error-handling-and-observability.md): `backtest.py` also calls `benchmark.resolve_benchmark`, a function that does not exist in `benchmark.py`, so the entry point itself cannot run either.

## C08 Set up, refresh data and diagnose (Low)

This capability has no capability obligations in `obligations.md` because of its Low importance rating [obligations.md], but its four flows were read in S13 and are included here for completeness.

| Flow | Entry point | Tests found | What they check | Test result | Code read |
|---|---|---|---|---|---|
| F011 Download and cache NAV history for scheme codes | E011 `fetch_nav_data.py` | none dedicated | nothing; the module is always replaced by a stub in `test_pipeline.py`, `test_benchmark.py`, `test_check_fund.py` and `test_mf_holdings_screener.py` | not tested | yes [S13] |
| F012 First-run check against the live services | E012 `live_check.py` | none | nothing | not tested | yes [S13] |
| F013 Patch the Word report format into check_fund.py | E013 `apply_docx_patch.py` | none directly | nothing tests the patch script itself; the test assertions it injects into `test_check_fund.py` would test the patch's effect only after the patch has already been run | not tested | yes [S13] |
| F014 Diagnose AMFI NAVAll parsing | E014 `navall_diag.py` | none | nothing | not tested | yes [S13] |

None of these four is an oversight needing a fix: F011's download and caching logic is a real gap (it is relied on by every other flow that needs NAV data, through stubs that never exercise it for real), but F012 and F014 are diagnostic tools meant to be read by a person, and F013 is a one-time migration script already run; the files read treat an unhandled traceback in these three as useful diagnostic output rather than a fault to guard against [S13, 07-error-handling-and-observability.md].

## Summary counts

| Test result | Flows | Which |
|---|---|---|
| well tested | 4 | F002, F003, F005, F015 |
| tested on the surface | 5 | F001, F007, F008, F009, F010 |
| not tested | 5 | F006, F011, F012, F013, F014 |
| unknown | 1 | F004 |
| switched off | 0 | none |
| scan only, not read | 0 | none (all 15 flows were read in full) |

| By capability importance | Flows | Well tested or tested on the surface | Not tested or unknown |
|---|---|---|---|
| High (C01, C02, C03) | F001, F003, F005, F006 | 3 | 1 (F006) |
| Medium (C04, C05, C06, C07) | F002, F004, F007, F008, F009, F010, F015 | 6 | 1 (F004) |
| Low (C08) | F011, F012, F013, F014 | 0 | 4 |

Two of the three High-importance capabilities have no untested flow. C02's F006, the CDSL PDF converter, is the only High-importance flow with no test at all. Among Medium-importance capabilities, F004 (the back-test) cannot currently run its tests or its own code.

## Unknowns and next probes

| ID | Question | Why it matters here |
|---|---|---|
| U11 | Is there any test that checks `calculate_cagr`, `calculate_volatility` or `calculate_sip_xirr` against a known answer? | These are three of the most heavily weighted metrics in `weights.ini`, and no assertion on them was found. |
| U13 | Does the test suite pass today? At least five assertions in `test_scoring.py`, `test_new_metrics.py` and `test_pipeline.py` expect `weights.ini` values the current file does not have. | A failing suite would hide a real fault in the scoring engine. |
| U15 | Does any test exercise the real `report.export_to_excel`? | `test_pipeline.py` fakes the Excel export, so its formatting is unverified. |
| U18 | What happens at a real run when AMFI blocks the `NAVAll.txt` download or changes its layout again? | No test drives the download, cache or fallback path that every holdings-screener run depends on. |
| U20 | Do the hardcoded A4 column positions in `cdsl_holdings_to_xls.py` work for all CDSL statement layouts? | There is no test to catch a layout mismatch either. |
| U21 | Is there a reason no tests exist for a 1,174-line script with OCR, ISIN repair and numeric cross-checks? | The entire CDSL conversion path for C02 is unverified. |
| U22 | Does `test_check_fund.py` still reflect production if `BENCHMARK_ENABLED` or `PORTFOLIO_QUALITY_ENABLED` are `True`? | Those paths are stubbed off in the one test file for `check_fund.py`. |
| U23 | Do the three AMC picker regexes still match the AMC websites today? | No test reaches a live page; a layout change would look identical to "no new files". |
| U24 | How consistent are industry names across real AMC workbooks? | Only synthetic workbooks were tested for the sector-concentration sub-score. |
| U25 | Does `import_tri.py`'s own CSV parsing handle all the NSE download formats in use? | No test calls `import_tri.main` or `import_tri.read_series` directly. |
| U26 | Are the missing helper functions, config settings and `benchmark.resolve_benchmark` function from an unmerged branch? | Decides whether `test_forward_signals.py` and `backtest.py` can ever be made to run as they stand. |

## Related documents

- [03-request-to-response-flow.md](03-request-to-response-flow.md): the main, alternative and exception flows these tests cover
- [07-error-handling-and-observability.md](07-error-handling-and-observability.md): the exit codes and failure paths behind several of the gaps above
- [10-test-review.md](10-test-review.md): strengths, weak tests and ranked risks (not yet written)
