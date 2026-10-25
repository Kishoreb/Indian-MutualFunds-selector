# Developer onboarding

Audience: a developer setting up this repository on a new machine for the first time, who needs to get a script running, run the tests, find where to make a common change, and read the error messages the toolkit prints.
Evidence: 15 of 15 entry points read · 8 capabilities · 7 open unknowns · commit ef2fb5a · Surveyor 2.2.0 · 2026-10-25

This is a local command-line toolkit, not a service: there is nothing to deploy and nothing to keep running [06-runtime-and-deployment.md](06-runtime-and-deployment.md). Onboarding here means installing the right packages and learning which script to run for a given task.

## Repository layout

All 57 tracked files sit at the repository root. There are no subdirectories of source code and no `__init__.py` files [inventory]:

| Group | Count | Examples |
|---|---|---|
| Entry points (CLI scripts) | 15 | `shortlist.py`, `check_fund.py`, `mf_holdings_screener.py` |
| Library modules (no entry point) | 16 | `config.py`, `metrics.py`, `scoring.py`, `benchmark.py` |
| Test files | 11 | `test_scoring.py`, `test_check_fund.py` |
| Configuration files | 3 | `config.py`, `weights.ini`, `requirements.txt` |

Full per-file tables, with line counts and what each file does, are in [02-module-architecture.md](02-module-architecture.md).

Three folders and two files outside this layout matter on a first checkout:

- `data/` is untracked by git. On the machine this survey was done on it holds 121 files: 60 NAV CSVs, 60 matching `_meta.csv` files, and one scheme-master JSON cache [inventory, I007]. A fresh clone will not have this folder.
- `out_smallcap/` is untracked and holds one sample run's output (`ranked_funds.md`, `run_log.txt`, `shortlisted_funds.csv`, `shortlisted_funds.xlsx`), kept as an example of what `shortlist.py` produces [S14, product owner, 2026-10-24].
- `.pytest_cache/` exists in the repository even though no `pytest.ini`, `conftest.py`, `tox.ini` or `setup.cfg` was found at the root. Its presence is evidence that `pytest` has been run here at least once, though not which files or with what result [inventory].
- `my_review.xls` and `mfReview.xls` are tracked by git. They are the product owner's own review of some past runs [product owner, 2026-10-24]. Whether they hold real folio numbers or valuations, and whether this repository is pushed to a remote, is open (U19, U28); treat them as sensitive until that is answered.

Whether `data/` and `out_smallcap/` are meant to stay outside git, and whether the scripts can rebuild `data/` from nothing on a fresh machine, is open (U06).

## Prerequisites

| What | Version or detail | Evidence |
|---|---|---|
| Python | Not declared in any file read. The machine this survey was done on has 3.14.3 installed. | `requirements.txt` lists only packages, no interpreter version [inventory]. Which versions are intended to work is open (U05). |
| pandas | `>=2.2`, pinned | `requirements.txt:1` - `pandas>=2.2` (checked) [inventory]. The pin matters: `metrics.py:65` resamples with the string `"ME"` (month-end), a pandas 2.2 feature [S02]. |
| numpy, requests, openpyxl, xlrd, pdfplumber, xlwt, python-docx | Named, no version pin recorded | `requirements.txt` [inventory] |
| pytesseract | Named in `requirements.txt` but commented out; install it only if the optional OCR path below is needed | `requirements.txt` [inventory] |
| Tesseract OCR | External program, not a Python package. Optional. | Needed only when `cdsl_holdings_to_xls.py` falls back to OCR because a PDF page has no text layer, or when `--force-ocr` is given. Without it, the script stops with `cdsl_holdings_to_xls.py:600` - `sys.exit("This PDF page has no text layer, so OCR is needed:\n...")` (checked) [S06]. If Tesseract is installed but not on the system path, point to it with `--tesseract-cmd`, passed to `pytesseract.pytesseract.tesseract_cmd` (`cdsl_holdings_to_xls.py:1124`, checked) [S06]. |

No `.env` file was found, and no code in the files read reads an environment variable for configuration; all settings are Python constants in `config.py` and `weights.ini` [06-runtime-and-deployment.md](06-runtime-and-deployment.md).

**Recommendation:** install the packages with `pip install -r requirements.txt`. No file in the repository states this exact command; it is the standard way to use a `requirements.txt` file, inferred from two error messages in the code that tell a user to `pip install` a single missing package (`report_docx.py:92`, `cdsl_holdings_to_xls.py:940`, both checked) [06-runtime-and-deployment.md](06-runtime-and-deployment.md).

## Running the project locally

Every entry point is started the same way: `python <file>.py [arguments]`, parsed by `argparse` [inventory]. Five worked examples, taken from each script's own usage text or docstring:

