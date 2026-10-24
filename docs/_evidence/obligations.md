# Obligations

Every question the 12 documents must answer for this repository. Commit ef2fb5a · Surveyor 2.2.0 · 2026-10-24

Statuses: `open`, `answered`, `partial`, `unknown`, `not-applicable`, `accepted gap`. See rules section 12. `open`, `partial` and `unknown` never count as done.

Project type is batch / CLI scripts, so the sections follow the batch adaptation in rules section 8. No section is marked not-applicable yet: that needs reading first (for example, whether any script has a health check or a security rule).

## Summary

| Status | Count |
|---|---|
| answered | 50 |
| partial | 10 |
| unknown | 1 |
| not-applicable | 0 |
| accepted gap | 0 |
| open | 23 |

## Document sections

| ID | Document | Required section | Status | Evidence or reason | Accepted by (role, date) |
|---|---|---|---|---|---|
| O-01-01 | 01-overview | What the project does and for whom | answered | 01-overview section 1, citing S01/F001, S02, S05, S06, inventory, I1, I2 | |
| O-01-02 | 01-overview | Capabilities table | answered | 01-overview "Capabilities" table, citing S01-S14 and capabilities.md | |
| O-01-03 | 01-overview | System context diagram | answered | 01-overview Mermaid "System context diagram", citing S01, S02, S05, S06, S09, S13, inventory | |
| O-01-04 | 01-overview | High-level architecture diagram | answered | 01-overview Mermaid "High-level architecture diagram", citing inventory, S01, S03 | |
| O-01-05 | 01-overview | End-to-end flow diagram of the most important capability | answered | 01-overview Mermaid "End-to-end flow: shortlist and rank", citing S01-S04, S14 | |
| O-02-01 | 02-module-architecture | Module layout with responsibilities | answered | 02-module-architecture "Module layout" section: 15 entry points, 16 libraries, 11 tests, 3 config files, all at root. Tables cite inventory, S01-S13. | |
| O-02-02 | 02-module-architecture | Dependency diagram | answered | 02-module-architecture Mermaid "Dependency diagram", citing S01-S13 imports. Dashed lines for non-runnable modules. | |
| O-02-03 | 02-module-architecture | Patterns observed (cited) | answered | 02-module-architecture "Patterns observed" section: 6 patterns, each citing slice evidence (S01-S04, S05, S07, S11, S13). | |
| O-02-04 | 02-module-architecture | Extension points | answered | 02-module-architecture "Extension points" section: 7 change points in table, citing S01, S03, S09, S10, S11. No plugin/hook system. | |
| O-02-05 | 02-module-architecture | Homegrown mechanisms found in the inventory | answered | 02-module-architecture "Homegrown mechanisms" section: 6 mechanisms (check() helper, weights.ini, benchmark auto-discovery, CDSL parser, duplicate rolling-return, forward-signal blend), citing inventory, S01-S03, S06, S12. | |
| O-03-01 | 03-request-to-response-flow | One section per capability with main, alternative and exception flows and business rules | answered | 03-request-to-response-flow: one section per capability (C01-C08), all 15 flows covered, citing S01-S14 | |
| O-03-02 | 03-request-to-response-flow | Flow diagram for each High-importance capability | answered | 03-request-to-response-flow: Mermaid diagrams for C01 (shortlist pipeline), C02 (CDSL + screener), C03 (check_fund pipeline) | |
| O-04-01 | 04-shortlist-and-rank | Interfaces and implementations of the core capability | answered | 04-shortlist-and-rank sections "Interfaces", "Implementations" (entry point, candidate lookup, metric computation, benchmark resolution, portfolio quality, scoring engine, hard filters, data checks, report generation) citing S01-S04, S10, S14 | |
| O-04-02 | 04-shortlist-and-rank | Rules | answered | 04-shortlist-and-rank section "Rules" (shared mutable state, missing data policy, duplicate rolling-return) citing S01-S03 | |
| O-04-03 | 04-shortlist-and-rank | Risks | answered | 04-shortlist-and-rank section "Risks" (alphabetical cap, weights/test contradiction, comment contradiction, no CAGR assertion, benchmark ordering, portfolio quality missing, backtest broken) citing S01-S04, S10, S12, S14, U11-U14, U17, U26 | |
| O-04-04 | 04-shortlist-and-rank | Failure and recovery | answered | 04-shortlist-and-rank section "Failure and recovery" table (8 conditions with exit codes) citing S01-S04, S10 | |
| O-05-01 | 05-api-reference | Every entry point listed (command, parameters) | answered | 05-api-reference: all 15 entry points (E001-E015) with command examples and parameter tables, citing S01-S14 | |
| O-05-02 | 05-api-reference | Inputs and outputs per entry point | answered | 05-api-reference: inputs and outputs sections per entry point, citing S01-S14 | |
| O-05-03 | 05-api-reference | Success and error cases per entry point | answered | 05-api-reference: exit codes tables per entry point (0/1/2 where defined, per-fund failure handling), citing S01-S14 | |
| O-05-04 | 05-api-reference | Security (credentials, data access) | answered | 05-api-reference: security section per entry point covering credentials (none), personal data (E005, E006), public data (all others), citing S01-S14 | |
| O-06-01 | 06-runtime-and-deployment | Stack and versions (cited from build files) | partial | 06-runtime-and-deployment "Stack and versions" section: Python, pandas>=2.2 pinned, other packages named without version pins, citing inventory, S02. Python version itself not declared anywhere (U05). | |
| O-06-02 | 06-runtime-and-deployment | Runtime dependencies | answered | 06-runtime-and-deployment "Runtime dependencies" section: requirements.txt packages plus Tesseract OCR as an external, optional program, citing inventory, S06/F006. | |
| O-06-03 | 06-runtime-and-deployment | Configuration model and keys | answered | 06-runtime-and-deployment "Configuration model and keys" section: config.py (~60 constants, keys listed) and weights.ini ([meta]/[weights_percent] keys and shipped values), citing inventory, S01/F001, S02/F001, S03/F001, S04/F001. | |
| O-06-04 | 06-runtime-and-deployment | Packaging | answered | 06-runtime-and-deployment "Packaging" section: no setup.py/pyproject.toml/Dockerfile/CI files found; pip install hints found in two error messages (inferred), citing inventory, S04/F003, S06/F006. | |
| O-06-05 | 06-runtime-and-deployment | Start commands | answered | 06-runtime-and-deployment "Start commands" section: python <file>.py pattern for all 15 entry points with 5 worked examples, citing inventory, S01/F001, S13. Full list deferred to 05-api-reference.md. | |
| O-06-06 | 06-runtime-and-deployment | Deployment targets and environments | partial | 06-runtime-and-deployment "Deployment targets and environments" section: no deployment target, CI/CD or environment distinction found; local data folder and tracked review spreadsheets flagged as a personal-data exposure risk (U19, U28), citing inventory, S09/F008, S11/F009. | |
| O-07-01 | 07-error-handling-and-observability | Error and exception patterns | open | | |
| O-07-02 | 07-error-handling-and-observability | Exit codes and status mappings | open | | |
| O-07-03 | 07-error-handling-and-observability | Logging and correlation | open | | |
| O-07-04 | 07-error-handling-and-observability | Health checks | open | | |
| O-07-05 | 07-error-handling-and-observability | Retries, timeouts and fallbacks | open | | |
| O-08-01 | 08-developer-onboarding | Repository layout | open | | |
| O-08-02 | 08-developer-onboarding | Prerequisites | open | | |
| O-08-03 | 08-developer-onboarding | How to run locally and run tests | open | | |
| O-08-04 | 08-developer-onboarding | Where to make common changes | open | | |
| O-08-05 | 08-developer-onboarding | Troubleshooting known from code or interviews | open | | |
| O-09-01 | 09-test-exposure-map | Per capability and flow: tests found and test result | open | | |
| O-09-02 | 09-test-exposure-map | Summary counts | open | | |
| O-10-01 | 10-test-review | Strengths | open | | |
| O-10-02 | 10-test-review | Tests that prove little | open | | |
| O-10-03 | 10-test-review | Disabled tests | open | | |
| O-10-04 | 10-test-review | Level-of-test problems | open | | |
| O-10-05 | 10-test-review | Risks ranked by importance times weakness | open | | |
| O-11-01 | 11-developer-testing-tasks | 3 to 5 tasks, highest risk first | open | | |
| O-12-01 | 12-test-plan | Strategy by level | open | | |
| O-12-02 | 12-test-plan | Priority areas from document 10 | open | | |
| O-12-03 | 12-test-plan | Entry and exit criteria | open | | |
| O-12-04 | 12-test-plan | Tooling already in the repository | open | | |
| O-12-05 | 12-test-plan | Recommendations | open | | |

