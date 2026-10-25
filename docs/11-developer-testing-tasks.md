# Developer testing tasks

Audience: a developer picking the next testing work, in order of risk.
Evidence: 15 of 15 entry points read · 8 capabilities · 9 open unknowns · commit ef2fb5a · Surveyor 2.2.0 · 2026-10-25

These are the 5 highest-risk gaps from the risk table in [10-test-review.md](10-test-review.md), turned into concrete work. The order matches that table: risk score (capability importance times test weakness) first, lower scores after.

No `pytest.ini`, `conftest.py` or CI file says which of the two existing assertion styles the project actually runs (U01). 9 of the 11 `test_*.py` files use a homegrown `check(name, cond)` helper that only runs when the file is executed directly; 2 use `def test_...` functions that pytest would collect [inventory]. Every task below follows whichever style the file it extends already uses, and defaults to `check(name, cond)` for a new file, since that is the more common style in this repository.

## Task 1: Test the CDSL statement PDF converter (risk score 9, highest)

The only High-importance flow with no test at all. `cdsl_holdings_to_xls.py` is 1,174 lines of ISIN validation, OCR repair and numeric cross-checks that feed personal financial data into the holdings screener, and no test file matches `cdsl` anywhere in the repository [S06].

**Target files:** `cdsl_holdings_to_xls.py` (existing); a new `test_cdsl_holdings_to_xls.py`.

**What to assert:**
- `isin_checksum_ok()` accepts a known-valid ISIN and rejects a known-invalid one [S06, `cdsl_holdings_to_xls.py:159`].
- The `CONFUSABLE` OCR-repair table substitutes a look-alike character (O/0, I/1, S/5, B/8, etc.) only when doing so makes the check digit pass, and when several repairs are valid the one needing fewest edits wins [S06, `cdsl_holdings_to_xls.py:103`].
- `resolve_numbers()` recovers a missing quantity, price or value from the other two, and the qty-times-price-equals-value check holds within the 0.02 tolerance [S06, `cdsl_holdings_to_xls.py:453,464`].
- The mutual fund triple cross-check (units times NAV equals valuation, valuation minus invested equals profit/loss, profit/loss divided by invested equals the percentage) flags a row that fails it [S06, `cdsl_holdings_to_xls.py:793`].
- `reconcile()` compares extracted totals against the statement's own Portfolio Value and Grand Total lines and flags a mismatch [S06, `cdsl_holdings_to_xls.py:639`].
- The three `sys.exit` failure paths: no holding rows found (exit 1), no text layer and Tesseract missing, and the chosen output library (`xlwt` or `openpyxl`) not installed [S06, `cdsl_holdings_to_xls.py:624,600,940`].

**Steps:**
1. Write unit tests for `isin_checksum_ok`, `resolve_numbers` and `reconcile` directly with hand-picked values; none of the three needs a PDF.
2. Obtain one real CDSL CAS PDF with the personal numbers (folio, demat BO ID, holding values) replaced by placeholder figures before it is added to the repository (rules section 1: no personal data in any output). `// adapt`: the fixture path below is a guessed name, since no such file exists yet.
3. Use that sanitised PDF to test the full page-to-row parsing path (the hardcoded A4 column positions at `cdsl_holdings_to_xls.py:69`) end to end, asserting the row count and a couple of known values.
4. Once a second real statement is available, record whether the column positions still line up (closes U20).

**Done when:**
- [ ] `isin_checksum_ok` has a passing and a failing case
- [ ] the `CONFUSABLE` repair is exercised with at least one OCR-garbled ISIN
- [ ] `resolve_numbers` is tested for all three derive directions and the 0.02 tolerance boundary
- [ ] `reconcile` is tested against a matching and a mismatching stated total
- [ ] all three `sys.exit` failure paths have a test
- [ ] one test runs the real parsing path against a real, sanitised statement, not a stub

## Task 2: Test the CAGR, volatility and SIP XIRR calculations, and settle the weights.ini contradiction (risk score 6)

The project's stated purpose. `test_pipeline.py` fakes the module that holds these calculations before testing `shortlist.py`, so the CAGR (1, 3 and 5-year), volatility and SIP XIRR figures have no known-answer assertion in the files read for S02 (U11, named `calculate_cagr`, `calculate_volatility` and `calculate_sip_xirr` in that question). Separately, at least five assertions across `test_scoring.py` and `test_new_metrics.py` expect `weights.ini` values the committed file does not have, so whether the scoring suite passes today is open (U13) [S02, S03].

**Target files:** `metrics.py` (existing); `test_metrics_window.py`, `test_new_metrics.py`, `test_scoring.py`, `test_pipeline.py` (existing, to extend or fix); `weights.ini` (may need a value changed, pending step 1 below).

**What to assert:**
- CAGR over 1, 3 and 5 years against a hand-computed value on a synthetic NAV series, including the `None` case when the fund's first NAV is more than 30 days after the window start [S02, `metrics.py:54`].
- Volatility against a hand-computed value, and the `None` case below 6 monthly returns [S02, `metrics.py:75`].
- SIP XIRR against a hand-computed value for a synthetic monthly series, including the `None` case below 6 instalments [S02].

