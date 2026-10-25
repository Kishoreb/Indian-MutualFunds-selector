# Test plan

Audience: a developer or test lead planning what to test next, in what order, and with what tooling, now that the survey has mapped every flow's test coverage and ranked the gaps.
Evidence: 15 of 15 entry points read · 8 capabilities · 14 open unknowns · commit ef2fb5a · Surveyor 2.2.0 · 2026-10-25

This plan ties together [09-test-exposure-map.md](09-test-exposure-map.md) (what each flow's tests check today), [10-test-review.md](10-test-review.md) (which of those tests are strong, weak or missing, ranked by risk) and [11-developer-testing-tasks.md](11-developer-testing-tasks.md) (the top 5 gaps turned into concrete tasks). It sets the strategy, the priority order beyond those 5 tasks, and what must be true before a gap counts as closed.

## Strategy by level

The repository's existing tests already fall into three levels, by how much of the real code each one exercises. The strategy keeps the two levels that already work and names what the third level needs.

**Level 1: known-answer checks on a single calculation or parsing function, with no file or network access.** This is the strongest level in the repository today. `test_scoring.py` checks the scoring engine against hand-computed answers: percentile direction, tied ranks sharing the average, the coverage floor, both missing-data policies, and 10 weights-loader error cases [S03]. `test_metrics_window.py`, `test_new_metrics.py` and part of `test_benchmark.py` recover known values for the aligned risk-return ratio, Jensen's alpha and beta, benchmark excess return and rolling-beat percentage, and a downside-capture case in `test_scoring.py` checks to exactly 0.5 for a fund that takes half of every market move [S02]. `test_portfolio_quality.py` recomputes the portfolio-quality score by an independent calculation [S10]. Recommendation: every new calculation or parsing function should get one of these first, following the same pattern, before a higher level is attempted; the CAGR, volatility, SIP XIRR, ISIN-checksum and CSV auto-detection work in [11-developer-testing-tasks.md](11-developer-testing-tasks.md) Tasks 1, 2, 4 and 5 is this level.

**Level 2: a whole entry point run end to end, with its external dependencies faked.** `test_pipeline.py` runs `shortlist.main` with fake `fund_universe`, `fetch_nav_data`, `metrics`, `benchmark`, `portfolio_quality`, `holdings_fetch`, `report` and `amc_registry` modules, and checks wiring, filters, rank order and exit codes [S01]. `test_check_fund.py` and `test_mf_holdings_screener.py` do the same for their own entry points, checking CLI exit codes and the content of written output files [S07, S05]. This level is also strong in this repository, but it proves wiring and exit codes, not the faked modules' own behaviour [10-test-review.md, "Tests that prove little"].

**Level 3: the real external input or output, not a fake.** This is where the repository's test gaps concentrate. No test calls the real `fund_universe.find_candidates`, the real metric calculations, or the real `report.export_to_excel` that Level 2's fakes stand in for (U11, U15) [S01, S04]. No test drives a real CDSL statement PDF through `cdsl_holdings_to_xls.py` (U20, U21) [S06], a real AMC portfolio page through `holdings_fetch.py` (U23) [S09], or a real NSE TRI download through `import_tri.py`'s own parsing (U25) [S11]. Recommendation: for each High- or Medium-importance flow that still lacks Level 3 coverage, add one test against a real, sanitised sample of its external input, as [11-developer-testing-tasks.md](11-developer-testing-tasks.md) Task 1 (step 2) already describes for the CDSL converter. A synthetic file can prove the parsing rules are internally consistent; only a real sample, with personal data replaced, can show those rules match what the outside system actually sends.

## Priority areas from document 10

[10-test-review.md](10-test-review.md)'s risk table ranks all 15 flows by capability importance times test weakness. In that order:

1. F006, the CDSL statement PDF converter (C02, High importance), not tested: the only High-importance flow with no test at all (score 9).
2. F001, shortlist and rank (C01, High importance), tested on the surface, and F004, back-test the forward signals (C07, Medium importance), unknown: tied at score 6. F001's gap is Level 3 coverage of the real metrics and the real Excel export; F004's test file cannot even import.
3. F007, F008 and F010, portfolio file collection and the market-cap list (C05, Medium importance), and F009, benchmark import (C06, Medium importance): tied at score 4, all missing Level 3 coverage of their own parsing or page-matching code.
4. F003 and F005 (C03 and C02, both High importance), well tested, and F011-F014 (C08, Low importance), not tested: tied at score 3 for opposite reasons. F003 and F005 are already strong, so their risk sits near its floor; the C08 scripts are genuinely untested but matter less if they break.
5. F002 and F015 (C04 and C05, both Medium importance), both well tested: the lowest risk on the table, at score 2.

[11-developer-testing-tasks.md](11-developer-testing-tasks.md) turns the top 5 rows (through score 4) into Tasks 1-5. This plan's priority order for work beyond those 5 tasks follows the same table: the row-3 ties not already covered by a task, then the row-4 ties, then row 5.

## Entry and exit criteria

Recommendation: before any of the work above counts as making a flow safer to change, three standing contradictions should be settled, because a new test built on top of them would inherit their uncertainty rather than resolve it:

- U01: whether the project runs its tests with `pytest`, or by executing each `check()`-style file directly as a script. Until this is settled, "well tested" anywhere in this survey means a check exists that would catch the described fault if run, not that it runs automatically today [10-test-review.md, "Level-of-test problems"].
- U13 and U14: whether `weights.ini`'s shipped values or the five test assertions that expect different values are the intended ones. This sits under the one test file covering the project's highest-importance scoring engine [S03].
- U26: whether `backtest.py`'s missing `benchmark.resolve_benchmark` function and the missing `BACKTEST_*`/`FORWARD_*` config settings belong to an unmerged branch or were removed on purpose. Until this is answered, no test of C07 can run regardless of how it is written [S12].

Recommendation: treat a gap as closed only when all of the following hold, since a partial fix can look done without being safe to build on:

- the new or changed test exercises the real function or script named in its task, not a fake standing in for it, closing the specific "tests that prove little" case it targets;
- a known-answer check is itself checked against a hand-computed value, not only run once to see that it currently passes;
- the test runs under whichever single convention U01 settles on, not a second convention nobody runs;
- the flow's row in [09-test-exposure-map.md](09-test-exposure-map.md) is updated to its new test result once the work lands.

Recommendation: the survey's own readiness rule (Surveyor rules section 12) gives the project-wide exit condition: every High- and Medium-importance capability's test-result obligation (`O-C0*-test` in `obligations.md`) is `answered` or `accepted gap`, not `partial` or `unknown`. At the time of writing, `O-C01-test` is `partial` and `O-C07-test` is `unknown` [obligations.md], which is why F001 and F004 lead the priority list above.

## Tooling already in the repository

- Two assertion styles exist side by side: 10 files define their own copy of a `check(name, cond)` helper that prints PASS or FAIL, and 1 file, `test_forward_signals.py`, uses 18 pytest-style `def test_` functions instead [inventory]. Across all 11 test files, 24 pytest-style functions and 421 `check()` lines exist in total [inventory, 09-test-exposure-map.md].
- No `pytest.ini`, `conftest.py`, `tox.ini` or `setup.cfg` exists at the repository root, so no file declares how these tests are meant to be run or collected [inventory].
- `.pytest_cache/` exists in the repository, which shows `pytest` has been run here at least once, though not which files or with what result [inventory, 08-developer-onboarding.md].
- No CI or pipeline file exists: `.github/`, `.gitlab-ci.yml`, `Jenkinsfile` and `azure-pipelines.yml` were all searched for and not found at the root, and neither was a `Dockerfile` [inventory]. No test currently runs automatically on any trigger.
- `requirements.txt` lists the packages the project's own code needs (`pandas`, `numpy`, `requests`, `openpyxl`, `xlrd`, `pdfplumber`, `xlwt`, `python-docx`); it does not list `pytest` or any other test-only package [inventory].

## Recommendations

Recommendation: adopt `pytest` as the single way to run every test file. It is already partly in use (`test_forward_signals.py`, and the `.pytest_cache/` evidence that it has run here before), and it can collect both the existing `def test_` functions directly and a thin `def test_x(): assert main_check_function()` wrapper around each file's existing `check()` calls, without rewriting the 421 existing assertion lines.

Recommendation: add a `pytest.ini`, or a `[tool.pytest.ini_options]` section in a new `pyproject.toml`, that names the test file pattern and the Python version the project expects. This would close part of U01 and U05 at the same time, since neither is declared anywhere today.

Recommendation: add `pytest` to `requirements.txt`, or to a separate `requirements-dev.txt`, since it is not listed today even though its cache file shows it is already being used.

Recommendation: add one CI workflow file that runs the test suite on every push, once U01 settles which command that is. No CI exists today, so nothing currently prevents a change from breaking a well-tested flow unnoticed before it is committed.

Recommendation: for each Level 3 gap this plan lists, add one fixture built from a real, sanitised sample of the external input, such as a CDSL PDF with personal numbers replaced, a real NSE TRI CSV export, or a cached AMC disclosure page, rather than a synthetic one alone, following rules section 1's rule against personal data in any output. A synthetic fixture already proves the parsing logic is internally consistent; only a real sample proves that logic matches what the outside system actually sends.

Recommendation: resolve U13, U14 and U26 before investing further test-writing effort in C01 and C07. A test written against a `weights.ini` contradiction, or against a back-test module that cannot run, would need to be rewritten once the contradiction is resolved, rather than being usable work today.

## Unknowns and next probes

| ID | Question | Why it matters here |
|---|---|---|
| U01 | Which tests does the owner actually run: pytest, or each test file as a script? | Decides the single convention this plan's entry and exit criteria, and its tooling recommendations, should standardise on. |
| U11 | Is there any test that checks `calculate_cagr`, `calculate_volatility` or `calculate_sip_xirr` against a known answer? | The Level 1 gap behind the highest-importance capability's priority ranking. |
| U13 | Does the test suite pass today? Five assertions expect `weights.ini` values the current file does not have. | An entry criterion: a new test built on top of an unresolved contradiction inherits it. |
| U15 | Does any test exercise the real `report.export_to_excel` or `report_md.explain`? | A named Level 3 gap behind C01's priority ranking. |
| U17 | Is `manifest.py` used by anything, and is the missing `MANIFEST_JSON` setting a sign that `config.py` predates the back-test code? | Part of the same drift as U26, behind C07's priority ranking. |
| U18 | What happens at a real run when AMFI blocks the `NAVAll.txt` download or changes its layout again? | A Level 3 gap for C02 not yet covered by any task in [11-developer-testing-tasks.md](11-developer-testing-tasks.md). |
| U20 | Do the hardcoded A4 column positions in `cdsl_holdings_to_xls.py` work for every CDSL statement layout? | Decides when Task 1's Level 3 coverage can be called complete. |
| U21 | Is there a reason no tests exist for the CDSL conversion script? | Context for why the highest-priority gap in this plan exists at all. |
| U22 | Does `test_check_fund.py` still reflect production if `BENCHMARK_ENABLED` or `PORTFOLIO_QUALITY_ENABLED` are `True`? | The one blind spot in an otherwise well-tested, High-importance flow. |
| U23 | Do the three AMC picker regexes still match the AMC websites today? | Explains why this plan's Level 3 recommendation for C05 favours a cached page sample over a live-page test. |
| U24 | How consistent are industry names across real AMC workbooks? | The one gap in an otherwise well-tested flow (F015). |
| U25 | Does `import_tri.py`'s own CSV parsing handle all the NSE download formats in use? | The Level 3 gap behind F009's priority ranking. |
| U26 | Are the missing helper functions, config settings and `benchmark.resolve_benchmark` function from an unmerged branch, or were they removed? | An entry criterion: blocks any new test of C07 until answered. |
| U27 | Is the 0.3-second sleep between mfapi.in calls sufficient to avoid rate-limiting, and does the cache logic handle concurrent runs? | A Level 3 gap shared by every flow that depends on `fetch_nav_data.py`. |

## Related documents

- [09-test-exposure-map.md](09-test-exposure-map.md): the per-flow test results this plan is built on
- [10-test-review.md](10-test-review.md): the ranked risk table behind the priority order above
- [11-developer-testing-tasks.md](11-developer-testing-tasks.md): the concrete tasks for the top 5 priority rows
- [04-shortlist-and-rank.md](04-shortlist-and-rank.md): the core capability most affected by the entry-criteria contradictions (U13, U14)
