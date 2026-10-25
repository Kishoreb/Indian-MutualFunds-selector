# Documentation check

Readiness: **READY WITH ACCEPTED GAPS**

Commit ef2fb5a · Surveyor 2.2.0 · 2026-10-25

## Obligations

| Status | Count |
|---|---|
| answered | 71 |
| not-applicable | 0 |
| accepted gap | 13 |
| partial | 0 |
| unknown | 0 |
| open | 0 |

## What blocks readiness

<Empty. All 13 obligations found partial or unknown were accepted as known gaps by the product owner, 2026-10-25, during this check. No unfixed findings remain.>

## Accepted gaps

| Obligation | What is missing | Accepted by (role, date) | Listed in document |
|---|---|---|---|
| O-06-01 | No file declares the intended Python version (U05) | product owner, 2026-10-25 | 06-runtime-and-deployment.md, "Stack and versions"; unknown U05 |
| O-06-06 | No deployment target or CI/CD found; whether the tracked review spreadsheets hold real personal data, and whether the repository is pushed to a remote, is unanswered (U19, U28) | product owner, 2026-10-25 | 06-runtime-and-deployment.md, "Deployment targets and environments"; unknowns U19, U28 |
| O-08-03 | No file or confirmation says whether tests run as `pytest` or as scripts (U01) | product owner, 2026-10-25 | 08-developer-onboarding.md, "Running the tests"; unknown U01 |
| O-08-05 | Troubleshooting content is code-derived only; no interview has been recorded | product owner, 2026-10-25 | 08-developer-onboarding.md, "Troubleshooting" |
| O-C01-alt | The `--fetch-holdings` alternative path for C01 was not fully traced | product owner, 2026-10-25 | 03-request-to-response-flow.md, C01 "Alternative flows" |
| O-C01-exc | C01's exception flows cover portfolio-quality failure only at the generic "metric returns None" level, not S10's specific reason strings | product owner, 2026-10-25 | 03-request-to-response-flow.md, C01 "Exception flows" |
| O-C01-rules | C01's business rules cover portfolio quality at a summary level, not S10's full sub-criterion detail | product owner, 2026-10-25 | 04-shortlist-and-rank.md, "Portfolio quality" |
| O-C01-test | C01's core metrics (CAGR, volatility, SIP XIRR) have no known-answer test, and the `weights.ini`/test contradiction (U10, U11, U13, U15) is unresolved | product owner, 2026-10-25 | 04-shortlist-and-rank.md, "Risks"; tracked as Task 2 in 11-developer-testing-tasks.md |
| O-C07-main | `backtest.py` cannot run: calls `benchmark.resolve_benchmark`, which does not exist, and references undefined config settings (U26) | product owner, 2026-10-25 | 03-request-to-response-flow.md, C07 "Main flow" |
| O-C07-alt | C07's alternative flows cannot be verified at runtime (U26) | product owner, 2026-10-25 | 03-request-to-response-flow.md, C07 "Alternative flows" |
| O-C07-exc | C07's exception flows cannot be verified at runtime (U26) | product owner, 2026-10-25 | 03-request-to-response-flow.md, C07 "Exception flows" |
| O-C07-rules | C07's business-rule thresholds live in config settings that `config.py` does not define (U26) | product owner, 2026-10-25 | 03-request-to-response-flow.md, C07 "Business rules" |
| O-C07-test | `test_forward_signals.py` cannot run: it imports helpers that do not exist in `test_pipeline.py` (U26) | product owner, 2026-10-25 | 09-test-exposure-map.md, C07; tracked as Task 3 in 11-developer-testing-tasks.md |

## Findings by check

| Check | Findings | Fixed | Open |
|---|---|---|---|
| 1. Obligations | 13 | 13 (accepted as known gaps) | 0 |
| 2. Contradictions between documents | 0 | 0 | 0 |
| 3. Evidence lines | 3 | 3 | 0 |
| 4. Citations | 0 | 0 | 0 |
| 5. Paths | 0 | 0 | 0 |
| 6. Quote sample (10 quotes) | 0 (12 re-checked, favouring High-importance slices) | 0 | 0 |
| 7. Absence claims | 2 | 2 | 0 |
| 8. Running behaviour | 0 | 0 | 0 |
| 9. Writing style | 0 | 0 | 0 |

## Details

**Check 1, Obligations.** `obligations.md`'s summary listed 12 `partial` and 1 `unknown` obligation (13 total): O-06-01, O-06-06, O-08-03, O-08-05, O-C01-alt, O-C01-exc, O-C01-rules, O-C01-test, O-C07-main, O-C07-alt, O-C07-exc, O-C07-rules, O-C07-test. Shown to the product owner, who chose to accept all 13 as known gaps rather than commission more reading or an interview first. Recorded as `accepted gap, product owner, 2026-10-25` in `obligations.md`; see "Accepted gaps" above.