| Script | Example command | Evidence |
|---|---|---|
| `shortlist.py` | `python shortlist.py --category "small cap"` | `shortlist.py:300` [S01] |
| `fetch_nav_data.py` | `python fetch_nav_data.py 120503 118989 100033` | `fetch_nav_data.py:9` [S13] |
| `live_check.py` | `python live_check.py` (optionally `--holdings --category "mid cap"`) | `live_check.py:8` [S13] |
| `apply_docx_patch.py` | `python apply_docx_patch.py`, run once, in the folder that holds `check_fund.py` | `apply_docx_patch.py:3` [S13] |
| `navall_diag.py` | `python navall_diag.py [path-to-NAVAll.txt]` | `navall_diag.py:2` [S13] |

The full command, parameters, inputs and outputs for all 15 entry points are in [05-api-reference.md](05-api-reference.md).

A first run of `shortlist.py` or `fetch_nav_data.py` needs network access: it downloads the AMFI scheme master and NAV history from mfapi.in and caches them under `data/` [S01, S13]. `shortlist.py` creates its own output folder if missing (`shortlist.py:366` - `os.makedirs(out_dir, exist_ok=True)`, checked) [S04], but no evidence read shows whether `data/` itself is created automatically or must exist first (U06).

**Recommendation:** if a run fails immediately with a file-not-found error under `data/`, create that folder by hand and try again.

**Recommendation:** run `live_check.py` first on a new machine. It is the one script built to tell you whether the external services the toolkit needs (mfapi.in, AMFI, the benchmark proxies) are reachable today, without changing anything except its own cache [S13, "Health checks" in [07-error-handling-and-observability.md](07-error-handling-and-observability.md)].

## Running the tests

11 test files exist at the root, in two styles [inventory, 02-module-architecture.md]:

- 10 files define their own copy of a `check(name, cond)` helper that prints PASS or FAIL and counts the result. This helper is not imported from a shared module [inventory].
- 1 file, `test_forward_signals.py`, uses pytest-style `def test_` functions (18 of them) [inventory].

No `pytest.ini`, `conftest.py`, `tox.ini` or `setup.cfg` was found at the root, so there is no file that declares how these are meant to be run. The presence of `.pytest_cache/` shows `pytest` has been invoked in this repository at least once, which is `inferred`, not a found command for which files or with what result [inventory].

Which style the owner actually runs (`pytest`, or each `check()`-style file directly as `python test_<name>.py`) is open (U01). Two things to know before running any of them:

- `test_forward_signals.py` cannot currently run: it imports four names (`_run_end_to_end`, `make_nav`, `bench_returns`, `fund_returns`) from `test_pipeline.py` that do not exist there (`test_pipeline.py`, 319 lines, read in full; names searched and not found), which raises an `ImportError` before any of its 18 tests execute [S12]. U26 asks the broader question behind this: whether `backtest.py` and `forward_signals.py` belong to an unmerged branch.
- At least five assertions in `test_scoring.py`, `test_new_metrics.py` and `test_pipeline.py` expect `weights.ini` values the committed file does not have (for example `test_scoring.py:61` expects `cagr_3y` to be 15; `weights.ini:35` has 10) [S03]. Whether the rest of the suite passes today is open (U13).

**Next probe:** ask a developer which command they run for tests, or run each file by hand and record the exit status and printed output (that would be runtime material, which the files read cannot supply).

## Where to make common changes

The project has no plugin system and no hook mechanism; changes are made by editing source files directly [02-module-architecture.md](02-module-architecture.md). The places a newcomer is most likely to need:

| Change | Where | How | Evidence |
|---|---|---|---|
| Which metrics matter and how much | `weights.ini` | Edit the `[weights_percent]` section. Must sum to 100 (tolerance 0.01). | [S03] |
| Filter thresholds (minimum CAGR, volatility cap, history years) | `config.py` lines 40-70 | Edit the constant values. | [S01] |
| Portfolio-quality sub-criterion thresholds | `config.py` `PQ_CRITERIA` dict | Edit the worst/best values per sub-criterion. | [S10] |
| Which categories are supported | `config.py` `BENCHMARKS` dict and `fund_universe.py` `CATEGORY_ALIASES` / `CATEGORY_KEYWORDS` | Add matching entries to all three. | [S01, S11] |
| Which AMC websites to scrape | `amc_registry.py` `AMCS` list | Add a dict with key, aliases, page URL and mode. For auto mode, also add a picker function in `holdings_fetch.py`. | [S09] |
| Scoring method | `weights.ini` `[meta]` section, `scoring_method` | Change from `percentile` to `zscore`. | [S03] |
| Missing-data policy | `weights.ini` `[meta]` section, `missing_data_policy` | Change from `renormalize_available` to `average`. | [S03] |