**Steps:**
1. Ask a developer to run `test_scoring.py`, `test_new_metrics.py` and `test_pipeline.py` once and report which assertions fail; Surveyor does not run code, so this is the only way to confirm U13.
2. `test_scoring.py:61` expects `cagr_3y` weight 15 where `weights.ini:35` has 10; `test_scoring.py:63` expects scoring method `zscore` where `weights.ini:27` has `percentile`; `test_new_metrics.py:72` expects `jensen_alpha` and `beta` at weight 0 where `weights.ini:51-52` give both 5 [S03]. Ask the product owner which side is the intended one (closes U14), then correct the other.
3. Add known-answer tests for the CAGR, volatility and SIP XIRR calculations in `metrics.py`, following the `check(name, cond)` pattern `test_metrics_window.py` and `test_new_metrics.py` already use for the ratio and the beta/alpha recovery [S02].
4. Use a hand-built NAV series, for example a constant 10%-a-year compounding series, so the expected CAGR, volatility and SIP XIRR can be computed by hand with a tight tolerance, the same way `test_metrics_window.py:51` checks the aligned risk-return ratio.

**Done when:**
- [ ] a developer has run the three test files and the pass/fail result for U13 is recorded
- [ ] the `weights.ini`/test mismatch is resolved on the side the product owner confirms, not left open
- [ ] CAGR (1, 3, 5-year) has a known-answer test and a None-case test
- [ ] volatility has a known-answer test and a None-case test
- [ ] SIP XIRR has a known-answer test and a None-case test

## Task 3: Restore the back-test and forward-signal modules before adding any test (risk score 6)

Scored lower in importance than Task 2, but the weakness is total, not partial: `test_forward_signals.py` cannot even import, and `backtest.py` cannot run. No new test is useful until the code itself runs [S12].

**Target files:** `backtest.py`, `forward_signals.py`, `test_forward_signals.py`, `benchmark.py`, `config.py` (all existing).

**What is broken, all read in full for S12:**
- `test_forward_signals.py:23` imports `_run_end_to_end`, `make_nav`, `bench_returns` and `fund_returns` from `test_pipeline.py`; none of those four names exist in that 319-line file. The import fails before any of the file's 18 tests run.
- `backtest.py:273` calls `benchmark.resolve_benchmark`, a function that does not exist anywhere in the 284-line `benchmark.py`.
- `backtest.py`, `forward_signals.py` and `test_forward_signals.py` reference more than a dozen `config.BACKTEST_*`, `FORWARD_*` and related settings that the 194-line `config.py` does not define.

The 18 existing tests already cover the right ground once this is fixed: NAV-derived signals, `fund_attributes.csv` loading and validation, staleness handling, template writing, forward tilt and re-ranking, CLI end-to-end behaviour, and verdict/weight suggestions [S12]. The task is to get them running, not to write new ones first.

**Steps:**
1. Ask a developer: is there an unmerged branch holding the missing `test_pipeline.py` helpers, the `benchmark.resolve_benchmark` function and the `BACKTEST_*`/`FORWARD_*` config settings, or were they removed (U26)?
2. If a branch exists, merge or port the missing pieces, then run `test_forward_signals.py` and record the result.
3. If they were removed on purpose, decide with the product owner whether capability C07 is still meant to work. If not, say so in the module rather than leaving a test file that can never pass.
4. Only once the import succeeds, review the 18 tests for gaps; none were found in the files read, but they were read for structure, not executed.

**Done when:**
- [ ] U26 is answered: a branch was found and merged, or the removal is confirmed
- [ ] `test_forward_signals.py` imports without an `ImportError`
- [ ] `backtest.py` runs against a real category without an `AttributeError`
- [ ] the 18 existing tests pass, or each failure is triaged individually

## Task 4: Test the AMFI market-cap list parser (risk score 4)

Part of the same risk-table row as the AMC portfolio-file download and sort flows (F007, F008). Of the three, `build_marketcap.py`'s own parsing is the one that can be tested from a local file alone: the AMC picker regexes (`pick_nippon`, `pick_dsp`, `pick_baroda`) need a live AMC page to test meaningfully, which an automated test cannot rely on (U23), so that gap is better closed by a manual check than a unit test [S09].

**Target files:** `build_marketcap.py` (existing); a new `test_build_marketcap.py`. `test_portfolio_quality.py` tests only the downstream use of this module's output (a synthetic ISIN-to-category dictionary), not the module itself [S09].

