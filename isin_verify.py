#!/usr/bin/env python3
"""
isin_verify.py
--------------
Item 2: more reliable ISINs from the CDSL CAS statement.

WHY. The mutual-fund and share ISINs are the keys the whole toolkit hangs on. When a statement page has to be
OCR'd, a character is sometimes read wrong (0/O, 1/I, 5/S, 8/B ...). cdsl_holdings_to_xls.py already repairs
reads with the ISIN CHECK DIGIT, but a check digit alone cannot tell the right repair from a wrong one: about one
random string in ten passes it, so two different "repairs" can both look valid.

WHAT THIS ADDS. A second, independent test using data you already have:
    * AMFI's NAVAll.txt lists every mutual fund ISIN together with the scheme name. An ISIN that is not in that
      list is NOT a real ISIN, and the name printed next to it on your statement must describe the scheme it
      belongs to.
So each statement ISIN is checked three ways -- check digit, membership of the AMFI list, and agreement of the
printed scheme name with the AMFI name (name_match.py, with the guard against look-alike schemes) -- and a damaged
ISIN is repaired only when ALL of these single out one answer:
    status 'ok'         ISIN is in the AMFI list and the name agrees.
    status 'repaired'   ISIN was not valid; exactly one ISIN within a couple of OCR-style character confusions
                        (or one arbitrary wrong character) is in the AMFI list with a compatible name. Applied,
                        and flagged in the Check column so you can look at it.
    status 'conflict'   ISIN is in the AMFI list but the printed name describes a different scheme. NOT changed.
    status 'suggested'  ISIN is not valid and no near neighbour fits, but the printed NAME matches one scheme.
                        NOT applied - the suggestion is only written in the note.
    status 'unknown'    nothing fits. Left as read.
Nothing is ever changed unless it is uniquely identified; everything else is reported.

For SHARES (INE... ISINs) no scheme list exists offline, so only an optional universe (config.AMFI_MARKETCAP_CSV,
the AMFI large/mid/small list) is used: a damaged ISIN is repaired only if exactly one ISIN of that list is within
one OCR-style confusion of it. Without the list shares keep the existing check-digit logic.

It does not "re-read the PDF better" - there is no neural OCR in it. It makes the OCR result checkable and
self-correcting against a list that cannot be wrong about which ISINs exist.

USE
    python isin_verify.py Kiran_2026-06-MF.XLS                 # -> Kiran_2026-06-MF-ISINcheck.XLS
    python isin_verify.py Kiran_2026-06-MF.XLS --navall NAVAll.txt -o checked.xls
and cdsl_holdings_to_xls.py calls it by itself when data/NAVAll.txt (or --navall FILE) is available; pass
--no-verify there to skip it.

Not investment advice. The repair is an aid; always compare flagged ISINs with the PDF.
"""

import argparse
import itertools
import os
import re
import sys

try:
    import name_match
except Exception:                                  # pragma: no cover
    name_match = None

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
ISIN_FIND = re.compile(r"\bIN[EF][0-9A-Z]{9}\b")
CONFUSABLE = {                                    # OCR look-alikes (same table as cdsl_holdings_to_xls.py)
    "0": "OQD", "O": "0Q", "Q": "0O", "D": "0", "1": "IL", "I": "1L", "L": "1I", "5": "S", "S": "5",
    "8": "B", "B": "8", "2": "Z", "Z": "2", "6": "G", "G": "6", "7": "T", "T": "7",
}
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
MAX_CONFUSIONS = 2
_NOT_GROWTH = ("idcw", "dividend", "payout", "reinvest", "bonus")


def checksum_ok(s: str) -> bool:
    if not ISIN_RE.match(s):
        return False
    digits = "".join(str(int(c, 36)) for c in s)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def make_valid(body11: str) -> str:
    """Append the check digit to an 11-character ISIN body (used by tests and by candidate generation)."""
    for d in "0123456789":
        if checksum_ok(body11 + d):
            return body11 + d
    raise ValueError(body11)


def parse_universe(navall_text: str) -> dict:
    """{isin: scheme name} from AMFI's NAVAll.txt (both ISIN columns). Handles the older layout and the layout
    with separate Plan / Option columns (appended to the name, so 'Direct' and 'Growth' stay visible)."""
    uni, cols = {}, {"name": 3, "plan": None, "option": None}
    for raw in navall_text.splitlines():
        if ";" not in raw:
            continue
        f = [x.strip() for x in raw.split(";")]
        if f[0].lower().startswith("scheme code"):
            low = [c.lower() for c in f]
            cols = {"name": next((i for i, c in enumerate(low) if "scheme name" in c), 3),
                    "plan": low.index("plan") if "plan" in low else None,
                    "option": low.index("option") if "option" in low else None}
            continue
        if len(f) < 5 or not f[0].isdigit():
            continue
        name = f[cols["name"]] if cols["name"] < len(f) else ""
        extra = [f[cols[k]] for k in ("plan", "option") if cols[k] is not None and cols[k] < len(f) and f[cols[k]]]
        name = " - ".join([name] + extra)
        for isin in (f[1], f[2]):
            if ISIN_RE.match(isin):
                uni.setdefault(isin, name)
    return uni


