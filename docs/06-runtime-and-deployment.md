# Runtime and deployment

Audience: a developer who needs to install, run or move this project to another machine, and wants to know what it depends on and what is not provided.

Evidence: 15 of 15 entry points read · 3 configuration files · 5 open unknowns · commit ef2fb5a · Surveyor 2.2.0 · 2026-10-24

This is a local command-line toolkit, not a service. There is no server process, no scheduler and nothing that stays running between commands [inventory].

## Stack and versions

| Part | Declared as | Evidence |
|---|---|---|
| Language | Python | `requirements.txt` lists only Python packages; no other language appears among the 57 tracked files [inventory] |
| Python version | Not declared in any file. The interpreter on the machine the inventory was taken on is 3.14.3. | inventory, "Project type" table |
| pandas | `pandas>=2.2` | `requirements.txt:1` - `pandas>=2.2` (checked, inventory) |
| Other packages | `numpy`, `requests`, `openpyxl`, `xlrd`, `pdfplumber`, `xlwt`, `python-docx` named in `requirements.txt`, no version pin recorded for these in the slices read | inventory, "Configuration" table |
| `pytesseract` | Named in `requirements.txt` but commented out | inventory, "Configuration" table |

The `pandas>=2.2` pin matters at runtime: `metrics.py:65` resamples with the string `"ME"` (month-end), a pandas 2.2 feature [S02/F001]. No source file states why 3.14.3 is the version in use, and no `.python-version`, `pyproject.toml`, `setup.cfg`, `pytest.ini`, `tox.ini` or `conftest.py` was found at the repository root (search boundary: these filenames at the root) [inventory]. Whether an older or newer Python version also works is unknown (U05).

## Runtime dependencies

Every script that touches NAV data, Excel files or Word output needs the packages in `requirements.txt`: `pandas`, `numpy`, `requests`, `openpyxl`, `xlrd`, `pdfplumber`, `xlwt`, `python-docx` [inventory]. There is one dependency outside this file:

- **Tesseract OCR**, an external program, not a Python package. It is only needed when `cdsl_holdings_to_xls.py` falls back to OCR because a PDF page has no text layer, or when `--force-ocr` is given [S06/F006]. If `pytesseract` is not installed and OCR is needed, the script stops with `sys.exit("This PDF page has no text layer, so OCR is needed:\n...")` (`cdsl_holdings_to_xls.py:600`, checked) [S06/F006]. The Tesseract path can be overridden with `--tesseract-cmd`, which is passed straight to `pytesseract.pytesseract.tesseract_cmd` (`cdsl_holdings_to_xls.py:1124`, checked) [S06/F006].

