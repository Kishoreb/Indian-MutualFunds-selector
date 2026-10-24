# Existing documentation comparison

Commit ef2fb5a · Surveyor 2.2.0 · 2026-10-24

## Documents reviewed

| Document | Lines | Type |
|---|---|---|
| `README.md` | 677 | Current README, detailed |
| `HoldingToExcel.md` | 325 | Older version of the README, frozen at an earlier codebase state |
| `mutual_fund_scoring_specification.md` | 208 | The scoring specification that drove the implementation |
| `ranked_funds.md` (root) | 214 | Program-generated run output (2026-10-19) |
| `out_smallcap/ranked_funds.md` | 237 | Program-generated run output (2026-10-22) |
| `run_log.txt` (root) | 119 | Program-generated run log (2026-10-19) |
| `out_smallcap/run_log.txt` | 122 | Program-generated run log (2026-10-22) |

`HoldingToExcel.md` is a copy of an earlier `README.md` that predates `weights.ini`, `scoring.py`, `weights_loader.py`, the holdings screener, `check_fund.py`, `rank_funds.py`, `extra_metrics.py` and most test files. Every contradiction below comes from it. The current `README.md` is largely accurate.

---

## Confirmed

Statements the code slices support.

### From README.md (37 statements)

| # | Statement (paraphrased) | Slice and flow |
|---|---|---|
| 1 | Scores funds on 13 metrics: 1/3/5-year CAGR, volatility, Sharpe-style ratio, Sortino, rolling 3-year positive %, SIP XIRR, max drawdown, benchmark excess return, rolling beat %, portfolio quality, downside capture, quartile consistency, Jensen's alpha, beta | S02/F001, S03/F001 |
| 2 | Weights are in `weights.ini`, an INI file with `[meta]` and `[weights_percent]` sections | S03/F001 |
| 3 | The weights file is validated: must exist, must have both sections, metrics must sum to 100 (tolerance 0.01), no unknown metrics, no negative weights | S03/F001 |
| 4 | Default missing-data policy is `renormalize_available`: score is weighted average over available metrics | S03/F001 |
| 5 | Coverage floor is 70%; below it a fund is listed as `INSUFFICIENT_DATA` | S03/F001 |
| 6 | Low-confidence flag when fewer than 8 funds are ranked | S03/F001 |
| 7 | Hard filters: 3y CAGR ≥ 10%, 5y CAGR ≥ 10%, volatility ≤ 35%, history ≥ 5 years; 1y CAGR and risk-return ratio filters off by default | S01/F001 |
| 8 | Exit codes: 0 = success, 1 = nothing ranked, 2 = bad input/config | S01/F001 |
| 9 | Output files: `shortlisted_funds.csv`, `.xlsx`, `ranked_funds.md`, `run_log.txt` | S01/F001, S04/F001, S14/F001 |
| 10 | Exploratory cross-category list with `--all-categories` | S01/F001 |
| 11 | Default: Direct + Growth plans only; index funds, ETFs and fund-of-funds excluded | S01/F001 |
| 12 | Benchmark priority: local CSV > pinned scheme code > auto-discovered index fund proxy | S02/F001, S11/F009 |
| 13 | Portfolio quality: five sub-criteria (top10_pct, n_holdings, top_sector_pct, largemid_pct, cash_pct) mapped 0-100 | S10/F015 |
| 14 | AMC registry modes: auto (3), manual (12), manual_unconfirmed (3), gated (2), not_found (12) | S09/F007 |
| 15 | CDSL extractor writes two Excel files (stock and MF), validates ISINs by check digit, cross-checks numbers | S06/F006 |
| 16 | Holdings screener verdicts: CONTINUE, CONTINUE - WATCH, REVIEW, INSUFFICIENT DATA | S05/F005 |
| 17 | Screener uses three evidence types: absolute return, benchmark, peers | S05/F005 |
| 18 | `check_fund.py` finds a fund by name or AMFI code, computes metrics vs peers and benchmark, outputs a report | S07/F003 |
| 19 | `rank_funds.py` reads a CSV, validates it, ranks within category, writes CSV + MD + log | S08/F002 |
| 20 | 12 supported categories (small cap through sectoral) | S01/F001 |
| 21 | Data source: AMFI scheme master via mfapi.in, cached for 7 days | S01/F001 |
| 22 | NAV history cached for 1 day | S02/F001 |
| 23 | 60-fund cap per category (alphabetical when exceeded) | S01/F001 |
| 24 | Risk-return ratio: aligned 3-year window by default (`RATIO_ALIGN_WINDOW = True`) | S02/F001 |
| 25 | Max drawdown over a 3-year window (`DRAWDOWN_WINDOW_YEARS = 3.0`), not whole history | S02/F001 |
| 26 | Downside capture and quartile consistency off by default (weight 0) | S03/F001 |
| 27 | Expense ratio deliberately not scored | S03/F001 |
| 28 | Screener peer ranking uses `weights.ini` weights, no hard filters applied | S05/F005 |
| 29 | Portfolio notes: concentration >15%, ≥3 funds in one category, Regular plan, IDCW | S05/F005 |
| 30 | Tests are all offline, synthetic data | S01-S12 (test observations) |
| 31 | `cdsl_holdings_to_xls.py` has no automated tests | S06/F006, U21 |
| 32 | `build_marketcap.py` builds the AMFI large/mid/small company list | S09/F010 |
| 33 | `import_tri.py` imports TRI CSV files and writes `data/benchmarks/<category>.csv` | S11/F009 |
| 34 | `holdings_import.py` sorts files into `data/holdings/<amc>/` and reports scores | S09/F008 |
| 35 | `live_check.py` checks mfapi.in, AMFI and the benchmark proxies | S13/F012 |
| 36 | Data-quality flags: DUPLICATE_CODE, DUPLICATE_NAME, STALE_NAV, INCONSISTENT, CATEGORY_MISMATCH, NO_NAV_DATE | S03/F001 |
| 37 | Jensen's alpha and beta: regression of monthly excess returns on benchmark, need 24+ common months | S02/F001 |