def parse_stock_universe(csv_path: str) -> set:
    """ISINs of a csv with an 'isin' column (config.AMFI_MARKETCAP_CSV)."""
    import pandas as pd
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]
    return set(df["isin"].astype(str).str.strip().str.upper()) if "isin" in df.columns else set()


def find_navall(explicit=None):
    """Path to NAVAll.txt: the explicit one, else data/NAVAll.txt (config.DATA_DIR when available)."""
    if explicit:
        return explicit if os.path.exists(explicit) else None
    base = "data"
    try:
        import config
        base = getattr(config, "DATA_DIR", base)
    except Exception:
        pass
    p = os.path.join(base, "NAVAll.txt")
    return p if os.path.exists(p) else None


# ---------------------------------------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------------------------------------
def near_candidates(read: str, universe, max_conf=MAX_CONFUSIONS):
    """Yield (isin, cost) for ISINs of `universe` reachable from the OCR read by
        * up to `max_conf` look-alike substitutions (cost = number of them), or
        * ONE arbitrary substituted character (cost 2), or
        * one deleted / one inserted character (cost 2).
    Only ISINs that pass the check digit and are in the universe are yielded; the cheapest cost wins."""
    s = re.sub(r"[^A-Z0-9]", "", read.upper())
    best = {}

    def offer(t, cost):
        if t in universe and checksum_ok(t) and cost < best.get(t, 99):
            best[t] = cost

    if len(s) == 12:
        pos = [i for i in range(2, 12) if s[i] in CONFUSABLE]
        for k in range(0, max_conf + 1):
            for combo in itertools.combinations(pos, k):
                for subs in itertools.product(*[CONFUSABLE[s[i]] for i in combo]):
                    t = list(s)
                    for i, ch in zip(combo, subs):
                        t[i] = ch
                    offer("".join(t), k)
        for i in range(2, 12):                       # one arbitrary wrong character
            for ch in ALPHABET:
                if ch != s[i]:
                    offer(s[:i] + ch + s[i + 1:], 2)
    elif len(s) == 13:                               # one stray character
        for i in range(2, 13):
            offer(s[:i] + s[i + 1:], 2)
    elif len(s) == 11:                               # one dropped character
        for i in range(2, 12):
            for ch in ALPHABET:
                offer(s[:i] + ch + s[i:], 2)
    return sorted(best.items(), key=lambda kv: kv[1])


# ---------------------------------------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------------------------------------
class Result:
    __slots__ = ("isin", "status", "note", "suggestion")

    def __init__(self, isin, status, note="", suggestion=""):
        self.isin, self.status, self.note, self.suggestion = isin, status, note, suggestion

    def __repr__(self):
        return f"Result({self.isin!r}, {self.status!r}, {self.note!r})"