No other external program (database server, message broker, cache server) appears in the files read. The project reaches two external web services at runtime (mfapi.in and AMFI's file server) and up to 25 AMC web pages; these are network dependencies, not installed software [inventory, "External integrations"].

There is a single `requirements.txt` for the whole project. Nothing in the files read separates a test-only dependency list from a runtime one; the homegrown `check()` test helper and the `def test_` functions use only the standard library and the same packages already listed [inventory, "Needs a human look"].

## Configuration model and keys

Configuration is Python source, not environment variables or a config-file-plus-overrides pattern. No `.env` file, and no code in the slices read calls `os.environ` (search boundary: `.env*` at the root, searched by the inventory; `os.environ` was not searched for specifically in the slices and is not asserted absent here).

Two files hold the settings:

- **`config.py`**, about 60 module-level constants covering data locations, filters, metric windows, benchmark and portfolio-quality switches and output paths [inventory, "Configuration" table]. Keys referenced in the slices read: `DATA_DIR`, `BENCHMARK_DIR`, `OUTPUT_DIR` (`config.py:188`, `OUTPUT_DIR = "."`, checked) [S04/F001], `MFAPI_BASE_URL`, `CACHE_MAX_AGE_DAYS` (1 day) [S01/F001, S13/F011], `SCHEME_MASTER_CACHE_DAYS` (7 days) [S01/F001], `STALE_NAV_DAYS` (10) [S01/F001], `MAX_FUNDS_TO_SCAN` (60) [S01/F001], `MIN_CAGR_3Y`, `MAX_VOLATILITY`, `MIN_HISTORY_YEARS` [S01/F001], `DRAWDOWN_WINDOW_YEARS` (3.0) [S02/F001], `RISK_FREE_RATE` (6.5% a year, fixed, not fetched) [S02/F001], `SIP_MONTHLY_AMOUNT` (1000) [S02/F001], `WEIGHTS_FILE`, `FUND_ATTRIBUTES_CSV` and `TOP_N` [inventory]. `config.py` loads the weights file at import time: `apply_weights(WEIGHTS_FILE)` (`config.py:182`, checked) [S01/F001]. Because these are module-level constants, a value changed at run time, such as `shortlist.py:322` setting `config.ROLLING_WINDOW_YEARS` from `--rolling-years`, is shared mutable state for the rest of that process, not a per-call parameter [S01/F001] (also noted as a risk in [04-shortlist-and-rank.md](04-shortlist-and-rank.md)).
- **`weights.ini`**, the scoring policy and per-metric weights read by `weights_loader.py`, with `[meta]` keys `version`, `missing_data_policy`, `minimum_coverage_percent`, `scoring_method`, `min_group_size`, and a `[weights_percent]` section with one line per metric [inventory, S03/F001]. The shipped values are `missing_data_policy = renormalize_available`, `scoring_method = percentile`, `minimum_coverage_percent = 70`, `min_group_size = 8` (`weights.ini:23,27,30`, checked) [S03/F001]. The file is checked hard before a run starts: missing file, missing section, an unknown policy or method, an unknown metric, a negative weight, or a total that is not 100 (tolerance 0.01) all raise `WeightsError`, which `shortlist.py` turns into exit code 2 before any network call [S01/F001, S03/F001].

`requirements.txt` is the third configuration file by the inventory's count, but it configures the install step, not a running process [inventory].

Some scripts take their own settings on the command line instead of `config.py`: for example `cdsl_holdings_to_xls.py --dpi`, `--workers`, `--tesseract-cmd`, `--password` [S06/F006], and `shortlist.py --weights`, `--output-dir`, `--rolling-years` [S01/F001]. Full parameter tables per entry point are in [05-api-reference.md](05-api-reference.md).

## Packaging

There is no package to build. The repository is a flat folder of 57 tracked files with no subdirectories of source code and no `__init__.py` [inventory, "Module layout" in [02-module-architecture.md](02-module-architecture.md)]. No `setup.py`, `pyproject.toml`, `Dockerfile`, or CI/CD file (`.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml`) was found at the root (search boundary: these filenames at the root) [inventory, "Surprising zeros"].

Two error messages in the code point at `pip` as the install tool, though no file in the working set states a single install command for the whole project:

- `report_docx.py:92` - `raise DocxUnavailable("python-docx is not installed. Run:  pip install python-docx")` (checked) [S04/F003]
- `cdsl_holdings_to_xls.py:940` - `sys.exit("Writing .xls needs xlwt:  pip install xlwt     (or use an output name ending in .xlsx)")` (checked) [S06/F006]

This is `inferred`, not observed: the messages show that missing packages are expected to be added with `pip install <package>`, not that a documented `pip install -r requirements.txt` step was read in the working files. The full install and setup procedure is left to [08-developer-onboarding.md](08-developer-onboarding.md).

## Start commands

Every one of the 15 entry points is started the same way: `python <file>.py [arguments]`, parsed by `argparse` [inventory, "Entry points" table]. There is no wrapper script, no console-script shim, and nothing installs itself onto the system `PATH`. Examples read directly from the usage text or docstring of each script:

| Script | Example command | Evidence |
|---|---|---|
| `shortlist.py` | `python shortlist.py --category "small cap"` | [S01/F001], `shortlist.py:300` |
| `fetch_nav_data.py` | `python fetch_nav_data.py 120503 118989 100033` | [S13/F011], `fetch_nav_data.py:9` |
| `live_check.py` | `python live_check.py` (optionally `--holdings --category "mid cap"`) | [S13/F012], `live_check.py:8` |
| `apply_docx_patch.py` | `python apply_docx_patch.py`, run once, in the folder that holds `check_fund.py` | [S13/F013], `apply_docx_patch.py:3` |
| `navall_diag.py` | `python navall_diag.py [path-to-NAVAll.txt]` | [S13/F014], `navall_diag.py:2` |

The remaining ten commands, with their full parameter lists, are in [05-api-reference.md](05-api-reference.md). Each run starts a Python process, does its work, prints to the screen (and, for `shortlist.py`, `rank_funds.py` and `check_fund.py`, writes files), and exits with a code of its own (0, 1 or 2 by convention; see the per-entry-point exit-code tables in [05-api-reference.md](05-api-reference.md)). Nothing keeps a process alive after that.

## Deployment targets and environments

No deployment target was found. There is no `Dockerfile`, no cloud configuration, no infrastructure-as-code file, and no CI/CD pipeline in the 57 tracked files (search boundary: `.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml`, `Dockerfile` at the root) [inventory, "Surprising zeros"]. Nothing in the files read distinguishes a development, staging or production environment: `config.py` has one set of values, used by every run [S01/F001].

The toolkit runs on whichever machine a person has cloned the repository to, and keeps its working data on that machine:

- `data/` holds 121 untracked files: 60 NAV CSVs, 60 `_meta.csv` files and one scheme-master JSON cache [inventory, I007].
- `data/benchmarks/` and `data/holdings/<amc>/` are written to by `import_tri.py` and `holdings_import.py` respectively [S11/F009, S09/F008].
- Output files from a run go to the current folder by default, or to `--output-dir` [S01/F001, config.py:188].

Two files that are tracked by git hold the owner's own data: `my_review.xls` and `mfReview.xls` [inventory, "Needs a human look"]. Whether these contain real folio numbers, ISIN holdings or valuations, and whether this repository is pushed to a remote such as GitHub, was not established by the files read (U19, U28). This matters for deployment because moving or cloning the repository would carry those files with it.

## Unknowns and next probes

| ID | Question | Why it matters here |
|---|---|---|
| U05 | Which Python version is intended? No file declares one; the machine the inventory was taken on has 3.14.3. | A newcomer setting up on another machine needs a version that is known to work. |
| U06 | Are `data/` and `out_smallcap/` meant to stay outside git, and can they be rebuilt by the scripts? | Decides what a newcomer must fetch or regenerate before a first run. |
| U19 | Do `my_review.xls` and `mfReview.xls` (tracked in git) hold real folio numbers and valuations, and is the repository pushed to a remote such as GitHub? | If so, cloning or pushing this repository carries personal financial data with it. |
| U27 | Is the 0.3-second sleep between mfapi.in calls sufficient to avoid rate-limiting, and does the cache logic handle concurrent runs? | Running two entry points at once on the same machine could hit the same cache files or the same API. |
| U28 | Do `my_review.xls` and `mfReview.xls` contain real folio numbers, ISIN holdings, or valuations? (Overlaps with U19.) | Same exposure risk, found independently while reading the sample output in S14. |

## Related documents

- [02-module-architecture.md](02-module-architecture.md): file layout and what each module does
- [05-api-reference.md](05-api-reference.md): full command, parameter, input, output and exit-code reference for every entry point
- [08-developer-onboarding.md](08-developer-onboarding.md): install steps and how to run the project and its tests (not yet written)
