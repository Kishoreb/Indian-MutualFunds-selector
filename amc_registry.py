"""
amc_registry.py
---------------
What we know about where each AMC publishes its monthly portfolio, and how far
the toolkit can automate it.

mode:
  "auto"               holdings_fetch.py scrapes the AMC's page for the file link
  "manual"             official page found, but the file list is script-rendered, so
                       download the file in a browser and drop it in data/holdings/<key>/
  "manual_unconfirmed" a page was suggested by notices/search results but not confirmed
  "gated"              the AMC puts the data behind a folio/PAN/citizenship form and
                       restricts reuse -- deliberately NOT automated
  "not_found"          no official monthly-portfolio page could be located

`checked` says how the page URL was established during research (Oct 2026):
  "fetched"   the page loaded and showed portfolio disclosures
  "search"    URL seen in search results only
  "notice"    named in an AMC notice, no page path
  ""          nothing found
None of this has been exercised against live downloads from the build sandbox
(its network blocks AMC sites), so treat "auto" as untested until you run it.
"""

# aliases are matched (lowercased substring) against the fund_house string
# returned by mfapi.in, e.g. "Axis Mutual Fund".
AMCS = [
    # --- automated (static pages that list direct file links) ---------------
    {"key": "nippon_india", "name": "Nippon India Mutual Fund", "aliases": ["nippon"], "mode": "auto",
     "page_url": "https://mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures",
     "checked": "fetched", "note": "One consolidated .xls per month (all schemes); file names are inconsistent, so links are scraped."},
    {"key": "dsp", "name": "DSP Mutual Fund", "aliases": ["dsp"], "mode": "auto",
     "page_url": "https://www.dspim.com/mandatory-disclosures/portfolio-disclosures",
     "checked": "fetched", "note": "Month-end portfolios as one .zip per month; URLs contain unpredictable hashes, so links are scraped."},
    {"key": "baroda_bnp_paribas", "name": "Baroda BNP Paribas Mutual Fund", "aliases": ["baroda bnp"], "mode": "auto",
     "page_url": "https://www.barodabnpparibasmf.in/downloads/monthly-portfolio-scheme",
     "checked": "fetched", "note": "One consolidated .xls per month, date in the file name; there is a LOAD MORE button, newest is listed first."},

    # --- official page found, files must be downloaded by hand --------------
    {"key": "sbi", "name": "SBI Mutual Fund", "aliases": ["sbi mutual"], "mode": "manual",
     "page_url": "https://www.sbimf.com/portfolios", "checked": "fetched",
     "note": "Script-rendered filters (category, scheme, frequency, year, month); one file per scheme."},
    {"key": "hdfc", "name": "HDFC Mutual Fund", "aliases": ["hdfc"], "mode": "manual",
     "page_url": "https://www.hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio", "checked": "fetched",
     "note": "Script-rendered list."},
    {"key": "aditya_birla_sun_life", "name": "Aditya Birla Sun Life Mutual Fund", "aliases": ["aditya birla"], "mode": "manual",
     "page_url": "https://mutualfund.adityabirlacapital.com/forms-and-downloads/portfolio", "checked": "fetched",
     "note": "Script-rendered list."},
    {"key": "axis", "name": "Axis Mutual Fund", "aliases": ["axis"], "mode": "manual",
     "page_url": "https://www.axismf.com/statutory-disclosures", "checked": "fetched",
     "note": "'Portfolios' entry found; file links not visible to the scraper."},
    {"key": "mirae_asset", "name": "Mirae Asset Mutual Fund", "aliases": ["mirae"], "mode": "manual",
     "page_url": "https://www.miraeassetmf.co.in/downloads/portfolio", "checked": "fetched",
     "note": "Tabs are script-rendered. Also files fortnightly PDFs on NSE."},
    {"key": "tata", "name": "Tata Mutual Fund", "aliases": ["tata"], "mode": "manual",
     "page_url": "https://www.tatamutualfund.com/schemes-related/portfolio", "checked": "fetched",
     "note": "Monthly / fortnightly / weekly sections by year."},
    {"key": "motilal_oswal", "name": "Motilal Oswal Mutual Fund", "aliases": ["motilal"], "mode": "manual",
     "page_url": "https://www.motilaloswalmf.com/download/month-end-portfolio", "checked": "fetched",
     "note": "List of 'Month End Portfolio - <Month YYYY>' entries; index funds are on a separate page."},
    {"key": "lic", "name": "LIC Mutual Fund", "aliases": ["lic mutual"], "mode": "manual",
     "page_url": "https://www.licmf.com/downloads/monthly-portfolio", "checked": "fetched",
     "note": "Form filter (category, scheme, year, month). A copy can also be requested by email."},
    {"key": "mahindra_manulife", "name": "Mahindra Manulife Mutual Fund", "aliases": ["mahindra manulife"], "mode": "manual",
     "page_url": "https://www.mahindramanulife.com/downloads", "checked": "fetched",
     "note": "Monthly entries per scheme in Excel/PDF/XML."},
    {"key": "samco", "name": "Samco Mutual Fund", "aliases": ["samco"], "mode": "manual",
     "page_url": "https://www.samcomf.com/StatutoryDisclosure", "checked": "fetched",
     "note": "Per-scheme monthly files (XML/Excel/PDF); file names are inconsistent."},
    {"key": "abakkus", "name": "Abakkus Mutual Fund", "aliases": ["abakkus"], "mode": "manual",
     "page_url": "https://www.abakkusmf.com/statutory-disclosures.html", "checked": "fetched",
     "note": "Monthly section is a year/month filter."},
    {"key": "jioblackrock", "name": "JioBlackRock Mutual Fund", "aliases": ["jioblackrock", "jio blackrock"], "mode": "manual",
     "page_url": "https://www.jioblackrockamc.com/statutory-disclosure/disclosures/monthly-portfolio-disclosure", "checked": "fetched",
     "note": "Year/month filters. Daily per-scheme .xlsx files exist on the daily-portfolio-disclosure page."},

    # --- page suggested but not confirmed -----------------------------------
    {"key": "icici_prudential", "name": "ICICI Prudential Mutual Fund", "aliases": ["icici prudential"], "mode": "manual_unconfirmed",
     "page_url": "https://www.icicipruamc.com/news-and-media/downloads?currentTabFilter=OtherSchemeDisclosures&subCatTabFilter=Monthly+Portfolio+Disclosures",
     "checked": "search", "note": "URL seen in search results only; the page did not load for the scraper."},
    {"key": "uti", "name": "UTI Mutual Fund", "aliases": ["uti mutual"], "mode": "manual_unconfirmed",
     "page_url": "https://www.utimf.com/statutory-disclosures", "checked": "search",
     "note": "Candidate page only; returned an empty shell."},
    {"key": "invesco", "name": "Invesco Mutual Fund", "aliases": ["invesco"], "mode": "manual_unconfirmed",
     "page_url": "https://www.invescomutualfund.com/about-us?tab=Financials", "checked": "notice",
     "note": "Named in a 2019 half-yearly notice; whether monthly files are there is unknown."},

    # --- deliberately not automated -----------------------------------------
    {"key": "edelweiss", "name": "Edelweiss Mutual Fund", "aliases": ["edelweiss"], "mode": "gated",
     "page_url": "https://www.edelweissmf.com/statutory/financials-portfolios", "checked": "fetched",
     "note": "Asks for folio no., bank account no., PAN and email, and the declarations restrict reproducing or storing the data."},
    {"key": "ppfas", "name": "PPFAS (Parag Parikh) Mutual Fund", "aliases": ["ppfas", "parag parikh"], "mode": "gated",
     "page_url": "https://amc.ppfas.com/statutory-disclosures/ConfirmCitizenship.php", "checked": "fetched",
     "note": "Disclosure sections sit behind a citizenship-confirmation step."},

    # --- no official monthly-portfolio page located -------------------------
    {"key": "kotak", "name": "Kotak Mahindra Mutual Fund", "aliases": ["kotak"], "mode": "not_found",
     "page_url": "https://www.kotakmf.com/Information/statutory-disclosure", "checked": "fetched",
     "note": "Statutory-disclosure page loaded but listed no portfolio files."},
    {"key": "bandhan", "name": "Bandhan Mutual Fund", "aliases": ["bandhan"], "mode": "not_found", "page_url": None, "checked": "", "note": ""},
    {"key": "canara_robeco", "name": "Canara Robeco Mutual Fund", "aliases": ["canara robeco"], "mode": "not_found",
     "page_url": None, "checked": "notice", "note": "Notices name www.canararobeco.com and amfiindia.com only."},
    {"key": "franklin_templeton", "name": "Franklin Templeton Mutual Fund", "aliases": ["franklin"], "mode": "not_found",
     "page_url": None, "checked": "notice", "note": "Notices name www.franklintempletonindia.com only."},
    {"key": "hsbc", "name": "HSBC Mutual Fund", "aliases": ["hsbc"], "mode": "not_found",
     "page_url": None, "checked": "search", "note": "Only an old (2018) all-schemes PDF found on assetmanagement.hsbc.co.in."},
    {"key": "quant", "name": "Quant Mutual Fund", "aliases": ["quant"], "mode": "not_found",
     "page_url": None, "checked": "notice", "note": "Notices say www.quantmutual.com; the Admin/MonthlyFortnightlyPortfolio folder holds notices only."},
    {"key": "bank_of_india", "name": "Bank of India Mutual Fund", "aliases": ["bank of india"], "mode": "not_found",
     "page_url": None, "checked": "", "note": "Only factsheets located on boimf.in."},
    {"key": "whiteoak", "name": "WhiteOak Capital Mutual Fund", "aliases": ["whiteoak"], "mode": "not_found",
     "page_url": None, "checked": "", "note": "Only factsheets located."},
    {"key": "360_one", "name": "360 ONE Mutual Fund", "aliases": ["360 one"], "mode": "not_found", "page_url": None, "checked": "", "note": ""},
    {"key": "groww", "name": "Groww Mutual Fund", "aliases": ["groww"], "mode": "not_found",
     "page_url": "https://www.growwmf.in/downloads/fact-sheet", "checked": "fetched",
     "note": "25 download categories, none a monthly portfolio (Portfolio Overlap and Archive not checked)."},
    {"key": "bajaj_finserv", "name": "Bajaj Finserv Mutual Fund", "aliases": ["bajaj"], "mode": "not_found",
     "page_url": "https://bajajamc.com/downloads?tid=532", "checked": "fetched",
     "note": "No monthly portfolio category on the site; monthly PDFs are filed on NSE."},
    {"key": "alphagrep", "name": "AlphaGrep Mutual Fund", "aliases": ["alphagrep"], "mode": "not_found",
     "page_url": "https://www.alphagrepmf.ai/home", "checked": "fetched", "note": "No disclosure page found on the homepage."},
]

BY_KEY = {a["key"]: a for a in AMCS}


def amc_for_fund_house(fund_house: str | None):
    text = (fund_house or "").lower()
    best, best_len = None, 0
    for amc in AMCS:
        for alias in amc["aliases"]:
            # longest alias wins, so "Kotak Mahindra" is not taken for Mahindra Manulife
            if alias in text and len(alias) > best_len:
                best, best_len = amc, len(alias)
    return best


def summary_counts() -> dict:
    out = {}
    for a in AMCS:
        out[a["mode"]] = out.get(a["mode"], 0) + 1
    return out
