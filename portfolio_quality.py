"""
portfolio_quality.py
--------------------
Spec parameter 8: a documented 0-100 portfolio-quality score built from
DISCLOSED holdings, never guessed.

Input: the monthly portfolio workbooks AMCs are required to publish (.xls /
.xlsx, or .zip of them) sitting anywhere under config.HOLDINGS_DIR (use
holdings_fetch.py or drop files in by hand). Every sheet that looks like a
SEBI-style portfolio statement is parsed:

    Name of the Instrument | ISIN | Industry/Rating | Quantity | Market Value | % to Net Assets

Five sub-criteria are measured from the equity holdings and each is mapped
to 0-100 by a straight line between a "worst" and a "best" value taken from
config.PQ_CRITERIA (these thresholds are this toolkit's defaults, not an
industry standard -- edit them):

    top10_pct        % of NAV in the ten largest equity holdings   (lower is better)
    n_holdings       number of equity holdings                     (higher is better)
    top_sector_pct   % of NAV in the largest industry              (lower is better)
    largemid_pct     % of equity in large+mid caps (liquidity proxy; needs the
                     AMFI categorisation list -> data/amfi_market_cap.csv)
    cash_pct         cash, TREPS and net receivables, % of NAV     (lower is better)

portfolio_quality = weighted average of the sub-scores that could be measured.
If the measurable weight is below config.PQ_MIN_COVERAGE the score is left
missing (None). Nothing is inferred: a missing file, an unmatched scheme, a
non-equity scheme, a statement whose weights don't add up to ~100%, or a
stale statement all give None, and shortlist.py then treats the metric as
missing like any other.

Debug a folder of real files:   python portfolio_quality.py data/holdings
"""

import glob
import os
import re
import sys
import zipfile
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

import config
import name_match

EXCEL_EXT = (".xls", ".xlsx", ".xlsm")

# Equity-share ISINs: INE + 4-char issuer + "01" (security class) + serial + check digit.
EQUITY_ISIN = re.compile(r"^INE[0-9A-Z]{4}01[0-9A-Z]{3}$")
ANY_ISIN = re.compile(r"^IN[A-Z0-9]{10}$")
CASH_PAT = re.compile(
    r"treps|cblo|tri[\s-]?party|net\s+receivable|net\s+current\s+asset|reverse\s+repo|"
    r"cash\s*(&|and)?\s*(cash\s*)?equivalent|cash\s+and\s+bank|other\s+current\s+asset|payables",
    re.I)
DERIV_PAT = re.compile(r"\b(fut|futures|options?)\b|\bmargin\b", re.I)
TOTAL_PAT = re.compile(r"^\s*(sub[\s-]*total|grand[\s-]*total|total)\b", re.I)
STOP_PAT = re.compile(r"^\s*grand[\s-]*total\b", re.I)


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------
_STOP_WORDS = {"direct", "plan", "growth", "option", "regular", "idcw", "dividend", "fund", "scheme",
               "the", "an", "open", "ended", "mutual", "of", "and"}


