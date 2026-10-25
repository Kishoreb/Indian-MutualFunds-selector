# Test review

Audience: a developer or test lead deciding where to spend testing effort first, and how much to trust the existing suite before changing code near it.
Evidence: 15 of 15 entry points read · 8 capabilities · 14 open unknowns · commit ef2fb5a · Surveyor 2.2.0 · 2026-10-25

This document reads the test results in [09-test-exposure-map.md](09-test-exposure-map.md) for what they mean for risk: which tests are genuinely strong, which run but prove little, whether any are disabled, where the suite itself has structural problems, and which gaps matter most given what each capability does.

## Strengths

Five test files check real calculations against hand-computed or independently recomputed answers:

- `test_scoring.py` (95 `check()` lines) checks the scoring engine against hand-computed answers: percentile direction, tied values sharing the average rank, the coverage floor as an inclusive boundary, both missing-data policies (`renormalize_available` and `average`), that the per-metric points add up to the final score, and 10 separate error cases in the weights loader [S03].
- `test_portfolio_quality.py` (lines 92-233, 35 `check()` lines) recomputes the portfolio-quality score by an independent calculation and checks every failure path returns `None` with a reason: too few equity holdings, weights not summing to about 100%, a stale statement, an unmatched scheme, and coverage below the floor. It also checks that zip extraction cannot write outside its target directory [S10].
- `test_check_fund.py` (46 `check()` lines) checks 6 name-resolution cases including a stale twin and a two-ISIN twin, builds the peer pool correctly (same category only, stale peers dropped, capped), and checks both output formats and all three CLI exit codes [S07].
- `test_mf_holdings_screener.py` and `test_screener_peers.py` (72 `check()` lines together) check 14 separate verdict cases (strong fund, weak fund, two ambers in one evidence type, two reds, absolute-only, young fund, stale NAV, zero value, unmapped, NAV error, too few peers) and read a written `.xls` workbook back row by row to check verdict, confidence, notes and totals [S05].
- `test_rank_funds.py` (25 `check()` lines) checks ranking correctness, percent-to-fraction unit conversion, duplicate handling, the Direct-Growth plan filter, staleness exclusion and 10 specific input-error exit paths, without mocking the scoring engine it calls [S08].

Three test files recover known answers for metrics that are hard to get right by accident: `test_metrics_window.py` checks the aligned risk-return ratio against a hand-computed value, `test_new_metrics.py` recovers a known beta and alpha from a synthetic series, and `test_benchmark.py` checks benchmark excess return and rolling-beat percentage against an analytic ratio, plus a downside-capture case in `test_scoring.py` where a fund that takes exactly half of every market move checks to 0.5 [S02].

## Tests that prove little

Several tests pass today but do not exercise the real code they appear to cover, because a fake or stub stands in for it:

- `test_pipeline.py` replaces `fund_universe`, `fetch_nav_data`, `metrics`, `benchmark`, `portfolio_quality`, `holdings_fetch`, `report` and `amc_registry` with fakes before importing `shortlist`, then asserts wiring, filters, ranking order and output files [S01]. The real candidate lookup (`fund_universe.find_candidates`), the real metric calculations, and the real Excel export in `report.export_to_excel` have no assertion anywhere in the test files read (U11, U15) [S01, S04].
- `test_check_fund.py` sets `config.BENCHMARK_ENABLED = False` and `config.PORTFOLIO_QUALITY_ENABLED = False` before running. `BENCHMARK_ENABLED` defaults to `True` in `config.py` [S01, cited from S07]. So if both flags are `True` in a real run, the one test file for a High-importance capability (C03) never runs the benchmark or portfolio-quality branches of `check_fund.evaluate` (U22) [S07].
- `test_benchmark.py`'s 41 assertions check `benchmark.py`, the module that consumes a TRI file, not `import_tri.py`, the module that produces one. No test calls `import_tri.main` or `import_tri.read_series`, so the CSV parsing, merging, deduplication and gap/staleness warnings that script performs are unchecked (U25) [S11].
- `test_portfolio_quality.py` checks `build_marketcap.py`'s output only by feeding a synthetic ISIN-to-category dictionary straight into the downstream calculation. The PDF line-scanning, the Excel/CSV column auto-detection, and the count-sanity warnings inside `build_marketcap.py` itself have no test [S09].
- `fetch_nav_data.py`, the module every other flow depends on for NAV history, is never imported for real in any test: `test_pipeline.py`, `test_benchmark.py`, `test_check_fund.py` and `test_mf_holdings_screener.py` all replace it with a stub before import. Its download, 1-day cache check, and meta-file saving have no test that calls the real functions [S13].
- `test_portfolio_quality.py`'s coverage of the AMC download step (F007) stubs the HTTP call entirely. The module's own docstring already says it was "written from the AMCs' public pages but NOT tested against live downloads," and the test does not change that (U23) [S09].

## Disabled tests