**Check 3, Evidence lines.** Compared each document's evidence line against the unique unknown IDs actually listed in its own "Unknowns and next probes" table:
- `01-overview.md` claimed 9 open unknowns; the table lists 7 distinct IDs (U10, U13, U14, U19, U26, U28, U29). Fixed: changed to 7.
- `04-shortlist-and-rank.md` claimed 14 open unknowns; the table lists 9 distinct IDs (U10, U11, U12, U13, U14, U15, U17, U24, U26). Fixed: changed to 9.
- `02-module-architecture.md`'s evidence line had no open-unknowns count at all, though its body lists 3 (U01, U17, U26). Fixed: added "3 open unknowns" to the evidence line.
- The other 9 documents' stated counts matched their tables exactly (03: 14, 05: 15, 06: 5, 07: 5, 08: 7, 09: 11, 10: 14, 11: 9, 12: 14); no change needed.

**Check 2, Contradictions between documents.** Compared: capability names and importance ratings across `01-overview.md`, `03-request-to-response-flow.md` and `09-test-exposure-map.md` (all 8 capabilities match); the 15 entry points in `05-api-reference.md` against the inventory's count of 15 (match, E001-E015 all present); stack and version statements in `01-overview.md`, `02-module-architecture.md` and `06-runtime-and-deployment.md` (pandas>=2.2 pinned, other packages unpinned, Python version undeclared, U05, consistent in all three); the 5 tasks in `11-developer-testing-tasks.md` against the risk scores in `10-test-review.md` (F006 score 9, F001/F004 score 6, F007-F010/F009 score 4, all match). No disagreement found.

**Check 4, Citations.** All 14 slice files (S01.md-S14.md) referenced by `[Sxx]` citations exist in `docs/_evidence/slices/`. No citation used a slice or flow number outside S01-S14 or F001-F015. The `I1`/`I2` intent citations in `01-overview.md` resolve to README.md quotes recorded in `doc-diff.md`. No interview citations exist yet, consistent with no `interviews/` folder being present.

**Check 5, Paths.** Extracted every backtick-quoted file-like path across all 12 documents and checked each against the repository. All existing source, test and configuration files named (`shortlist.py`, `cdsl_holdings_to_xls.py`, `weights.ini`, and so on) exist. Paths named as absent (`pytest.ini`, `conftest.py`, `setup.py`, CI files, and the three new test files `11-developer-testing-tasks.md` proposes) are correctly framed as absent or proposed, not as existing. Paths describing declared output or cache locations (for example `data/amfi_market_cap.csv`, `data/NAVAll.txt`) are framed as what the code writes or reads, not as a claim that the file currently exists on disk. All relative Markdown links between the 12 documents resolve to a real file in `docs/`.

**Check 6, Quote sample.** Re-checked quotes from S01, S02, S03, S04, S05, S06, S07, S09, S11 and S12 (favouring the High-importance C01, C02 and C03 capabilities), plus two further line references in `11-developer-testing-tasks.md`'s Task 1. All 12 matched the source file exactly or within the 5-line drift allowance. No quote failed; no slice reverts to `not read`.

**Check 7, Absence claims.** `02-module-architecture.md` stated twice ("No caller found at this commit" in the module table; "no caller was found" in the dependency-diagram caption) that nothing calls `manifest.py`, without restating the search boundary inline, even though the boundary is recorded in slice S04 (`manifest` searched across `*.py` at the repository root) and in `10-test-review.md`. Fixed: both sentences now name that boundary inline. All other absence and "not tested" claims sampled already stated a boundary at the point of the claim (for example, the CDSL test search in `09-test-exposure-map.md` and the disabled-test search in `10-test-review.md`).

**Check 8, Running behaviour.** Searched for claims about production state, performance, schedules or deployment stated as `observed` fact. None found. `06-runtime-and-deployment.md` and `08-developer-onboarding.md` label the `pip install` step and the Python version `inferred`, not observed. `07-error-handling-and-observability.md` uses `not observed` for exit codes that were not found. The one "in production" phrase, in `open-questions.md`'s U22, poses it as a conditional question, not an observed fact.

**Check 9, Writing style.** Scanned all 12 documents for em/en dashes, inflated words, "not X but Y" contrasts, staged openers, chatbot leftovers, sales language, forced lists of three, vague links, decorative "-ing" riders and Title Case headings. No instance found. The one hit for "underscore" (in `04-shortlist-and-rank.md`) refers to the `_` character in a Python name, not the figurative verb, so it is not a finding.

## Fixes made

1. `01-overview.md`: evidence line's open-unknowns count corrected from 9 to 7.
2. `04-shortlist-and-rank.md`: evidence line's open-unknowns count corrected from 14 to 9.
3. `02-module-architecture.md`: evidence line now states "3 open unknowns" (previously omitted).
4. `02-module-architecture.md`: both absence claims about `manifest.py` having no caller now name the search boundary (`manifest` across `*.py` at the repository root) inline.
5. `obligations.md`: 13 obligations (O-06-01, O-06-06, O-08-03, O-08-05, O-C01-alt, O-C01-exc, O-C01-rules, O-C01-test, O-C07-main, O-C07-alt, O-C07-exc, O-C07-rules, O-C07-test) changed from `partial`/`unknown` to `accepted gap`, recorded as `product owner, 2026-10-25`; summary counts updated accordingly.
