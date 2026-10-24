# Capabilities and slice plan

Commit ef2fb5a · Surveyor 2.2.0 · 2026-10-24

Capability names and importance confirmed by the human: yes, product owner, 2026-10-24 (C03 raised from Medium to High by the owner)

Importance ratings are `inferred` from what the module docstrings say each script does (first 22 lines of each entry-point file were opened for grouping). No person has stated them.

## Capabilities

| ID | Name (business words) | Importance | Why this importance | Entry points | Supporting code |
|---|---|---|---|---|---|
| C01 | Shortlist and rank funds in a category | High | This is the project's stated purpose: choosing funds to invest money in. The ranking decides which funds are considered. | E001 | `fund_universe.py`, `fetch_nav_data.py`, `metrics.py`, `extra_metrics.py`, `benchmark.py`, `portfolio_quality.py`, `data_checks.py`, `fund_filters.py`, `scoring.py`, `weights_loader.py`, `weights.ini`, `config.py`, `report.py`, `report_md.py`, `manifest.py`, `logutil.py` |
| C02 | Screen funds you already hold | High | Says whether to keep holding each fund in the owner's real holdings, so it affects money already invested. | E005, E006 | `mf_holdings_screener.py` (also entry), `cdsl_holdings_to_xls.py` (also entry), `metrics.py`, `benchmark.py`, `scoring.py` |
| C03 | Check one fund | High | A single-fund report with a screen result. Rated High by the product owner, 2026-10-24. | E003 | `check_fund.py`, `report_md.py`, `report_docx.py`, `metrics.py`, `benchmark.py`, `scoring.py` |
| C04 | Rank funds from a supplied metrics file | Medium | Reuses the scoring engine on numbers the owner supplies; no internet. Used to run the scoring specification on its own. | E002 | `rank_funds.py`, `scoring.py`, `weights_loader.py` |
| C05 | Collect fund portfolio files and score portfolio quality | Medium | Feeds one of the scored metrics (portfolio quality) with disclosed holdings; wrong parsing would shift scores. | E007, E008, E010, E015 | `amc_registry.py`, `holdings_fetch.py`, `holdings_import.py`, `portfolio_quality.py`, `build_marketcap.py` |
| C06 | Provide benchmark index history | Medium | Benchmark-relative metrics (excess return, rolling beat) depend on it; a real index history replaces a proxy. | E009 | `import_tri.py`, `benchmark.py` |
| C07 | Back-test the forward signals | Medium | Tests whether a signal earned a weight; it informs `weights.ini` but does not rank funds itself. | E004 | `backtest.py`, `forward_signals.py` |
| C08 | Set up, refresh data and diagnose | Low | Housekeeping scripts: download NAV history, check live services, debug a parsing problem, patch a report format. | E011, E012, E013, E014 | `fetch_nav_data.py` (also a library), `live_check.py`, `apply_docx_patch.py`, `navall_diag.py` |

## Flows

One flow per entry point for now. Command-line modes found in the usage text (for example several categories, `--all-categories`, `--refresh`, `--list`) are not yet confirmed in code; `/survey-4-read` will split flows where the code shows separate paths.

| Flow | Capability | Entry point | Business name |
|---|---|---|---|
| F001 | C01 | E001 | Shortlist and rank funds for one or more categories |
| F002 | C04 | E002 | Rank funds from a metrics CSV |
| F003 | C03 | E003 | Report on one fund |
| F004 | C07 | E004 | Back-test forward signals for a category |
| F005 | C02 | E005 | Screen holdings and say keep or review |
| F006 | C02 | E006 | Convert a CDSL statement PDF to holdings spreadsheets |
| F007 | C05 | E007 | Download newest portfolio files from fund houses |
| F008 | C05 | E008 | Sort and check downloaded portfolio files |
| F009 | C06 | E009 | Import index (TRI) history as a benchmark |
| F010 | C05 | E010 | Build the AMFI large/mid/small company list |
| F011 | C08 | E011 | Download and cache NAV history for scheme codes |
| F012 | C08 | E012 | First-run check against the live services |
| F013 | C08 | E013 | Patch the Word report format into check_fund.py |
| F014 | C08 | E014 | Diagnose AMFI NAVAll parsing |
| F015 | C05 | E015 | Debug portfolio-quality parsing for a holdings folder |