### From mutual_fund_scoring_specification.md (9 statements)

| # | Statement (paraphrased) | Slice and flow |
|---|---|---|
| 38 | Weights must be numeric, non-negative, sum to 100 | S03/F001 |
| 39 | Invalid configuration rejected with a clear error | S03/F001 |
| 40 | No silent replacement with hard-coded weights | S03/F001 |
| 41 | Configuration version and actual weights recorded in output | S04/F001, S14/F001 |
| 42 | Funds ranked within the same category | S01/F001, S03/F001 |
| 43 | Percentile scoring available (now the default) | S03/F001 |
| 44 | Minimum coverage requirement before ranking | S03/F001 |
| 45 | Stale, missing, inconsistent data flagged | S03/F001 |
| 46 | Risk disclaimer included | S04/F001 |

---

## Contradicted

Statements the code does not support. All come from `HoldingToExcel.md`, which is a frozen copy of an earlier README.

| # | Statement in HoldingToExcel.md | What the code does | Evidence | Capability (importance) |
|---|---|---|---|---|
| H1 | "Everything is controlled from `config.py`" for weights | Weights are in `weights.ini`, read by `weights_loader.py`. `config.py` has no `SCORE_WEIGHTS`. | S03/F001: `weights_loader.py:15`, `weights.ini:27` | C01 (High) |
| H2 | "Weights are normalised, so they need not sum to exactly 1" | Weights must sum to exactly 100 (tolerance 0.01); the program refuses to run otherwise. | S03/F001: `weights_loader.py:90` | C01 (High) |
| H3 | "Missing values: scored as average (z = 0)" | Default policy is `renormalize_available`, which rescales over available metrics. `average` is still an option but not the default. | S03/F001: `weights.ini:22`, `scoring.py:106` | C01 (High) |
| H4 | "Not implemented from the spec: percentile scoring, renormalising weights, external weights file, ranked_funds.md / run-log outputs" | All four are now implemented: `scoring_method = percentile`, `renormalize_available`, `weights.ini`, `ranked_funds.md` and `run_log.txt`. | S03/F001, S04/F001 | C01 (High) |
| H5 | `shortlist.py` writes "CSV + Excel" only | `shortlist.py` writes four files: CSV, Excel, `ranked_funds.md` and `run_log.txt`. | S01/F001: `shortlist.py:454`, S04/F001 | C01 (High) |
| H6 | File table lists 12 source files | The repository has 30+ source files, including major modules not listed (weights_loader.py, scoring.py, report_md.py, data_checks.py, fund_filters.py, extra_metrics.py, mf_holdings_screener.py, check_fund.py, rank_funds.py, build_marketcap.py, import_tri.py, holdings_import.py, live_check.py, and 11 test files). | Inventory | C01-C08 (all) |
| H7 | "Tests: test_benchmark.py, test_portfolio_quality.py. Both run offline." (only 2 test files) | 11 test files exist. | Inventory | all |
| H8 | "Max drawdown: largest peak-to-trough NAV decline over the fund's history" | Max drawdown is over a 3-year trailing window (`DRAWDOWN_WINDOW_YEARS = 3.0`). The whole-history number is kept as `max_drawdown_all` but not scored. | S02/F001: `config.py:94` | C01 (High) |
| H9 | Risk-return ratio uses whole-history volatility (no mention of aligned window) | By default, volatility for the ratio is measured over the same 3-year window as the return (`RATIO_ALIGN_WINDOW = True`). | S02/F001: `metrics.py:306` | C01 (High) |
| H10 | `cdsl_holdings_to_xls.py` "is independent of the shortlisting scripts"; no mention of `mf_holdings_screener.py` | The holdings screener is a High-importance capability (C02) that depends on `shortlist.score_and_rank`, `metrics.py`, `benchmark.py`, etc. It is not mentioned in HoldingToExcel.md at all. | S05/F005 | C02 (High) |