None found. Searched `skip`, `xfail`, `Skip`, `disabled`, `DISABLED` across all 11 `test_*.py` files at the repository root; the 4 matches are test description text and variable names, not a disabling mechanism such as `@pytest.mark.skip` or `unittest.skip` [inventory]. This is a whole-repository search within the stated boundary, so the absence is stated directly rather than as an unknown.

## Level-of-test problems

- No `pytest.ini`, `conftest.py` or CI file says which of the two assertion styles the owner actually runs. 24 functions named `def test_...` (18 of them in one file) would be collected by pytest; 421 `check(name, cond)` lines spread across 10 files are a homegrown assertion helper that only runs when its file is executed directly as a script [inventory]. Until that is settled, "well tested" in this document means "a check for this exists and would catch the described fault if run," not "runs today, automatically, as part of a release step" (U01).
- `test_forward_signals.py` has 18 well-structured `def test_` functions, but its import line pulls `_run_end_to_end`, `make_nav`, `bench_returns` and `fund_returns` from `test_pipeline.py`, and none of those four names exist there (`test_pipeline.py` read in full, 319 lines) [S12]. The import fails before any of the 18 tests run, so the whole file currently contributes nothing, however well the individual tests read (U26).
- The entry point those tests would cover does not run either. `backtest.py` calls `benchmark.resolve_benchmark`, a function that does not exist in `benchmark.py` (284 lines, read in full), and both `backtest.py` and `forward_signals.py` reference more than a dozen `config.BACKTEST_*` and `FORWARD_*` settings that `config.py` (194 lines, read in full) does not define [S12]. A test suite fix alone would not make this capability work; the module itself would raise `AttributeError` on first use (U26).
- At least five assertions in `test_scoring.py`, `test_new_metrics.py` and `test_pipeline.py` expect `weights.ini` values the committed file does not have: `test_scoring.py:61` expects `cagr_3y` at 15 where the file has 10, `test_scoring.py:63` expects scoring method `zscore` where the file has `percentile`, and `test_new_metrics.py:72` expects Jensen's alpha and beta at weight 0 where the file gives both 5 [S03]. Because Surveyor does not run code, whether these assertions fail today is inferred, not observed, but a fault here would hide a real problem in the scoring engine for the project's highest-importance capability (U13).
- `manifest.py` defines `write_manifest`, which has no caller anywhere in `*.py`, `*.md`, `*.ini` or `*.txt` at the repository root except `test_forward_signals.py`, which reads `config.MANIFEST_JSON`, a setting `config.py` does not define [S04]. This is the same drift as the back-test modules: test code written against a version of `config.py` that this repository does not contain (U17).

## Risks ranked by importance times weakness

Recommendation: the scoring below multiplies each capability's importance (High = 3, Medium = 2, Low = 1, from `capabilities.md`) by how weak its test result is (well tested = 1, tested on the surface = 2, not tested or unknown = 3, from [09-test-exposure-map.md](09-test-exposure-map.md)). It ranks where a fault is most likely to go unnoticed and matter most, not how good or bad the code itself is.

| Score | Flow | Capability (importance) | Test result | Why it matters |
|---|---|---|---|---|
| 9 | F006 Convert a CDSL statement PDF | C02 (High) | not tested | The only High-importance flow with no test at all. ISIN check-digit repair, the OCR confusable-character substitution, three numeric cross-checks and the reconciliation against statement totals are all unverified in 1,174 lines of parsing logic that feeds personal financial data into the holdings screener (U20, U21) [S06]. |
| 6 | F001 Shortlist and rank funds | C01 (High) | tested on the surface | The project's stated purpose. The one test file fakes the candidate lookup, the real metric calculations and the real Excel export, and five of its own assertions expect `weights.ini` values the shipped file does not have, so whether it passes at all today is open (U11, U13, U15). |
| 6 | F004 Back-test the forward signals | C07 (Medium) | unknown | Lower importance than F001, but the weakness is total: the test file cannot import, and the script it would test calls a function that does not exist. Nothing here can be trusted until the missing pieces are explained (U17, U26) [S12]. |
| 4 | F007, F008, F010 Collect and sort portfolio files, build the market-cap list | C05 (Medium) | tested on the surface | All three feed the portfolio-quality metric. Live AMC page matching, the file-sort-and-copy workflow, and the market-cap file's own parsing are each untested; a changed AMC page would look identical to "no new file" (U23) [S09]. |
| 4 | F009 Import benchmark index history | C06 (Medium) | tested on the surface | `import_tri.py`'s own CSV parsing, merging and validation warnings are untested; only the module that consumes its output is tested (U25) [S11]. |
| 3 | F003 Report on one fund | C03 (High) | well tested | Scored here only because of its importance, not a real weakness: the test suite for this flow is strong. The one caveat is that two config flags are forced off during the test; `BENCHMARK_ENABLED` defaults to `True`, so if it is also `True` in a real run, the benchmark and portfolio-quality branches are not exercised by this test (U22) [S07]. |
| 3 | F005 Screen funds you already hold | C02 (High) | well tested | Same pattern as F003: importance alone, not a test gap, accounts for the score. The verdict logic itself is well covered (U18 covers only the NAV-download path, not the verdict rules) [S05]. |
| 3 | F011-F014 Setup and diagnostic scripts | C08 (Low) | not tested | Four Low-importance, untested flows. Three (`live_check.py`, `apply_docx_patch.py`, `navall_diag.py`) are one-off or diagnostic tools where an unhandled traceback is useful output, not a fault. The fourth, `fetch_nav_data.py`, is a real gap: every other flow depends on it for NAV history, but only through stubs that never call its real download, cache or meta-saving code, and whether the real code handles rate-limiting and concurrent runs is itself an open question (U27) [S13]. |
| 2 | F002 Rank funds from a metrics CSV | C04 (Medium) | well tested | Lowest risk on this list: a well-tested flow of middling importance. The only gaps are the `--exploratory` output and Markdown report content, neither of which affects the ranking itself [S08]. |
| 2 | F015 Score portfolio quality | C05 (Medium) | well tested | Also low risk: the rubric itself is tested against an independent recomputation. The residual risk is that every test workbook is synthetic, so inconsistent industry-name spelling across real AMC workbooks (U24) would not be caught by this suite [S10]. |

