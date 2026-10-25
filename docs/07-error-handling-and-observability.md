# Error handling and observability

Audience: a developer who needs to know how a run fails, what a run's exit code and log mean, and how to tell whether the live data sources are reachable.

Evidence: 15 of 15 entry points read · 8 capabilities · 5 open unknowns · commit ef2fb5a · Surveyor 2.2.0 · 2026-10-24

Every entry point is a single command that starts, does its work, prints to the screen, and exits. None of them is a server, so there is no request to trace and no uptime to watch; "observability" here means the exit code, the printed and written log, and the one script built to check whether the external services the toolkit depends on are reachable [inventory].

## Error and exception patterns

Three patterns repeat across the codebase.

#### Fail fast with a message, before any work starts

Several entry points check their arguments and configuration first and stop immediately if something is wrong, using Python's `sys.exit(<text>)`, which prints the text to standard error and exits with status 1:

- `mf_holdings_screener.py:274` - `sys.exit("No header row with an 'ISIN' column was found - is this the mutual fund holdings file?")` (checked) [S05/F005]
- `mf_holdings_screener.py:955` - `sys.exit("AMFI NAVAll.txt had no scheme rows - is it the right file?")` (checked) [S05/F005]
- `cdsl_holdings_to_xls.py:624` - `sys.exit("No holding rows were found. Try --force-ocr, a higher --dpi, or --pages.")` (checked) [S06/F006]
- `cdsl_holdings_to_xls.py:940` - `sys.exit("Writing .xls needs xlwt:  pip install xlwt     (or use an output name ending in .xlsx)")` (checked) [S06/F006]
- `import_tri.py:65` - `print("ERROR: give --category and at least one input file (or use --list)", file=sys.stderr)` (checked), followed by an exit [S11/F009]
- `build_marketcap.py:112` - `print(f"ERROR: cannot read {a.input}: {exc}", file=sys.stderr)` (checked) [S09/F010]

`shortlist.py` and `rank_funds.py` use named exceptions for the same purpose instead of calling `sys.exit` directly: a bad weights file raises `weights_loader.WeightsError`, which the entry point catches and turns into exit code 2.

- `weights_loader.py:38` - `raise WeightsError(f"Weights file not found: {path}")` (checked) [S03/F001]
- `shortlist.py:333` - `except weights_loader.WeightsError as exc:` (checked) [S01/F001]
- `rank_funds.py:167` - `raise InputError("the file needs a fund_name column (or scheme_name)")` (checked) [S08/F002]

`check_fund.py` has its own `FundLookupError` for a fund that cannot be found or is ambiguous, caught in the same way and turned into exit code 2 [S07/F003].

#### Never raise for missing data: return an empty value with a reason instead

`metrics.py`, `benchmark.py` and `portfolio_quality.py` all follow this rule when a fund's history is too short, a benchmark cannot be resolved, or a portfolio statement cannot be scored: the function returns `None` (or a dictionary of `None` values) rather than raising, so one fund's thin data cannot stop a run that is ranking sixty funds.

- `benchmark.py:95` - `except Exception as exc:  # never let a benchmark failure abort the run` (checked) [S02/F001]
- `portfolio_quality.py:351` - `out["pq_note"] = "no holdings file matched this scheme"` (checked) [S10/F015]
- `portfolio_quality.py:181` - `return None, f"weights sum to {total:.1f}%, not ~100%"` (checked) [S10/F015]

#### Catch the one exception a missing optional library would raise

Three entry points depend on an optional package and catch its absence by name instead of letting the process crash:

- `report.py:42` - `except ImportError:` (checked), when `openpyxl` is missing; `shortlist.py` prints a message and the run continues without the Excel file [S04/F001]
- `report_docx.py:92` - `raise DocxUnavailable("python-docx is not installed. Run:  pip install python-docx")` (checked), caught at `check_fund.py:522` - `except report_docx.DocxUnavailable as exc:` (checked); a warning is printed and no Word file is written, but the run does not stop [S04/F003, S07/F003]
- `cdsl_holdings_to_xls.py:600` - `sys.exit("This PDF page has no text layer, so OCR is needed:\n"` (checked), when `pytesseract` is not installed and OCR is actually needed [S06/F006]