def norm_scheme_name(text: str) -> str:
    """Comparable form of a scheme name: drops parentheses ('(An open ended ...)'),
    plan/option words, the 'portfolio as on ...' tail and punctuation."""
    s = str(text or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.split(r"\b(monthly|portfolio|statement|as on|as at)\b", s)[0]
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    tokens = [t for t in s.split() if t not in _STOP_WORDS]
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Parsing one sheet
# ---------------------------------------------------------------------------
def _cell(v) -> str:
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip()


def _find_header(raw: pd.DataFrame):
    """Returns (row_index, column_map) or None."""
    for i in range(min(len(raw), 60)):
        cells = [_cell(v).lower() for v in raw.iloc[i].tolist()]
        isin = next((j for j, c in enumerate(cells) if "isin" in c), None)
        pct = next((j for j, c in enumerate(cells)
                    if ("%" in c or "percent" in c or "net asset" in c or "nav" in c) and j != isin), None)
        if isin is None or pct is None:
            continue
        name = next((j for j, c in enumerate(cells)
                     if any(k in c for k in ("name", "instrument", "security", "company", "issuer"))), None)
        if name is None:
            continue
        industry = next((j for j, c in enumerate(cells) if "industry" in c or "rating" in c or "sector" in c), None)
        return i, {"name": name, "isin": isin, "industry": industry, "pct": pct}
    return None


def _find_as_of(texts) -> pd.Timestamp | None:
    for t in texts:
        m = re.search(r"as\s+(?:on|at)\s*[:\-]?\s*([A-Za-z0-9 ,\-/\.]{6,40})", t, re.I)
        if not m:
            continue
        tokens = m.group(1).replace(",", " ").split()
        for n in range(min(4, len(tokens)), 0, -1):  # longest prefix that parses as a date with a year
            chunk = " ".join(tokens[:n])
            if not re.search(r"\b(19|20)\d{2}\b|\d{1,2}[-/.]\d{1,2}[-/.]\d{2}\b", chunk):
                continue
            d = pd.to_datetime(chunk, dayfirst=True, errors="coerce")
            if pd.notna(d):
                return d
    return None


def classify_row(name: str, isin: str) -> str:
    """equity | cash | derivative | other | total | skip"""
    if TOTAL_PAT.match(name):
        return "total"
    if EQUITY_ISIN.match(isin):
        return "equity"
    if DERIV_PAT.search(name):
        return "derivative"
    if CASH_PAT.search(name):
        return "cash"
    if not name and not isin:
        return "skip"
    return "other"


def parse_sheet(raw: pd.DataFrame, sheet_name: str = ""):
    """Parses one sheet. Returns a dict, or None if it isn't a portfolio statement.
    dict keys: candidates (names to match against), as_of, holdings (DataFrame), reason."""
    found = _find_header(raw)
    if found is None:
        return None
    hdr, cols = found

    above = [_cell(v) for r in range(hdr) for v in raw.iloc[r].tolist() if _cell(v)]
    candidates = [c for c in above if len(c) > 5][:8] + ([sheet_name] if sheet_name else [])
    as_of = _find_as_of(above)

    rows = []
    for r in range(hdr + 1, len(raw)):
        row = raw.iloc[r]
        name = _cell(row.iloc[cols["name"]])
        isin = _cell(row.iloc[cols["isin"]]).upper().replace(" ", "")
        if STOP_PAT.match(name):
            break
        pct = pd.to_numeric(row.iloc[cols["pct"]], errors="coerce")
        if pd.isna(pct):
            continue
        kind = classify_row(name, isin)
        if kind in ("total", "skip"):
            continue
        industry = _cell(row.iloc[cols["industry"]]) if cols["industry"] is not None else ""
        rows.append({"name": name, "isin": isin, "industry": industry, "pct": float(pct), "kind": kind})

    holdings = pd.DataFrame(rows, columns=["name", "isin", "industry", "pct", "kind"])
    return {"candidates": candidates, "as_of": as_of, "holdings": holdings, "sheet": sheet_name}


# ---------------------------------------------------------------------------
# Quality calculation
# ---------------------------------------------------------------------------
def _scale_to_percent(holdings: pd.DataFrame):
    """Weights may be stored as percents (5.23) or fractions (0.0523). Decide from the
    sum of the non-derivative rows, which must be ~100% (or ~1.0). Returns (df, reason)."""
    core = holdings[holdings["kind"] != "derivative"]
    total = core["pct"].sum()
    if 0.9 <= total <= 1.1:
        holdings = holdings.assign(pct=holdings["pct"] * 100)
        total *= 100
    if not (config.PQ_SUM_TOLERANCE[0] <= total <= config.PQ_SUM_TOLERANCE[1]):
        return None, f"weights sum to {total:.1f}%, not ~100%"
    return holdings, ""


def _linear(x: float, worst: float, best: float) -> float:
    if best == worst:
        return 0.0
    return float(min(1.0, max(0.0, (x - worst) / (best - worst))) * 100)


def compute_quality(holdings: pd.DataFrame, mcap_map: dict | None = None) -> dict:
    """Returns {'score', 'coverage', 'inputs', 'subscores', 'reason'}. score is None if it can't be measured."""
    out = {"score": None, "coverage": 0.0, "inputs": {}, "subscores": {}, "reason": ""}
    scaled, reason = _scale_to_percent(holdings)
    if scaled is None:
        out["reason"] = reason
        return out
    eq = scaled[scaled["kind"] == "equity"]
    if len(eq) < config.PQ_MIN_EQUITY_HOLDINGS:
        out["reason"] = f"only {len(eq)} equity holdings (not an equity portfolio)"
        return out

    inputs = {
        "top10_pct": float(eq["pct"].nlargest(10).sum()),
        "n_holdings": float(len(eq)),
        "cash_pct": float(max(0.0, scaled.loc[scaled["kind"] == "cash", "pct"].sum())),
    }
    ind = eq["industry"].str.strip()
    if (ind != "").mean() >= 0.8:
        inputs["top_sector_pct"] = float(eq.groupby(ind)["pct"].sum().max())
    if mcap_map:
        cats = eq["isin"].map(mcap_map)
        known = eq[cats.notna()]
        if len(known) and known["pct"].sum() / eq["pct"].sum() >= config.PQ_MIN_MCAP_MATCH:
            large_mid = known.loc[cats[cats.notna()].isin(["large", "mid"]), "pct"].sum()
            inputs["largemid_pct"] = float(large_mid / known["pct"].sum() * 100)

    weights = {k: v["weight"] for k, v in config.PQ_CRITERIA.items()}
    subs = {k: _linear(inputs[k], config.PQ_CRITERIA[k]["worst"], config.PQ_CRITERIA[k]["best"])
            for k in inputs if k in config.PQ_CRITERIA}
    coverage = sum(weights[k] for k in subs) / sum(weights.values())
    out.update(inputs=inputs, subscores=subs, coverage=coverage)
    if coverage < config.PQ_MIN_COVERAGE:
        out["reason"] = f"only {coverage:.0%} of criteria measurable (< {config.PQ_MIN_COVERAGE:.0%})"
        return out
    out["score"] = sum(subs[k] * weights[k] for k in subs) / sum(weights[k] for k in subs)
    return out


# ---------------------------------------------------------------------------
# AMFI large/mid/small categorisation (for the liquidity sub-criterion)
# ---------------------------------------------------------------------------
def load_marketcap_map(path: str | None = None) -> dict:
    """{isin: 'large'|'mid'|'small'} from a CSV with columns isin,category. Empty dict if absent."""
    path = path or config.AMFI_MARKETCAP_CSV
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if "isin" not in df.columns or "category" not in df.columns:
        raise ValueError(f"{path} needs columns isin,category")
    cat = df["category"].astype(str).str.lower().str.extract(r"(large|mid|small)")[0]
    return dict(zip(df["isin"].astype(str).str.strip().str.upper(), cat))


def marketcap_csv_from_pdf_lines(lines) -> pd.DataFrame:
    """Best-effort conversion of text lines from AMFI's 'Average Market Capitalization' PDF
    (one table row per line) into isin,category. The ISIN is the first 12 characters of the
    ISIN cell (AMFI's PDF sometimes runs the BSE symbol into it) and the category is the last
    'Large Cap' / 'Mid Cap' / 'Small Cap' on the line. Lines that don't fit are skipped."""
    rows = []
    for line in lines:
        m = re.search(r"IN[EF][0-9A-Z]{9}", line)
        c = re.search(r"(Large|Mid|Small)\s*Cap\s*$", line.strip(), re.I)
        if m and c:
            rows.append({"isin": m.group(0), "category": c.group(1).lower()})
    return pd.DataFrame(rows, columns=["isin", "category"]).drop_duplicates("isin")


# ---------------------------------------------------------------------------
# Folder index
# ---------------------------------------------------------------------------
def _excel_files(root: str):
    files = []
    for path in glob.glob(os.path.join(root, "**", "*"), recursive=True):
        low = path.lower()
        if os.sep + "_extracted" + os.sep in path:
            continue
        if low.endswith(EXCEL_EXT):
            files.append(path)
        elif low.endswith(".zip"):
            dest = os.path.join(root, "_extracted", re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.basename(path)))
            if not os.path.isdir(dest):
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(path) as z:
                    for member in z.namelist():
                        if member.lower().endswith(EXCEL_EXT) and not member.startswith("__MACOSX"):
                            target = os.path.join(dest, os.path.basename(member))
                            with z.open(member) as src, open(target, "wb") as dst:
                                dst.write(src.read())
            files.extend(glob.glob(os.path.join(dest, "*")))
    return sorted(f for f in files if f.lower().endswith(EXCEL_EXT))