## Slice plan

High-importance capabilities first. At most 6 flows per slice. All slices are read by `/survey-4-read`, five per run.

| Slice | Capability | Flows | Question | Files to open | Related tests | Status |
|---|---|---|---|---|---|---|
| S01 | C01 | F001 | How does `shortlist.py` pick candidate funds, apply the hard filters and drive the whole run? | `shortlist.py`, `fund_universe.py`, `fund_filters.py`, `config.py` | `test_pipeline.py` | read |
| S02 | C01 | F001 | How are the per-fund metrics computed (returns, risk, rolling, SIP, benchmark-relative, downside capture)? | `metrics.py`, `extra_metrics.py`, `benchmark.py`, `fetch_nav_data.py` | `test_metrics_window.py`, `test_new_metrics.py`, `test_benchmark.py` | read |
| S03 | C01 | F001 | How are funds scored and ranked, and how do weights, missing data and low confidence behave? | `scoring.py`, `weights_loader.py`, `weights.ini`, `data_checks.py` | `test_scoring.py` | read |
| S04 | C01 | F001, F003 | What do the reports and run records contain, and how are the files written? | `report.py`, `report_md.py`, `report_docx.py`, `manifest.py`, `logutil.py` | `test_pipeline.py` | read |
| S05 | C02 | F005 | How does the holdings screener map ISINs, compute metrics, rank against peers and reach a keep or review verdict? | `mf_holdings_screener.py` (976 lines, read in parts) | `test_mf_holdings_screener.py`, `test_screener_peers.py` | read |
| S06 | C02 | F006 | How is the CDSL PDF turned into holdings spreadsheets, and how does the OCR fallback work? | `cdsl_holdings_to_xls.py` (1,174 lines, read in parts) | none found (searched `cdsl` across `test_*.py`) | read |
| S07 | C03 | F003 | How does the single-fund check build its report, peer comparison and screen result? | `check_fund.py`, `test_check_fund.py` | `test_check_fund.py` | read |
| S08 | C04 | F002 | How does the metrics-CSV ranking read its input and what does it reject? | `rank_funds.py`, `test_rank_funds.py` | `test_rank_funds.py` | read |
| S09 | C05 | F007, F008, F010 | How are portfolio files fetched, sorted by fund house and checked, and how is the market-cap list built? | `holdings_fetch.py`, `holdings_import.py`, `amc_registry.py`, `build_marketcap.py`, `test_portfolio_quality.py` | `test_portfolio_quality.py` | read |
| S10 | C05 | F015 | How is the 0-100 portfolio-quality score built from disclosed holdings? | `portfolio_quality.py`, `test_portfolio_quality.py` | `test_portfolio_quality.py` | read |
| S11 | C06 | F009 | How are benchmark histories imported, checked and chosen (TRI file or proxy)? | `import_tri.py`, `benchmark.py` | `test_benchmark.py` | read |
| S12 | C07 | F004 | How are forward signals defined and back-tested, and what makes a signal "supported"? | `backtest.py`, `forward_signals.py` | `test_forward_signals.py` | read |
| S13 | C08 | F011, F012, F013, F014 | What do the setup and diagnostic scripts do and change? | `fetch_nav_data.py`, `live_check.py`, `apply_docx_patch.py`, `navall_diag.py` | none found by name | read |
| S14 | C01, C02 | F001, F005 | What do the sample run output (`out_smallcap/`) and the owner's review spreadsheets contain, and which code wrote them? | `out_smallcap/` files (names and headers only), `my_review.xls`, `mfReview.xls` (headers only), `shortlisted_funds.csv`, `ranked_funds.md` | none | read |

Slices S02 and S05 cover files large enough that they may need a second slice; `/survey-4-read` will split them and record the line ranges read.