**What to assert:**
- `from_text_lines()` picks the last Large/Mid/Small Cap label on a line that has both an ISIN and a label [S09, `build_marketcap.py:36`].
- `from_table()` picks the column with the most ISIN-matching cells as the ISIN column, and the column with the most Large/Mid/Small matches as the category column [S09, `build_marketcap.py:47`].
- A duplicate ISIN is dropped, keeping the first [S09, `build_marketcap.py:115`].
- `validate()` warns when the company count is under 500, when the large-cap count is outside 80-130, when the mid-cap count is outside 120-180, or when a category has 0 rows [S09, `build_marketcap.py:85`].
- Exit 2 for an unreadable or unsupported input file, exit 1 when no ISIN-and-category rows are found [S09, `build_marketcap.py:112,117`].

**Steps:**
1. Build a small synthetic input for each of the three accepted formats (a short text block standing in for extracted PDF lines, and a small Excel or CSV table), rather than a real AMFI download, since the parsing rules are format-generic.
2. Follow the `check(name, cond)` convention `test_portfolio_quality.py` already uses for this module's downstream consumer [S09, inventory].
3. For the `validate()` warnings, build one input exactly at each boundary (500 companies, 80 and 130 large-cap, 120 and 180 mid-cap) rather than only testing the middle of each range.

**Done when:**
- [ ] `from_text_lines` is tested with multiple labels on one line
- [ ] `from_table` is tested for both the ISIN-column and the category-column auto-detection
- [ ] duplicate-ISIN dropping is tested
- [ ] all four `validate()` warning conditions have a boundary test
- [ ] both exit codes (1 and 2) have a test

## Task 5: Test import_tri.py's own CSV parsing (risk score 4)

`test_benchmark.py`'s 41 assertions test `benchmark.py`, the module that consumes a TRI (Total Return Index) file; no test calls `import_tri.main` or `import_tri.read_series`, the functions that produce one [S11].

**Target files:** `import_tri.py` (existing); a new `test_import_tri.py`.

**What to assert:**
- Column auto-detection picks a column containing "date" and a column containing one of close, tri, total return, value, nav or index as the value column [S11, `import_tri.py:37`].
- Multiple input CSVs are merged, duplicate dates dropped (keeping the last), and the result sorted by date [S11].
- The 250-row minimum: exit 1 below it [S11, `import_tri.py:82,83`].
- The 10-day gap warning and the fewer-than-5-years warning [S11, `import_tri.py:95,103`].
- The output filename convention: spaces become underscores, "&" becomes "and" [S11, `import_tri.py:28`].
- Exit 2 for a missing `--category`, no input files, or an unknown category [S11, `import_tri.py:65`].

**Steps:**
1. Build two small synthetic CSVs with overlapping dates to test the merge and de-duplication together.
2. Build one undersized CSV (under 250 rows) for the exit-1 path, and one with a 15-day gap for the warning, following the `check(name, cond)` convention `test_benchmark.py` already uses for this capability [S11, inventory].
3. Ask the product owner which real NSE TRI download format they actually use (U25), and add one test using a short excerpt of that real format once known.

**Done when:**
- [ ] column auto-detection is tested for at least two of the accepted value-column names
- [ ] merge and de-duplication across two input files is tested
- [ ] the 250-row minimum and both warnings (gap, short history) are tested
- [ ] the output filename convention is tested
- [ ] both exit-2 conditions and the exit-1 condition are tested

## Unknowns and next probes

| ID | Question | Why it matters here |
|---|---|---|
| U01 | Which tests does the owner actually run: pytest, or each test file as a script? | Decides which convention a new test file should follow to actually run. |
| U11 | Is there any test that checks the CAGR, volatility or SIP XIRR calculations against a known answer? | Task 2's main gap. |
| U13 | Does the test suite pass today? Five assertions expect `weights.ini` values the current file does not have. | Must be answered before trusting any pass/fail result from the existing scoring tests. |
| U14 | Are the shipped weights, including 5 points each on Jensen's alpha and beta, the owner's intended current weights? | Decides which side of the Task 2 contradiction gets corrected. |
| U20 | Do the hardcoded A4 column positions in `cdsl_holdings_to_xls.py` work for every CDSL statement layout? | Task 1 cannot fully close until a second real statement is checked. |
| U21 | Is there a reason no tests exist for the CDSL conversion script? | Context for Task 1; no answer changes the task, but it is worth asking before assuming the gap was accidental. |
| U23 | Do the AMC picker regexes still match the AMC websites today? | Explains why Task 4 picks `build_marketcap.py` over the picker regexes from the same risk row. |
| U25 | Does `import_tri.py`'s own CSV parsing handle all the NSE download formats in use? | Task 5's main gap. |
| U26 | Are the missing functions and config settings in an unmerged branch, or were they removed? | Blocks Task 3 entirely until answered. |

## Related documents

- [10-test-review.md](10-test-review.md): the risk table these tasks are drawn from
- [09-test-exposure-map.md](09-test-exposure-map.md): the per-flow test results behind that risk table
- [04-shortlist-and-rank.md](04-shortlist-and-rank.md): the core capability Task 2 and Task 3 affect
- [12-test-plan.md](12-test-plan.md): the overall testing strategy these tasks feed into (not yet written)