class PortfolioIndex:
    """All parsed schemes found under the holdings folder."""

    def __init__(self, root: str | None = None, mcap_map: dict | None = None):
        self.root = root or config.HOLDINGS_DIR
        self.mcap_map = load_marketcap_map() if mcap_map is None else mcap_map
        self.entries = []       # one dict per parsed scheme sheet
        self.warnings = []
        self.files_read = 0
        self._matcher = None
        if os.path.isdir(self.root):
            for path in _excel_files(self.root):
                self._read_file(path)

    def _read_file(self, path: str):
        try:
            sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
        except ImportError as exc:
            self.warnings.append(f"{os.path.basename(path)}: {exc} (pip install xlrd for .xls files)")
            return
        except Exception as exc:
            self.warnings.append(f"{os.path.basename(path)}: unreadable ({exc})")
            return
        self.files_read += 1
        for sheet_name, raw in sheets.items():
            parsed = parse_sheet(raw, str(sheet_name))
            if parsed is None:
                continue
            q = compute_quality(parsed["holdings"], self.mcap_map)
            parsed.update(quality=q, source=os.path.basename(path), mtime=os.path.getmtime(path),
                          keys={norm_scheme_name(c) for c in parsed["candidates"] if norm_scheme_name(c)})
            self.entries.append(parsed)

    def _title_matcher(self):
        """Fallback matcher over the sheet titles (built once, on first use)."""
        if self._matcher is None:
            items = {}
            for n, e in enumerate(self.entries):
                for k, c in enumerate(e["candidates"]):
                    title = re.split(r"\b(monthly|portfolio|statement|as on|as at)\b", c, flags=re.I)[0]
                    if len(name_match.tokens(title, strip_code=False)) >= 2:
                        items[(n, k)] = title.strip()
            self._matcher = name_match.NameMatcher(items, strip_code_query=False, strip_code_items=False)
        return self._matcher

    def lookup_ex(self, scheme_name: str):
        """(entry, how). how is '' for an exact / near-identical name match, or a 'verify' label when the entry was
        found only by the name-similarity fallback (name_match.py). (None, '') when nothing matches."""
        target = norm_scheme_name(scheme_name)
        if not target:
            return None, ""
        exact = [e for e in self.entries if target in e["keys"]]
        if not exact:
            scored = []
            for e in self.entries:
                best = max((SequenceMatcher(None, target, k).ratio() for k in e["keys"]), default=0)
                if best >= config.PQ_NAME_MATCH_RATIO:
                    scored.append((best, e))
            if not scored:
                return self._fallback(scheme_name)
            top = max(s for s, _ in scored)
            exact = [e for s, e in scored if s == top]
            if len({tuple(sorted(e["keys"])) for e in exact}) > 1:
                return None, ""  # ambiguous between different schemes -> don't guess
        return max(exact, key=lambda e: (e["as_of"] if e["as_of"] is not None else pd.Timestamp.min, e["mtime"])), ""

    def _fallback(self, scheme_name: str):
        if not name_match.setting("NAME_EMBED_ENABLED") or not self.entries:
            return None, ""
        m = self._title_matcher().match(scheme_name)
        if m is None:
            return None, ""
        entry = self.entries[m.key[0]]
        # every sheet whose title matches equally well is the same scheme in another month: newest wins
        same = [e for e in self.entries if name_match.canon(m.name, False) in
                {name_match.canon(re.split(r"\b(monthly|portfolio|statement|as on|as at)\b", c, flags=re.I)[0], False)
                 for c in e["candidates"]}]
        entry = max(same or [entry], key=lambda e: (e["as_of"] if e["as_of"] is not None else pd.Timestamp.min, e["mtime"]))
        return entry, f"portfolio sheet matched by name similarity {m.score:.0%} ('{m.name[:50]}') - verify"

    def lookup(self, scheme_name: str):
        """Best matching entry for a scheme, or None. Exact normalised-name match first, then a
        very close fuzzy match that must be unambiguous, then (name_match.py) a guarded similarity match.
        Newest statement wins."""
        return self.lookup_ex(scheme_name)[0]