class IsinVerifier:
    """universe: {isin: scheme name} (mutual funds). stock_universe: optional set of share ISINs."""

    def __init__(self, universe, stock_universe=None, embedder="default"):
        self.universe = universe
        self.stocks = stock_universe or set()
        self.embedder = embedder
        self._matchers = {}
        self.counts = {}

    # -- names ------------------------------------------------------------------------------------------
    def _emb(self):
        if self.embedder == "default":
            self.embedder = name_match.default_embedder() if name_match and name_match.setting("NAME_EMBED_ENABLED") else None
        return self.embedder

    def _name_check(self, printed, isin):
        """name_match.compare() of the printed name against the AMFI name of `isin`; None if names can't be judged."""
        if name_match is None or not printed or isin not in self.universe:
            return None
        return name_match.compare(printed, self.universe[isin], strip_code_a=True, strip_code_b=False, embedder=self._emb())

    def _name_matcher(self, printed):
        """Matcher over the Direct (or Regular) growth-type schemes, one entry per distinct name."""
        direct = "direct" in printed.lower()
        if direct not in self._matchers:
            items, seen = {}, set()
            for isin, name in self.universe.items():
                low = name.lower()
                if any(w in low for w in _NOT_GROWTH) or (("direct" in low) != direct) or name in seen:
                    continue
                seen.add(name)
                items[isin] = name
            self._matchers[direct] = name_match.NameMatcher(items, embedder=self._emb(), strip_code_query=True,
                                                            strip_code_items=False)
        return self._matchers[direct]

    def _bump(self, status):
        self.counts[status] = self.counts.get(status, 0) + 1

    def _done(self, res):
        self._bump(res.status)
        return res

    # -- mutual funds -----------------------------------------------------------------------------------
    def verify_mf(self, isin, name):
        isin = re.sub(r"[^A-Z0-9]", "", (isin or "").upper())
        if isin in self.universe:
            c = self._name_check(name, isin)
            if c is None or c["severity"] == "none":
                return self._done(Result(isin, "ok"))
            if c["severity"] == "mild":
                return self._done(Result(isin, "ok", f"name differs from AMFI's ('{self.universe[isin]}'): possible rename"))
            sugg = self._by_name(name)
            msg = (f"ISIN is valid but belongs to '{self.universe[isin]}', not the scheme printed on the statement "
                   f"({c['reason'] or 'names differ'}). ISIN may be misread - compare with the PDF.")
            if sugg:
                msg += f" By name the statement fund looks like {sugg[0]} ('{sugg[1]}')."
            return self._done(Result(isin, "conflict", msg, sugg[0] if sugg else ""))
        # not in the AMFI list: try to repair
        cands = []
        for cand, cost in near_candidates(isin, self.universe):
            c = self._name_check(name, cand)
            if c is not None and c["severity"] == "severe":
                continue
            cands.append((cost, -(c["similarity"] if c else 0.0), cand))
        cands.sort()
        if cands:
            if len(cands) == 1 or (cands[0][0] < cands[1][0]) or (cands[0][1] + 0.10 < cands[1][1]):
                cost, _, cand = cands[0]
                return self._done(Result(cand, "repaired",
                                         f"ISIN '{isin}' is not in AMFI's list; replaced by {cand} "
                                         f"('{self.universe[cand]}') - {cost} OCR-style character change(s), name agrees. Verify."))
            return self._done(Result(isin, "unknown", f"ISIN '{isin}' is not in AMFI's list and several near ISINs fit "
                                                      f"({', '.join(c[2] for c in cands[:3])}) - not guessing. Verify."))
        sugg = self._by_name(name)
        if sugg:
            return self._done(Result(isin, "suggested",
                                     f"ISIN '{isin}' is not in AMFI's list. By name the fund looks like {sugg[0]} "
                                     f"('{sugg[1]}') - NOT applied, verify.", sugg[0]))
        return self._done(Result(isin, "unknown", f"ISIN '{isin}' is not in AMFI's list and no scheme matches the name."))

    def _by_name(self, printed):
        if name_match is None or not printed:
            return None
        m = self._name_matcher(printed).match(printed)
        return (m.key, m.name) if m is not None else None

    # -- shares -----------------------------------------------------------------------------------------
    def verify_stock(self, isin, name=""):
        isin = re.sub(r"[^A-Z0-9]", "", (isin or "").upper())
        if not self.stocks:
            return Result(isin, "ok" if checksum_ok(isin) else "unknown",
                          "" if checksum_ok(isin) else "check digit invalid; no share ISIN list available")
        if isin in self.stocks:
            return self._done(Result(isin, "ok"))
        # not in the list. A misread can still pass the check digit (about 1 in 10), so look for a neighbour first
        cands = [(c, k) for c, k in near_candidates(isin, self.stocks, max_conf=1) if k <= 1]
        valid = checksum_ok(isin)
        if len(cands) == 1:
            why = "passed the check digit but is not in the share list" if valid else "failed the check digit"
            return self._done(Result(cands[0][0], "repaired", f"ISIN '{isin}' {why}; the only share ISIN within one "
                                     f"OCR confusion is {cands[0][0]}. Verify."))
        if valid:                                    # valid but outside the (partial) list: nothing to say
            return Result(isin, "ok")
        return self._done(Result(isin, "unknown", f"ISIN '{isin}' fails the check digit and no unique repair exists."))


def apply_to_mf_rows(rows, verifier, log=print):
    """Updates statement rows in place ('ISIN', 'Scheme Name', 'Check'); returns the list of (row, Result)."""
    out = []
    for r in rows:
        res = verifier.verify_mf(r.get("ISIN", ""), r.get("Scheme Name", ""))
        if res.status == "repaired":
            r["ISIN"] = res.isin
        if res.status != "ok" or res.note:
            tag = {"repaired": "ISIN repaired against AMFI list", "conflict": "ISIN/name CONFLICT",
                   "suggested": "ISIN not in AMFI list", "unknown": "ISIN not verified", "ok": "ISIN note"}[res.status]
            prev = r.get("Check", "OK")
            r["Check"] = (tag + ": " + res.note) if prev in ("", "OK", None) else prev + "; " + tag + ": " + res.note
        out.append((r, res))
    return out