Two scripts are the exception to "never crash": `navall_diag.py` and, for a file that does not match the text it expects, `apply_docx_patch.py`. Both are one-off diagnostic or migration tools, read in S13, where an unhandled traceback is treated as diagnostic information for the person running it rather than a fault to guard against [S13/F013, S13/F014].

## Exit codes and status mappings

Every entry point is a Python process, so its only outward status is its exit code. Seven of the fifteen use both a 1 and a 2 (success is then an implied 0): `shortlist.py`, `rank_funds.py`, `check_fund.py`, `holdings_import.py`, `import_tri.py`, `build_marketcap.py` and `apply_docx_patch.py`. The rest either stop only with `sys.exit` at status 1, have no numbered codes at all, or are debugging aids with no defined contract.

| Entry point | 0 | 1 | 2 | Evidence |
|---|---|---|---|---|
| `shortlist.py` (E001) | ranked and reports written | nothing could be ranked | bad weights, bad `--rolling-years`, bad `--as-of-date`, missing CSV, unrecognised or no category | [S01/F001] |
| `rank_funds.py` (E002) | done | nothing could be ranked | bad command line, weights file or input file (9+ specific `InputError` cases) | `rank_funds.py:52` - `Exit status: 0 done; 1 nothing could be ranked; 2 bad command line, weights file or input file.` (checked) [S08/F002] |
| `check_fund.py` (E003) | report written | fund found but NAV data could not be fetched | bad command line, bad weights file, fund not found or ambiguous, AMFI file unavailable | `check_fund.py:37` - `Exit status: 0 report written; 1 the fund was found but its NAV data could not be fetched;` (checked) [S07/F003] |
| `backtest.py` (E004) | not observed | not observed | not observed | No numbered exit codes were found; the script exits early without a crash for no query, no candidates, too few funds or no usable dates, but cannot run at all today (see Known risk, below) [S12/F004] |
| `mf_holdings_screener.py` (E005) | implied default | the four stop conditions, each a `sys.exit(text)` call, which exits at status 1 | not used | The script defines no numbered exit codes of its own [S05/F005] |
| `cdsl_holdings_to_xls.py` (E006) | implied default | no holding rows, missing OCR support, missing writer library (all via `sys.exit`) | not used | [S06/F006] |
| `holdings_fetch.py` (E007) | not observed | not observed | not observed | No exit codes defined; the `main` block does not return a status. A failed page load or download prints a message per AMC and moves to the next one [S09/F007] |
| `holdings_import.py` (E008) | after import | nothing was imported | no files given and no `--check` | [S09/F008] |
| `import_tri.py` (E009) | success | fewer than 250 usable rows after merging | missing `--category`, no input files, unknown category, unreadable input | [S11/F009] |
| `build_marketcap.py` (E010) | success | no ISIN + category rows found | input file cannot be read or is an unsupported type | [S09/F010] |
| `fetch_nav_data.py` (E011) | implied default | no scheme codes given on the command line | not used | [S13/F011] |
| `live_check.py` (E012) | no step failed | at least one of the six guarded steps reported FAIL | not used | `live_check.py:167` - `fails, warns = results.count("FAIL"), results.count("WARN")` (checked) [S13/F012] |
| `apply_docx_patch.py` (E013) | all four files patched | at least one file's expected text was not found (FAIL) | `report_docx.py` is missing | [S13/F013] |
| `navall_diag.py` (E014) | not observed | not observed | not observed | No exit codes; a missing file or import error raises an unhandled exception, which is the intended behaviour for this diagnostic [S13/F014] |
| `portfolio_quality.py` debug CLI (E015) | implied default (no `sys.exit` call found) | not used | not used | A debugging aid: it only prints scores and reasons, and the underlying `fields_for_fund` never raises [S10/F015] |

