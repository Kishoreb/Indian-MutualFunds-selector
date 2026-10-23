# Implementation notes - October 2026 additions

Items implemented: (1) name-similarity fallback, (2) ISIN verification for CDSL CAS reads, (3) walk-forward validation.
Everything below was tested in a sandbox WITHOUT access to mfapi.in, AMFI or Hugging Face: see "What is and is not verified".

## New / changed files
| File | Status | What |
|---|---|---|
| name_match.py | new | guarded name matching (character n-gram similarity; optional local sentence-transformers model) |
| isin_verify.py | new | checks CAS ISINs against AMFI's list + printed names, repairs only unique fits; also a stand-alone command |
| walk_forward.py | new | walk-forward validation of the score (rank year 2023, 2-year horizon, survivors only) |
| portfolio_quality.py | changed | `lookup_ex()` + guarded fallback for sheet-title matching; `pq_note` carries a "verify" label |
| mf_holdings_screener.py | changed | name-similarity fallback after difflib; ISIN-vs-name conflict check; Method-sheet text |
| cdsl_holdings_to_xls.py | changed | `--navall FILE` / `--no-verify`; runs isin_verify after extraction when data/NAVAll.txt exists |
| test_name_match.py, test_isin_verify.py, test_walk_forward.py | new | offline tests |

No change to shortlist.py, scoring.py, weights.ini, config.py. All new settings have defaults in name_match.py and may be
added to config.py: NAME_EMBED_ENABLED (True), NAME_EMBED_MODEL ("models/name-embedder"), NAME_FALLBACK_MIN (0.80),
NAME_FALLBACK_MARGIN (0.04), NAME_CONFLICT_MAX (0.55).

## 1. Name matching fallback
Order in both callers is unchanged: exact / difflib first. Only if that finds nothing is `name_match` asked.
A fallback match needs: similarity >= 0.80, a lead of >= 0.04 over the runner-up, and the GUARD must pass - the guard
refuses a pair when each name has words the other lacks, when a differing word is a number or a category/type word
(small, mid, large, index, etf, liquid, nifty ...), or when fewer than two words are shared. So "Axis Small Cap" never
matches "Axis Mid Cap" however similar the model thinks they are. Matches are labelled "(verify)".
In the screener, when the ISIN IS in AMFI's list but the printed name describes a clearly different scheme
(severity "severe"), the verdict is INSUFFICIENT DATA until you check the ISIN; a mild difference (rename) is a Data Note.
Neural part: put a sentence-transformers model in a folder (default `models/name-embedder`; copy it over from a machine with
internet - nothing is ever downloaded by the toolkit). Without it the module prints one line and uses the n-gram similarity.
On your 75 real holdings the n-gram version alone found the right scheme for every name it answered and never a wrong
one; the embedding model adds recall only for names with very different wording - it has NOT been tested with a real model.

## 2. ISIN verification
Check digit + membership in AMFI NAVAll.txt + printed-name agreement. A damaged ISIN is replaced only when exactly one real
ISIN within <=2 OCR-style confusions (or one arbitrary wrong / extra / missing character) fits the name. Conflicts and
name-only suggestions are written to the Check column and NEVER applied. A misread can pass the check digit by chance
(~1 in 10), so the AMFI list catches errors the old logic could not. No neural OCR was added: the existing
multi-magnification Tesseract + glyph-width correction stays; this makes its output checkable.
Stand-alone: `python isin_verify.py Kiran_2026-06-MF.XLS --navall NAVAll.txt`.

## 3. Walk-forward
`python walk_forward.py` (rank year 2023 -> 31 Mar, 30 Jun, 30 Sep, 31 Dec 2023; forward horizon 2 years; survivors only).
Needs NAV history to reach end-2025 for the last date (it is October 2026, so it does). Run online once to fill data/,
then `--offline` reuses the cache. Outputs in `output/`: walk_forward.md (report), walk_forward.csv, walk_forward_summary.csv.
Read the report's own caveats: overlapping windows, survivors only, today's fund universe, proxy benchmark, no point-in-time
portfolio quality. A significant IC means the ranking carried information in that sample, not that it will next time.