def apply_to_stock_rows(rows, verifier):
    out = []
    for r in rows:
        res = verifier.verify_stock(r.get("ISIN", ""), r.get("Security", ""))
        if res.status == "repaired":
            r["ISIN"] = res.isin
            prev = r.get("Check", "OK")
            r["Check"] = ("ISIN repaired against share list: " + res.note) if prev in ("", "OK", None) else prev + "; " + res.note
        out.append((r, res))
    return out


def summarize(verifier):
    c = verifier.counts
    return ("ISIN verification: " + ", ".join(f"{c.get(k, 0)} {k}" for k in ("ok", "repaired", "conflict", "suggested", "unknown")))


# ---------------------------------------------------------------------------------------------------------
# Stand-alone command: check an existing MF holdings file
# ---------------------------------------------------------------------------------------------------------
def _read_grid(path):
    if path.lower().endswith(".xlsx"):
        from openpyxl import load_workbook
        return [list(r) for r in load_workbook(path, data_only=True).worksheets[0].iter_rows(values_only=True)]
    import xlrd
    sh = xlrd.open_workbook(path).sheet_by_index(0)
    return [sh.row_values(i) for i in range(sh.nrows)]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check (and where unique, repair) the ISINs of a mutual fund holdings file "
                                             "against AMFI's scheme list and the printed scheme names.")
    ap.add_argument("holdings", help="mutual fund holdings .xls/.xlsx (from cdsl_holdings_to_xls.py)")
    ap.add_argument("--navall", help="AMFI NAVAll.txt on disk (default: data/NAVAll.txt)")
    ap.add_argument("-o", "--output", help="output file (default: <input>-ISINcheck.<ext>)")
    ap.add_argument("--no-repair", action="store_true", help="report only; never change an ISIN")
    a = ap.parse_args(argv)

    path = find_navall(a.navall)
    if not path:
        sys.exit("AMFI NAVAll.txt not found. Pass --navall FILE, or run mf_holdings_screener.py once so that data/NAVAll.txt exists.")
    with open(path, encoding="utf-8", errors="replace") as fh:
        uni = parse_universe(fh.read())
    if not uni:
        sys.exit(f"{path} had no scheme rows - is it AMFI's NAVAll.txt?")
    grid = _read_grid(a.holdings)
    hi = next((i for i, r in enumerate(grid) if any(str(c).strip() == "ISIN" for c in r)), None)
    if hi is None:
        sys.exit("No header row with an 'ISIN' column was found.")
    heads = [str(c).strip() for c in grid[hi]]
    ni, ii = heads.index("Scheme Name"), heads.index("ISIN")
    ver = IsinVerifier(uni)
    body = []
    for r in grid[hi + 1:]:
        name = str(r[ni]).strip()
        if not name or name.upper() == "TOTAL":
            body.append(list(r) + ["", "", ""])
            continue
        res = ver.verify_mf(str(r[ii]), name)
        new = list(r)
        if res.status == "repaired" and not a.no_repair:
            new[ii] = res.isin
        body.append(new + [res.status, res.suggestion or (res.isin if res.status == "repaired" else ""), res.note])
    out = a.output or (lambda b, e: b + "-ISINcheck" + (e or ".XLS"))(*os.path.splitext(a.holdings))
    hdr = heads + ["ISIN Status", "ISIN Suggested/Applied", "ISIN Note"]
    if out.lower().endswith(".xlsx"):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "ISIN check"
        ws.append(hdr)
        for row in body:
            ws.append(row)
        wb.save(out)
    else:
        import xlwt
        wb = xlwt.Workbook(encoding="utf-8"); ws = wb.add_sheet("ISIN check")
        for j, h in enumerate(hdr):
            ws.write(0, j, h)
        for i, row in enumerate(body, 1):
            for j, v in enumerate(row):
                if v not in ("", None):
                    ws.write(i, j, v)
        wb.save(out)
    print(f"Wrote {out}\n{summarize(ver)}")
    for row in body:
        if row[len(heads)] not in ("ok", ""):
            print(f"  [{row[len(heads)]}] {str(row[ni])[:50]}: {row[len(heads) + 2]}")


if __name__ == "__main__":
    main()