## Capabilities

C08 (Low importance) has no capability obligations. High and Medium capabilities have five each.

| ID | Capability | Required answer | Status | Evidence or reason | Accepted by (role, date) |
|---|---|---|---|---|---|
| O-C01-main | C01 Shortlist and rank funds in a category | Main flow | answered | S01-S04 (F001 traced from command line to output files)
| O-C01-alt | C01 Shortlist and rank funds in a category | Alternative flows | partial | S01: CSV input, several categories, --all-categories and exploratory list read. --fetch-holdings path waits for S09.
| O-C01-exc | C01 Shortlist and rank funds in a category | Exception flows | partial | S01-S04: exit codes, skipped downloads, benchmark failures, weights errors. Portfolio-quality failures wait for S10.
| O-C01-rules | C01 Shortlist and rank funds in a category | Business rules | partial | S01-S03: filters, metric rules, scoring. Portfolio-quality rules wait for S10.
| O-C01-test | C01 Shortlist and rank funds in a category | Test result per flow | partial | S01-S04: tested on the surface; U10, U11, U13, U15 open. S10 adds portfolio-quality test coverage for C01's scoring pipeline.
| O-C02-main | C02 Screen funds you already hold | Main flow | answered | S05 answers F005; S06 answers F006 (CDSL PDF to Excel via text-layer or OCR, ISIN validation, reconciliation).
| O-C02-alt | C02 Screen funds you already hold | Alternative flows | answered | S05: --no-peers, name-match fallback, .xlsx output. S06: --force-ocr, --skip-mf, --pages, password-protected PDFs.
| O-C02-exc | C02 Screen funds you already hold | Exception flows | answered | S05: four stop conditions, per-fund failures. S06: no rows found (exit 1), missing Tesseract, missing writer library, flagged cross-check failures.
| O-C02-rules | C02 Screen funds you already hold | Business rules | answered | S05: all verdict thresholds. S06: ISIN check-digit with OCR confusable repair, qty*price=value (0.02 tolerance), MF triple cross-check, reconciliation against statement totals, hardcoded A4 column positions.
| O-C02-test | C02 Screen funds you already hold | Test result per flow | answered | S05 F005: well tested. S06 F006: not tested (no test file found; U21).
| O-C03-main | C03 Check one fund | Main flow | answered | S07: fund lookup by name or code, peer pool, metrics via shortlist, verdict via mf_holdings_screener.decide, Markdown report.
| O-C03-alt | C03 Check one fund | Alternative flows | answered | S07: --no-peers (benchmark only), --format md, --no-file (print only), --rolling-years, --refresh, --weights.
| O-C03-exc | C03 Check one fund | Exception flows | answered | S07: exit 2 for not found/ambiguous/bad args, exit 1 for NAV failure with INSUFFICIENT DATA, missing python-docx prints warning.
| O-C03-rules | C03 Check one fund | Business rules | answered | S07: stale-twin disambiguation, two-ISIN twin handling, peer pool capped at 60, 16-metric table with direction-aware percentiles, verdict from decide().
| O-C03-test | C03 Check one fund | Test result per flow | answered | S07 F003: well tested (32 checks in test_check_fund.py). Known gap: benchmark and portfolio-quality paths stubbed off in tests (U22).
| O-C04-main | C04 Rank funds from a supplied metrics file | Main flow | answered | S08: reads CSV (spec or toolkit style), validates, ranks per category with scoring.score_and_rank, writes CSV+MD+log.
| O-C04-alt | C04 Rank funds from a supplied metrics file | Alternative flows | answered | S08: --units override, --include-all-plans, --ignore-category, --exploratory cross-category, --category filter, --as-of-date.
| O-C04-exc | C04 Rank funds from a supplied metrics file | Exception flows | answered | S08: exit 2 for 10+ specific InputErrors, exit 1 when nothing ranked, LOW CONFIDENCE for small categories, INSUFFICIENT_DATA per fund.
| O-C04-rules | C04 Rank funds from a supplied metrics file | Business rules | answered | S08: auto-detected column styles, range validation, duplicate handling, plan filter, staleness, expense_ratio excluded by design.
| O-C04-test | C04 Rank funds from a supplied metrics file | Test result per flow | answered | S08 F002: well tested (22 checks). Known gaps: no test for --exploratory or Markdown report content.
| O-C05-main | C05 Collect fund portfolio files and score portfolio quality | Main flow | answered | S09: F007 scrapes 3 auto AMCs, prints manual checklist for 29. F008 sorts by AMC alias, reports scores. F010 builds AMFI market-cap CSV. S10: F015 parses SEBI sheets, computes 5-sub-criterion 0-100 score.
| O-C05-alt | C05 Collect fund portfolio files and score portfolio quality | Alternative flows | answered | S09: named AMCs, --list, --check. S10: fraction-style weights, missing market-cap list (largemid skipped), fuzzy scheme matching.
| O-C05-exc | C05 Collect fund portfolio files and score portfolio quality | Exception flows | answered | S09: failed page/download prints and continues, unrecognised files to unsorted/, bad zips skipped. S10: every failure returns None with reason (few holdings, bad weights, stale, unmatched, low coverage).
| O-C05-rules | C05 Collect fund portfolio files and score portfolio quality | Business rules | answered | S09: picker regexes, magic-byte download validation, longest-alias-wins AMC detection, ISIN+category detection for market-cap. S10: equity ISIN pattern, linear 0-100 mapping with configurable thresholds, coverage floor, staleness check.
| O-C05-test | C05 Collect fund portfolio files and score portfolio quality | Test result per flow | answered | S09: F007 tested on surface (helpers only, no live download; U23). F008 tested on surface (AMC detection, path traversal; import workflow not tested). F010 tested on surface (downstream use only; parsing untested). S10 F015: well tested (35 checks). Known gap: no real AMC workbooks tested (U24).
| O-C06-main | C06 Provide benchmark index history | Main flow | answered | S11: import_tri.py parses CSV(s), merges, validates, writes data/benchmarks/<category>.csv. BenchmarkProvider resolves in priority: local CSV, pinned code, auto-discovery. |
| O-C06-alt | C06 Provide benchmark index history | Alternative flows | answered | S11: --list prints categories and indexes. Auto-discovery selects the longest-history Direct-Growth index fund. |
| O-C06-exc | C06 Provide benchmark index history | Exception flows | answered | S11: exit 2 for bad args/unknown category, exit 1 for <250 rows, warnings for gaps/staleness/short history. Provider catches all exceptions and returns None. |
| O-C06-rules | C06 Provide benchmark index history | Business rules | answered | S11: 250-row minimum, 10-day gap warning, staleness check, 5-year history warning. 11 categories defined in config.BENCHMARKS. Filename convention: spaces->underscores, "&"->"and". |
| O-C06-test | C06 Provide benchmark index history | Test result per flow | answered | S11 F009: tested on the surface (benchmark.py has 41 checks in test_benchmark.py; import_tri.py itself untested, U25). |
| O-C07-main | C07 Back-test the forward signals | Main flow | partial | S12: back-test design fully documented (signal computation, as-of grid, Spearman IC, verdict logic). But backtest.py cannot run: calls benchmark.resolve_benchmark (does not exist) and references undefined config settings. U26. |
| O-C07-alt | C07 Back-test the forward signals | Alternative flows | partial | S12: --horizon, --step-months, --window, --benchmark, --refresh, CSV input documented. Cannot verify at runtime. U26. |
| O-C07-exc | C07 Back-test the forward signals | Exception flows | partial | S12: early exit for no query, no candidates, too few funds, no usable dates. Cannot verify at runtime. U26. |
| O-C07-rules | C07 Back-test the forward signals | Business rules | partial | S12: "supported" (mean IC >= threshold, positive share >= threshold), "inverted" (opposite), "insufficient data" (too few dates). Thresholds in undefined config settings. U26. |
| O-C07-test | C07 Back-test the forward signals | Test result per flow | unknown | S12: 18 test functions exist but test_forward_signals.py cannot run (imports missing helpers from test_pipeline.py). U26. |