---

## Not covered

Statements about areas the slices did not read, or runtime claims that code alone cannot establish (section 2 of the rules). These are marked `unverified`.

| # | Statement | Source file | Why not covered |
|---|---|---|---|
| NC1 | "First live check (Oct 2026): mfapi.in, category lookup, NAV download and all benchmark proxies worked." | README.md | Runtime observation of a live run. Code cannot establish production behaviour. |
| NC2 | "Two warnings: the large & mid cap proxy has only ~4.9 years of history and the multi cap proxy ~2.2 years" | README.md | Runtime observation from one run. |
| NC3 | "Tested on one statement with a text layer (Kiran_2026-06.pdf): 48 stock rows and 75 mutual fund rows, with all totals matching the statement." | README.md | Manual test result. No automated test reproduces it. |
| NC4 | "AMFI's NAVAll.txt had changed: Plan and Option are now separate columns, which parse_navall now reads from the header row" | README.md | External service change, observed at runtime. |

---

## Intent, policy and history

Statements about why something was built or what is forbidden. They cannot come from code. Copied for the Surveyor documents.

| # | Statement | Source file |
|---|---|---|
| I1 | "This is a screening tool, not investment advice — check exit loads, expense ratios, fund manager tenure, portfolio overlap and your own risk profile before investing." | README.md |
| I2 | "Past returns (which is mostly what this measures) don't guarantee future performance. Short horizons (1-3 years) carry substantial equity risk." | README.md |
| I3 | "Expense ratio is deliberately not scored" (excluded on the product owner's request). | README.md |
| I4 | "AI-written summaries are deferred, by decision"; per-fund summaries are rule-based text. | README.md |
| I5 | "`MIN_CAGR_1Y` and `MIN_RISK_RETURN_RATIO` are off by default: after a weak year they removed almost every established small-cap fund (5 of 53 candidates survived the first live run). Both metrics are still scored through `weights.ini`." | README.md |
| I6 | "The thresholds are this toolkit's defaults, not an industry standard — tune them." (about portfolio quality) | README.md |
| I7 | AMC portfolio automation is deliberately limited: gated AMCs behind folio/PAN forms are not automated. | README.md |
| I8 | "Percentile and z-scores are relative to the funds in the run, not an absolute measure of quality or safety." | README.md |
| I9 | "The scoring system below is a starting specification. It is not an official industry standard or investment recommendation." | mutual_fund_scoring_specification.md |
| I10 | "This specification defines the scoring engine, not a guaranteed source of live financial data." | mutual_fund_scoring_specification.md |
| I11 | "It is not just a starting specification" — the README tracks the implementation against the spec in a mapping table, and the spec's role has shifted from "what to build" to "what was asked for". | README.md (the mapping table) |
| I12 | `mf_holdings_screener.py` explicitly states its limits: "This is a rules-based screen of past NAV data, not advice. It does not know your goals, holding period, tax position or exit load, and selling can trigger tax and exit load." | README.md |

---

## Summary

| List | Count |
|---|---|
| Confirmed | 46 |
| Contradicted | 10 |
| Not covered (unverified) | 4 |
| Intent / policy / history | 12 |

All 10 contradictions come from `HoldingToExcel.md`, an orphaned earlier version of the README. Nine of them affect High-importance capabilities (C01, C02). The current `README.md` is accurate on every statement the slices could verify.

### Contradictions on High-importance capabilities

| Capability | Count | Impact |
|---|---|---|
| C01 Shortlist and rank (High) | 9 (H1-H9) | Every scored metric, the scoring method, the missing-data policy, the output files, the file table, the drawdown window, the ratio window, and the test count are wrong in HoldingToExcel.md. Someone following HoldingToExcel.md would expect config.py to hold the weights, would expect missing values to score as average, and would not know about 4 of the 6 output files. |
| C02 Screen funds you hold (High) | 1 (H10) | HoldingToExcel.md does not mention `mf_holdings_screener.py` at all. Someone reading only that file would not know the screener exists. |
| C03 Check one fund (High) | 0 direct, but H6 and H7 apply | `check_fund.py` is not in the HoldingToExcel.md file table or test section. |