Below the process exit code, four modules keep their own status vocabulary that the exit code does not show:

- **Ranking status**, set by `scoring.py` and reused by `shortlist.py` and `rank_funds.py`: `RANKED` or `INSUFFICIENT_DATA` per fund, and a group `confidence` of `OK` or `LOW (only N ranked, need M+)` [S03/F001].
  - `scoring.py:106` - `insufficient = coverage + eps < min_coverage` (checked)
  - `scoring.py:129` - `scored["confidence"] = "OK" if n_ranked >= min_group_size else f"LOW (only {n_ranked} ranked, need {min_group_size}+)"` (checked)
- **Screen verdict**, produced by `mf_holdings_screener.decide` and reused by `check_fund.py`: `CONTINUE`, `CONTINUE - WATCH`, `REVIEW`, or `INSUFFICIENT DATA`, with a confidence of High, Medium or Low [S05/F005, S07/F003].
- **Diagnostic step result**, in `live_check.py`: `PASS`, `WARN` or `FAIL` per step, printed and counted [S13/F012].
- **Data-quality flags**, from `data_checks.py`, attached to a fund row without removing it: duplicate names, a stale NAV, a category that differs from the group's most common one, and CAGR figures computed on too little history [S03/F001].

## Logging and correlation

Each run is one process working on one request from the command line, so there is nothing to correlate across requests; no entry point generates or prints a run ID, a request ID or a trace ID in the files read. The record of what one run did is the log it prints and writes for that run alone.

Three different ways of producing that record exist side by side:

1. **`report_md.RunLog`**, used by `shortlist.py` and `rank_funds.py`. Each call to `log.add(text)` both prints the line to the screen as it happens and keeps it; at the end of the run every kept line is written to `run_log.txt` [S04/F001].
   - `report_md.py:46` - `def add(self, text="", echo=True):` (checked) [S04/F001]
   - If the run stops partway through, `run_log.txt` is not written, because it is written last: `shortlist.py:464` - `log.write(log_path)` (checked) [S04/F001]
2. **`logutil.py`**, a thin wrapper over Python's standard `logging` module. Only `backtest.py` and `forward_signals.py` import it; nothing else does.
   - `backtest.py:54` - `from logutil import get_logger, setup_logging` (checked) [S04/F001]
   - `forward_signals.py:38` - `from logutil import get_logger` (checked) [S04/F001]
   - `backtest.py:279` - `log.warning("No usable as-of dates: the funds don't have enough history for this window + horizon. "` (checked) [S12/F004]
3. **Direct `print`**, to standard output for normal messages and to standard error for failures, used by every other entry point: `mf_holdings_screener.py`, `cdsl_holdings_to_xls.py`, `holdings_fetch.py`, `holdings_import.py`, `build_marketcap.py`, `import_tri.py`, `fetch_nav_data.py`, `live_check.py`, `apply_docx_patch.py`, and the `check_fund.py` error path.
   - `check_fund.py:480` - `print(f"ERROR: {exc}", file=sys.stderr)` (checked) [S07/F003]
   - `fetch_nav_data.py:105` - `print(f"  WARNING: could not fetch {code}: {exc}")` (checked) [S13/F011]
   - `apply_docx_patch.py:95` - `print(f"OK    {name} patched (backup: {name}.bak)")` (checked, worded from S13) [S13/F013]

So a script that fails inside `backtest.py` or `forward_signals.py` produces a logging-module record with levels (`warning`, and by implication `info` and `error`), while every other script produces plain printed lines with no level at all; the two styles cannot be filtered or compared the same way. This split was already noted while reading the output step of C01 [S04/F001].

A fourth, unused path exists: `manifest.py` writes a JSON file recording the run's arguments, the whole `config` module, library versions, counts and output files, which would be useful for comparing one run's settings against another. Its only function, `write_manifest`, has no caller anywhere in the `*.py`, `*.md`, `*.ini` or `*.txt` files at the repository root; `shortlist.py` does not call it. The only place it is read is `test_forward_signals.py`, which expects a `config.MANIFEST_JSON` setting that `config.py` does not define (U17).