Two ties are worth reading past the number. F003 and F005 share a score of 3 with the four Low-importance scripts in C08, but for opposite reasons: F003 and F005 are already well tested, so their risk is close to its floor, while the C08 scripts are genuinely untested and simply matter less if they break. The number treats them alike; the reason behind each number does not.

## Unknowns and next probes

| ID | Question | Why it matters here |
|---|---|---|
| U01 | Which tests does the owner actually run: pytest, or each test file as a script? | Decides whether any of the results in this document describe a check that runs automatically, or only one that would catch a fault if someone remembered to run that file. |
| U11 | Is there any test that checks `calculate_cagr`, `calculate_volatility` or `calculate_sip_xirr` against a known answer? | These are among the most heavily weighted metrics in `weights.ini`, and `test_pipeline.py` fakes the module that contains them. |
| U13 | Does the test suite pass today? Five assertions expect `weights.ini` values the current file does not have. | A failing suite for the highest-importance capability's scoring engine would hide a real fault. |
| U15 | Does any test exercise the real `report.export_to_excel` or `report_md.explain`? | `test_pipeline.py` fakes the Excel export, so its formatting and the risk-note logic are unverified. |
| U17 | Is `manifest.py` used by anything, and is the missing `MANIFEST_JSON` setting a sign that `config.py` predates the back-test code? | Explains why `test_forward_signals.py` and `backtest.py` reference settings `config.py` does not define. |
| U18 | What happens at a real run when AMFI blocks the `NAVAll.txt` download or changes its layout again? | No test drives the download, cache or fallback path every holdings-screener run depends on. |
| U20 | Do the hardcoded A4 column positions in `cdsl_holdings_to_xls.py` work for every CDSL statement layout? | There is no test to catch a layout mismatch, and this is the only untested High-importance flow. |
| U21 | Is there a reason no tests exist for a 1,174-line script with OCR, ISIN repair and numeric cross-checks? | The entire CDSL conversion path for a High-importance capability is unverified. |
| U22 | Does `test_check_fund.py` still reflect production if `BENCHMARK_ENABLED` or `PORTFOLIO_QUALITY_ENABLED` are `True`? | Those paths are stubbed off in the one test file for `check_fund.py`, a well-tested flow with one real blind spot. |
| U23 | Do the three AMC picker regexes still match the AMC websites today? | No test reaches a live page; a layout change would look identical to "no new files," and three Medium-importance flows depend on this. |
| U24 | How consistent are industry names across real AMC workbooks? | Only synthetic workbooks were tested for the sector-concentration sub-score; this is the one gap in an otherwise well-tested flow. |
| U25 | Does `import_tri.py`'s own CSV parsing handle all the NSE download formats in use? | No test calls `import_tri.main` or `import_tri.read_series` directly; the 41 assertions in `test_benchmark.py` test a different module. |
| U26 | Are the missing helper functions, config settings and `benchmark.resolve_benchmark` function from an unmerged branch, or were they removed? | Decides whether `test_forward_signals.py` and `backtest.py` can be made to run as they stand, or need the missing pieces restored first. |
| U27 | Is the 0.3-second sleep between mfapi.in calls sufficient to avoid rate-limiting, and does the cache logic handle concurrent runs? | `fetch_nav_data.py` is stubbed in every test that touches it, so nothing checks its real behaviour under load. |

## Related documents

- [09-test-exposure-map.md](09-test-exposure-map.md): the per-flow test results this document ranks and reviews
- [04-shortlist-and-rank.md](04-shortlist-and-rank.md): the core capability most affected by the weights.ini contradiction (U13)
- [11-developer-testing-tasks.md](11-developer-testing-tasks.md): concrete tasks to close the highest-ranked gaps (not yet written)
- [12-test-plan.md](12-test-plan.md): the strategy built from the priorities ranked here (not yet written)