Because `config.py` holds its settings as module-level constants loaded once at import time, and at least one entry point mutates them at runtime (`shortlist.py:322` sets `config.ROLLING_WINDOW_YEARS` from `--rolling-years`), a change made by editing `config.py` applies to every script that imports it for the rest of that process; there is no per-call override mechanism beyond what each script's own command-line flags expose [02-module-architecture.md](02-module-architecture.md).

## Troubleshooting

No interview has been recorded yet, so this section comes from the error messages and fallback logic the code itself defines. The full exit-code and fallback reference is in [07-error-handling-and-observability.md](07-error-handling-and-observability.md); the entries below are the ones most likely to come up while setting up or making a first change.

| Symptom | Likely cause | What to do | Evidence |
|---|---|---|---|
| `shortlist.py` exits 2 before any network call | `weights.ini` is missing, has an unknown metric, a negative weight, or does not sum to 100 | Fix `weights.ini`; the `WeightsError` message names the file and the fault | `weights_loader.py:38` (checked) [S03] |
| `shortlist.py` exits 1, "nothing could be ranked" | Category misspelled, or the hard filters (3y/5y CAGR, volatility, history) excluded every candidate | Check `fund_universe.CATEGORY_ALIASES` for the category name; check `config.py` filter constants | [S01] |
| `mf_holdings_screener.py` or `check_fund.py` stops with "Could not get AMFI's NAVAll.txt" | AMFI's download failed on every one of two URLs and no cached copy exists | Run `navall_diag.py` against a manually downloaded copy to see the raw parsing output | `mf_holdings_screener.py:246` (checked) [S05, S13] |
| `mf_holdings_screener.py` stops with "No header row with an 'ISIN' column was found" | The input file is not the expected holdings export format | Check the input file's header row matches what the screener expects | `mf_holdings_screener.py:274` (checked) [S05] |
| `cdsl_holdings_to_xls.py` stops with "No holding rows were found" | The PDF's text layer and OCR both failed to find rows at the expected column positions | Try `--force-ocr`, a higher `--dpi`, or `--pages` | `cdsl_holdings_to_xls.py:624` (checked) [S06] |
| `cdsl_holdings_to_xls.py` stops needing OCR, or asks for `xlwt` | Tesseract or `xlwt` is not installed | Install the named package, or for `xlwt` use an output name ending in `.xlsx` instead | `cdsl_holdings_to_xls.py:600`, `cdsl_holdings_to_xls.py:940` (checked) [S06] |
| A run finishes but has no `.xlsx` file, or `check_fund.py` finishes with a warning and no `.docx` file | `openpyxl` or `python-docx` is not installed | Install the missing package; the run itself does not stop | `report.py:42`, `report_docx.py:92` (checked) [S04, S07] |
| A fund's benchmark-relative metrics are blank | No local TRI CSV, no pinned scheme code, and no index-fund proxy could be auto-discovered for that category | This is a warning, not a failure; add a TRI CSV with `import_tri.py` for that category if needed | `benchmark.py:164` (checked) [S02, S11] |
| `backtest.py` crashes with an `AttributeError` on `benchmark.resolve_benchmark` | That function does not exist in `benchmark.py` at this commit | Do not expect `backtest.py` to run until this is resolved; see U26 | `backtest.py:273`, `benchmark.py` (284 lines, read in full, function absent, checked) [S12] |

## Unknowns and next probes

| ID | Question | Why it matters here |
|---|---|---|
| U01 | Which tests does the owner run: `pytest`, or each `check()`-style file as a script? | Decides what "the test suite passes" even means on this project. |
| U05 | Which Python version is intended? No file declares one; the machine this survey used has 3.14.3. | A newcomer on a different machine needs a version known to work. |
| U06 | Are `data/` and `out_smallcap/` meant to stay outside git, and can the scripts rebuild `data/` from nothing? | Decides what a newcomer must do before the first successful run. |
| U13 | Does the test suite pass today? At least five assertions expect `weights.ini` values the committed file does not have. | A newcomer who runs the tests and sees failures needs to know whether that is expected. |
| U19, U28 | Do `my_review.xls` and `mfReview.xls` hold real folio numbers or valuations, and is this repository pushed to a remote? | Decides whether cloning or pushing this repository carries personal financial data with it. |
| U26 | Is `backtest.py` from an unmerged branch, given the missing `benchmark.resolve_benchmark` function and undefined config settings? | A newcomer trying `backtest.py` should not assume it is simply their own setup at fault. |

## Related documents

- [02-module-architecture.md](02-module-architecture.md): full file-by-file layout, dependency diagram and extension points
- [05-api-reference.md](05-api-reference.md): every entry point's full command, parameters, inputs, outputs and exit codes
- [06-runtime-and-deployment.md](06-runtime-and-deployment.md): stack, versions, configuration keys and packaging
- [07-error-handling-and-observability.md](07-error-handling-and-observability.md): the full error, exit-code and fallback reference