- `manifest.py:44` - `def write_manifest(path: str, run_info: dict) -> dict:` (checked) [S04/F001]
- `test_forward_signals.py:357` - `manifest = json.load(open(config.MANIFEST_JSON))` (checked) [S04/F001]

## Health checks

There is no running process to probe, so "health check" here means a script a person runs by hand to find out whether the services the toolkit needs are reachable today.

**`live_check.py` (F012)** is that script. It runs six independent steps, each wrapped so that one failing step cannot stop the others from running:

- `live_check.py:40` - `def guarded(step):` (checked) [S13/F012]
- `live_check.py:45` - `except (Exception, SystemExit) as exc:   # a failed check must not stop the others` (checked) [S13/F012]

The six steps are: download the mfapi.in scheme master and check it has 5,000 or more schemes; look up a category and find Direct-Growth candidates; download one fund's NAV history and check how recent it is; resolve a benchmark for every category in `config.BENCHMARKS`; download and parse AMFI's `NAVAll.txt`; and, only with `--holdings`, run the AMC portfolio downloaders [S13/F012]. Each step prints PASS, WARN or FAIL; the process exits 0 if nothing failed and 1 if any step failed [S13/F012].

`live_check.py` is a first-run diagnostic, not a routine or scheduled check: nothing in the files read calls it on a timer [S13/F012]. **`navall_diag.py` (F014)** is a narrower, second-level diagnostic for one specific failure: it is meant to be run when `live_check.py`'s AMFI step fails or finds zero Direct-Growth schemes, and it prints the raw lines and parsed counts that explain why [S13/F014].

No other entry point checks its dependencies before starting; each one simply tries to do its work and reports the specific failure if a download or a file read does not succeed (see Error and exception patterns, above).

## Retries, timeouts and fallbacks

#### Timeouts

Only one explicit network timeout was found in the files read: `fetch_nav_data.py:44` - `resp = requests.get(url, timeout=20)` (checked), a 20-second limit on each mfapi.in request [S13/F011]. No timeout keyword appears in the checked quotes for the AMFI `NAVAll.txt` download in `mf_holdings_screener.py` or the AMC page downloads in `holdings_fetch.py`; whether they rely on the `requests` library default is unknown from the files read.

#### Retries

No automatic retry of the same request was found anywhere in the slices read. A failed download is caught once, reported, and the run moves on:

- `fetch_nav_data.py:105` - `print(f"  WARNING: could not fetch {code}: {exc}")` (checked), inside `fetch_many`, which catches every exception per fund and continues to the next one [S01/F001, S13/F011]
- `holdings_fetch.py:127` - `return f"{amc['name']}: could not load {amc['page_url']} ({exc})"` (checked), printed once, no second attempt [S09/F007]

The nearest thing to pacing rather than retrying is `fetch_nav_data.py:103` - `time.sleep(pause)  # be polite to the free API` (checked), a fixed 0.3-second wait between successive mfapi.in requests in `fetch_many` [S13/F011]. Whether 0.3 seconds is enough to avoid rate-limiting, and how the file-based NAV cache behaves if two entry points are run at the same time, is open (U27).

#### Fallback chains

Three multi-step fallbacks were found, each falling back to a different source rather than retrying the same one:

1. **Benchmark resolution** (`benchmark.BenchmarkProvider._load`): a local TRI CSV in `data/benchmarks/<category>.csv`, written by `import_tri.py`, is tried first; then a pinned AMFI scheme code from `config.BENCHMARKS` (none is pinned today); then auto-discovery of the Direct-Growth index fund with the longest history among up to `config.BENCHMARK_MAX_CANDIDATES` (6) candidates. If none of the three succeeds, benchmark metrics are left `None` rather than the run stopping [S02/F001, S11/F009].
   - `benchmark.py:164` - `print(f"  WARNING: no index-fund proxy found for {spec['label']}; "` (checked) [S02/F001]