EMPTY_FIELDS = {"portfolio_quality": None, "pq_coverage": None, "pq_top10_pct": None, "pq_holdings": None,
                "pq_top_sector_pct": None, "pq_largemid_pct": None, "pq_cash_pct": None,
                "pq_as_of": "", "pq_source": "", "pq_note": ""}


def fields_for_fund(index: "PortfolioIndex | None", scheme_name: str) -> dict:
    """Columns shortlist.py adds for one fund. Always the full key set. pq_note says why a score is missing."""
    out = dict(EMPTY_FIELDS)
    if index is None:
        return out
    e, how = index.lookup_ex(scheme_name)
    if e is None:
        out["pq_note"] = "no holdings file matched this scheme"
        return out
    q = e["quality"]
    out["pq_source"] = e["source"]
    out["pq_as_of"] = "" if e["as_of"] is None else e["as_of"].strftime("%Y-%m-%d")
    out["pq_coverage"] = q["coverage"]
    inp = q["inputs"]
    out.update(pq_top10_pct=inp.get("top10_pct"), pq_holdings=inp.get("n_holdings"),
               pq_top_sector_pct=inp.get("top_sector_pct"), pq_largemid_pct=inp.get("largemid_pct"),
               pq_cash_pct=inp.get("cash_pct"))
    tail = f"; {how}" if how else ""
    if q["score"] is None:
        out["pq_note"] = q["reason"] + tail
        return out
    if e["as_of"] is not None and config.PQ_MAX_AGE_DAYS is not None:
        age = (pd.Timestamp.now().normalize() - e["as_of"]).days
        if age > config.PQ_MAX_AGE_DAYS:
            out["pq_note"] = f"statement is stale ({age} days old)" + tail
            return out
    out["portfolio_quality"] = q["score"]
    out["pq_note"] = how
    return out


# ---------------------------------------------------------------------------
# Debug CLI
# ---------------------------------------------------------------------------
def _debug(root: str):
    idx = PortfolioIndex(root)
    print(f"{idx.files_read} workbook(s) read, {len(idx.entries)} portfolio sheet(s) parsed under {root}")
    for w in idx.warnings:
        print("  WARNING:", w)
    for e in idx.entries:
        q = e["quality"]
        title = norm_scheme_name(e["candidates"][0]) if e["candidates"] else e["sheet"]
        score = "n/a" if q["score"] is None else f"{q['score']:.1f}"
        note = q["reason"] if q["score"] is None else ""
        print(f"  [{e['source']} / {e['sheet']}] {title!r} score={score} coverage={q['coverage']:.0%} {note}")


if __name__ == "__main__":
    _debug(sys.argv[1] if len(sys.argv) > 1 else config.HOLDINGS_DIR)
