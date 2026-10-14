"""
holdings_fetch.py
-----------------
Downloads the newest month-end portfolio file for the AMCs whose disclosure
page is a plain list of file links (see amc_registry.py, mode == "auto"):
Nippon India, DSP and Baroda BNP Paribas. Files land in data/holdings/<amc>/.

Every other AMC either renders its file list with JavaScript, hides it behind a
form, or has no page we could find. For those, download the file in your
browser from the page printed by `--list` and drop it anywhere under
data/holdings/ -- portfolio_quality.py parses whatever is there.

Usage:
    python holdings_fetch.py              # fetch every automated AMC, then print the manual list
    python holdings_fetch.py dsp nippon_india
    python holdings_fetch.py --list       # show every AMC, its mode and page URL

NOTE: written from the AMCs' public pages but NOT tested against live downloads
(the build sandbox cannot reach AMC sites). If a site changes its layout the
scraper reports "no matching link" instead of guessing.
"""

import html
import os
import re
import sys
from datetime import datetime
from urllib.parse import unquote, urljoin

import requests

import amc_registry
import config

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; mf-shortlister/1.0)"}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def extract_links(page_html: str, base_url: str) -> list[str]:
    """All href targets on a page as absolute URLs, in page order, de-duplicated."""
    seen, out = set(), []
    for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", page_html, flags=re.I):
        url = urljoin(base_url, html.unescape(href.strip()))
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def date_from_filename(url: str) -> datetime | None:
    """Reads dates like 30-09-2026, 31-Aug-26, 30-september-2026, 31_july_2026 from the file name."""
    name = unquote(os.path.basename(url.split("?")[0]))
    m = re.search(r"(\d{1,2})[-_ .](\d{1,2})[-_ .](\d{4})", name)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    for m in re.finditer(r"(\d{1,2})[-_ .]*([A-Za-z]{3,9})[-_ .]*(\d{2,4})", name):
        month = _MONTHS.get(m.group(2)[:3].lower())
        if not month:
            continue
        year = int(m.group(3))
        year += 2000 if year < 100 else 0
        try:
            return datetime(year, month, int(m.group(1)))
        except ValueError:
            continue
    return None


def newest(urls: list[str], n: int = 1) -> list[str]:
    """The n most recent URLs by the date in their file name; undated ones keep page order after dated ones."""
    dated = [(date_from_filename(u), i, u) for i, u in enumerate(urls)]
    dated.sort(key=lambda t: (t[0] is None, -(t[0].timestamp()) if t[0] else 0, t[1]))
    return [u for _, _, u in dated[:n]]


def _ext(url: str) -> str:
    return os.path.splitext(url.split("?")[0])[1].lower()


def pick_nippon(links):
    return [u for u in links if re.search(r"NIMF[-_ ]MONTHLY[-_ ]PORTFOLIO", u, re.I) and _ext(u) in (".xls", ".xlsx")]


def pick_dsp(links):
    return [u for u in links if _ext(u) == ".zip" and re.search(r"month", u, re.I) and re.search(r"portfolio", u, re.I)]


def pick_baroda(links):
    return [u for u in links if re.search(r"Monthly_Portfolio_\d{2}-\d{2}-\d{4}", u, re.I) and _ext(u) in (".xls", ".xlsx")]


PICKERS = {"nippon_india": pick_nippon, "dsp": pick_dsp, "baroda_bnp_paribas": pick_baroda}


def looks_like_office_or_zip(data: bytes) -> bool:
    """True for .xls (OLE2) and .xlsx/.zip (PK) -- rejects HTML error pages saved with a .xls name."""
    return data[:4] == b"\xd0\xcf\x11\xe0" or data[:2] == b"PK"


def download(url: str, dest_dir: str) -> tuple[str | None, str]:
    os.makedirs(dest_dir, exist_ok=True)
    fname = re.sub(r"[^A-Za-z0-9_.()-]+", "_", unquote(os.path.basename(url.split("?")[0])))
    path = os.path.join(dest_dir, fname)
    if os.path.exists(path):
        return path, "already downloaded"
    resp = requests.get(url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    if len(resp.content) < 2048 or not looks_like_office_or_zip(resp.content):
        return None, "response was not an Excel/zip file (blocked, moved, or an error page)"
    with open(path, "wb") as f:
        f.write(resp.content)
    return path, "downloaded"


def fetch_amc(key: str) -> str:
    amc = amc_registry.BY_KEY[key]
    if amc["mode"] != "auto":
        return f"{amc['name']}: not automated ({amc['mode']})"
    try:
        resp = requests.get(amc["page_url"], headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except Exception as exc:
        return f"{amc['name']}: could not load {amc['page_url']} ({exc})"
    links = PICKERS[key](extract_links(resp.text, amc["page_url"]))
    if not links:
        return (f"{amc['name']}: no matching file link on the page (it may be script-rendered now or "
                f"the layout changed). Download manually from {amc['page_url']}")
    msgs = []
    for url in newest(links, config.HOLDINGS_MONTHS_TO_FETCH):
        try:
            path, status = download(url, os.path.join(config.HOLDINGS_DIR, key))
        except Exception as exc:
            msgs.append(f"download failed ({exc}): {url}")
            continue
        msgs.append(f"{status}: {path or url}")
    return f"{amc['name']}: " + "; ".join(msgs)


def list_amcs() -> str:
    lines = []
    for a in amc_registry.AMCS:
        lines.append(f"{a['key']:<22} {a['mode']:<19} {a['page_url'] or '-'}")
    counts = ", ".join(f"{m}: {n}" for m, n in amc_registry.summary_counts().items())
    return "\n".join(lines) + f"\n\n{len(amc_registry.AMCS)} AMCs ({counts})"


def manual_checklist() -> str:
    lines = ["", "Download these by hand (browser) into data/holdings/<amc>/ :"]
    for a in amc_registry.AMCS:
        if a["mode"] in ("manual", "manual_unconfirmed"):
            tag = "" if a["mode"] == "manual" else "  [page unconfirmed]"
            lines.append(f"  {a['name']}: {a['page_url']}{tag}")
    gated = [a["name"] for a in amc_registry.AMCS if a["mode"] == "gated"]
    missing = [a["name"] for a in amc_registry.AMCS if a["mode"] == "not_found"]
    lines.append(f"  Not automated (folio/PAN/citizenship gate): {', '.join(gated)}")
    lines.append(f"  No monthly-portfolio page found: {', '.join(missing)}")
    return "\n".join(lines)


def fetch_all(keys=None, quiet_manual: bool = False):
    keys = keys or [a["key"] for a in amc_registry.AMCS if a["mode"] == "auto"]
    print("Fetching month-end portfolio files ...")
    for k in keys:
        if k not in amc_registry.BY_KEY:
            print(f"  unknown AMC key '{k}'")
            continue
        print("  " + fetch_amc(k))
    if not quiet_manual:
        print(manual_checklist())


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--list" in sys.argv:
        print(list_amcs())
    else:
        fetch_all(argv or None)