2. **AMFI `NAVAll.txt` acquisition** (`mf_holdings_screener.load_navall`, also used by `check_fund.py`): a file given with `--navall`, then a same-day cache, then a download from the first of two AMFI URLs in turn, then the second URL; if every download fails and an older cache file exists, that older cache is used with a message; only if nothing at all is available does the program stop [S05/F005].
   - `mf_holdings_screener.py:246` - `sys.exit(f"Could not get AMFI's NAVAll.txt ({last}).\n"` (checked), the final step after every other option has failed [S05/F005]
3. **CDSL PDF text extraction** (`cdsl_holdings_to_xls.py`): the text layer of a page is used when it has 50 characters or more; otherwise, or when `--force-ocr` is given, the page is rendered as an image and read with Tesseract OCR instead [S06/F006].
   - `cdsl_holdings_to_xls.py:592` - `if not force_ocr and len(pg.chars) >= 50:` (checked) [S06/F006]

A fourth, smaller fallback sits inside the ISIN repair step of the same script: when an OCR-read ISIN fails its check digit, the code tries substituting commonly confused characters (O/0, I/1, S/5, B/8, and others) only until the check digit passes, and picks the reading needing the fewest substitutions when more than one would work [S06/F006].

- `cdsl_holdings_to_xls.py:103` - `CONFUSABLE = {  # OCR look-alikes, used ONLY when the ISIN check digit fails` (checked) [S06/F006]

#### Known risk: a fallback target that does not exist

`backtest.py` calls a function that `benchmark.py` does not define:

- `backtest.py:273` - `label, bench_df, note = benchmark.resolve_benchmark(canonical, nav_data, override=args.benchmark,` (checked) [S12/F004]
- `benchmark.py` (284 lines, read in full): no function named `resolve_benchmark` exists in it (checked) [S12/F004]

So the back-test entry point (E004, F004) would stop with an `AttributeError` before it could reach any of the error handling described above, and `config.py` also does not define the `BACKTEST_*` and `FORWARD_*` settings the same module reads. Whether this is an unmerged branch or a removed feature is open (U26); it affects every failure path, retry and fallback this section would otherwise describe for C07.

## Unknowns and next probes

| ID | Question | Why it matters here |
|---|---|---|
| U17 | Is `manifest.py` used by anything, and is the missing `MANIFEST_JSON` setting a sign that `config.py` is an older copy than the back-test code? | `manifest.py` is the one module built to record a machine-readable audit trail of a run, and nothing calls it. |
| U18 | What happens at a real run when AMFI blocks the `NAVAll.txt` download or changes its layout again? | The holdings screener's and `check_fund.py`'s fallback chain for this file has never been tested against a live failure. |
| U23 | Do the three AMC picker regexes (`pick_nippon`, `pick_dsp`, `pick_baroda`) still match the links on the AMC websites today? | `holdings_fetch.py` prints a message and continues on a mismatch rather than failing loudly; a silent miss would just look like zero new files. |
| U26 | Are the missing `benchmark.resolve_benchmark` function and the missing `BACKTEST_*`/`FORWARD_*` config settings from an unmerged branch, or were they removed? | Decides whether capability C07's failure handling and fallbacks can be exercised at all today. |
| U27 | Is the 0.3-second pause between mfapi.in calls enough to avoid rate-limiting, and does the file cache handle two runs at once? | The only throttling found in the codebase; a rate-limit response would currently be treated the same as any other per-fund download failure. |

## Related documents

- [03-request-to-response-flow.md](03-request-to-response-flow.md): the exception and alternative flows per capability that these error patterns belong to
- [05-api-reference.md](05-api-reference.md): the full exit-code table and parameters for every entry point
- [06-runtime-and-deployment.md](06-runtime-and-deployment.md): the two logging styles noted again here, and the packages each error path depends on
