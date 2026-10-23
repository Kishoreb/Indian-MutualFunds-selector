#!/usr/bin/env python3
"""
walk_forward.py
---------------
Walk-forward validation of the toolkit's score: "if I had ranked the funds as of a past date using only the
data available then, did the top-ranked funds do better afterwards?"

    python walk_forward.py                                  # rank year 2023, 2-year horizon, all categories
    python walk_forward.py --rank-year 2023 --horizon-years 2
    python walk_forward.py --rank-date 2023-06-30           # one explicit date (repeat for several)
    python walk_forward.py --category "small cap" --category "mid cap"
    python walk_forward.py --offline                        # use only the NAV files already cached under data/
    python walk_forward.py --no-hard-filters                # score every evaluable fund, ignore the config.py filters
    python walk_forward.py --weights my_weights.ini --output-dir out --seed 1

SETTINGS DECIDED BY THE USER: rank date = a date in 2023, forward horizon = 2 years, SURVIVOR funds only
(accepting survivorship bias). Because only a year was given, the default is the four calendar quarter-ends of
that year (31 Mar, 30 Jun, 30 Sep, 31 Dec): one date alone is a noisy test. The four forward windows OVERLAP
heavily, so they are NOT four independent tests; the report says so. Use --rank-date for one exact date.

WHAT IT DOES (for every rank date T, using the toolkit's own code so "the existing score" is exactly what is tested)
  1. Universe: today's Direct+Growth schemes of the requested categories (fund_universe.find_candidates), grouped
     by the fund's own AMFI category, like the live tool.
  2. Survivors only: funds whose NAV stopped updating (older than config.STALE_NAV_DAYS before the newest NAV
     loaded) and funds whose data does not reach T + horizon are dropped, and both counts are reported.
  3. As-of-T metrics with NO LOOK-AHEAD: every fund's NAV (and the benchmark's) is cut at T before
     metrics.compute_all_metrics, benchmark.metrics_for_fund and extra_metrics are run with the config.py settings.
     portfolio_quality is left missing for everyone: the holdings files are today's, not point-in-time, and the
     missing-data policy in weights.ini then handles it.
  4. The config.py hard filters (as of T) unless --no-hard-filters; the removed funds are kept for a diagnostic.
  5. Scoring within each AMFI category with scoring.score_and_rank and the weights.ini weights and policy.
  6. Forward return = (NAV(T + h) / NAV(T)) ** (1/h) - 1, NAV on or before each date, from the full series.
     Forward EXCESS = forward return minus the median forward return of all evaluable funds in the same category
     and rank date, so categories can be pooled.
  7. Statistics on funds that were ranked in categories with at least --min-funds ranked funds:
       * Spearman rank correlation (IC) between the tool's ranking score (composite_score, the order of the rank
         column) and forward excess, pooled across categories per rank date, averaged over dates; one-sided
         permutation p-value: whole FUNDS are shuffled inside each category, with the same relabelling on every rank
         date (a fund keeps its forward-return history together; seeded)
       * quartiles of the ranking (Q1 = top 25% within the category): n, mean forward return and excess, hit rate;
         Q1 minus Q4 spread of the mean forward excess with a 90% cluster-bootstrap interval (funds resampled, each
         bringing all of its rank dates)
       * baselines: the same IC for the 0-100 score, for trailing 3-year CAGR alone and trailing 1-year CAGR alone,
         and for each weighted metric on its own
       * a diagnostic comparing funds removed by the hard filters with the ones kept

OUTPUT (in --output-dir, default "output"): walk_forward.csv (one row per fund per rank date),
walk_forward_summary.csv (per date and category, and pooled), walk_forward.md (the report), walk_forward_log.txt.
Exit status: 0 wrote output; 1 nothing could be evaluated; 2 bad command line, bad weights file, bad date, or the
NAV data does not reach the forward window (the message says how far it must reach).

READ THIS: a result here is one market period, a few hundred fund-observations at best, with overlapping windows,
survivors only, an index-fund proxy as benchmark where no TRI csv exists, and no point-in-time portfolio quality.
It can tell you whether the ranking carried information in THIS sample; it cannot tell you it will next time.
It is not investment advice.
"""

import argparse
import math
import os
import sys
import zlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import benchmark
import config
import extra_metrics
import fetch_nav_data
import fund_universe
import scoring
import weights_loader
from metrics import compute_all_metrics, years_of_history

MIN_EVAL_HISTORY_YEARS = 1.0     # a fund with less history than this at T is not evaluable
WINDOW_TOLERANCE_DAYS = 7        # data may end this many days before T + horizon and still cover it

MAIN_SCORE = "composite_score"   # the column the tool sorts by (so "top-ranked" means exactly what the rank column shows)

ST_RANKED, ST_INSUFF = "RANKED", "INSUFFICIENT_DATA"
ST_FILTERED = "EXCLUDED_HARD_FILTER"
ST_STALE, ST_WINDOW, ST_NOEVAL = "DROPPED_STALE", "DROPPED_FORWARD_WINDOW", "NOT_EVALUABLE"
EVALUABLE_STATUSES = (ST_RANKED, ST_INSUFF, ST_FILTERED)

OUT_COLS = [
    "rank_date", "category", "scheme_code", "scheme_name", "status", "exclusion_reasons", "in_statistics",
    "rank", "final_score_0_100", "composite_score", "score_coverage", "score_missing", "quartile",
    "history_years", "cagr_1y", "cagr_3y", "cagr_5y", "volatility", "risk_return_ratio", "sortino_ratio",
    "max_drawdown", "rolling_positive_pct", "sip_xirr", "benchmark_excess_return",
    "rolling_beat_benchmark_pct", "downside_capture", "jensen_alpha", "beta", "quartile_consistency",
    "nav_at_rank_date", "nav_at_horizon", "forward_return", "forward_excess",
]

METRIC_LABELS = {
    "cagr_1y": "1y CAGR", "cagr_3y": "3y CAGR", "cagr_5y": "5y CAGR", "risk_return_ratio": "Sharpe-style ratio",
    "sortino_ratio": "Sortino ratio", "rolling_positive_pct": "Rolling windows positive",
    "sip_xirr": "SIP XIRR", "max_drawdown": "Max drawdown (3y)", "benchmark_excess_return": "Excess vs benchmark",
    "rolling_beat_benchmark_pct": "Rolling beat-benchmark %", "portfolio_quality": "Portfolio quality",
    "downside_capture": "Downside capture", "quartile_consistency": "Quartile consistency",
    "jensen_alpha": "Jensen alpha", "beta": "Beta",
}


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------
class Log:
    """List of lines written to walk_forward_log.txt; everything is also printed."""

    def __init__(self, echo=True):
        self.lines, self.echo = [], echo

    def add(self, text=""):
        self.lines.append(str(text))
        if self.echo:
            print(text)

    def warn(self, text):
        self.add(f"WARNING: {text}")

    def write(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")


class InputError(Exception):
    """Fatal problem with the command line or the data window (exit status 2)."""


def quarter_ends(year):
    return [pd.Timestamp(year=year, month=m, day=d) for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))]


def norm_category(scheme_category, fallback):
    """'Equity Scheme - Small Cap Fund' -> 'small cap fund'; blank/missing -> the requested category."""
    if isinstance(scheme_category, str) and scheme_category.strip():
        return scheme_category.split(" - ")[-1].strip().lower()
    return str(fallback or "unknown").lower()


def _nav_on_or_before(dates, navs, target):
    """NAV on the last date <= target from sorted numpy arrays, or None."""
    pos = np.searchsorted(dates, np.datetime64(target), side="right") - 1
    return None if pos < 0 else float(navs[pos])


def _pct(x, digits=1):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x * 100:.{digits}f}%"


def _num(x, digits=3):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{digits}f}"


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def _rng(seed, label):
    return np.random.default_rng([int(seed), zlib.crc32(str(label).encode("utf-8"))])


# --------------------------------------------------------------------------------------
# Loading the data (once)
# --------------------------------------------------------------------------------------
def _offline_reader(code, force_refresh=False):
    path = os.path.join(config.DATA_DIR, f"{code}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"no cached NAV file {path}")
    return pd.read_csv(path, parse_dates=["date"])


def _clean_nav(df):
    df = df[["date", "nav"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    return df.dropna().drop_duplicates("date").sort_values("date").reset_index(drop=True)


def load_universe(categories, args, log):
    """-> (funds dict, info). funds[code] = {name, category, scheme_category, requested, df, dates, navs, last}."""
    cands = {}
    for cat in categories:
        canonical, lst = fund_universe.find_candidates(cat, force_refresh=bool(args.refresh and not args.offline))
        lst = sorted(lst, key=lambda c: c["scheme_name_hint"])
        if len(lst) > args.max_funds_per_category:
            log.warn(f"{canonical}: {len(lst)} candidates, using the first {args.max_funds_per_category} alphabetically "
                     f"(--max-funds-per-category)")
            lst = lst[:args.max_funds_per_category]
        log.add(f"{canonical}: {len(lst)} current Direct-Growth candidate(s)")
        for c in lst:
            cands.setdefault(str(c["scheme_code"]), {"requested": canonical, "hint": c["scheme_name_hint"]})

    def one(code):
        try:
            df = (fetch_nav_data.get_nav_history(code, force_refresh=bool(args.refresh and not args.offline)))
            return code, _clean_nav(df), None
        except Exception as exc:                       # a failed fund is skipped and counted, never fatal
            return code, None, str(exc)[:100]

    funds, failed = {}, []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        for i, (code, df, err) in enumerate(ex.map(one, list(cands)), 1):
            if df is None or df.empty:
                failed.append((code, err or "no NAV rows"))
                continue
            meta = fetch_nav_data.get_scheme_meta(code) or {}
            raw_cat = meta.get("scheme_category")
            raw_cat = raw_cat if isinstance(raw_cat, str) else ""
            name = meta.get("scheme_name")
            name = name if isinstance(name, str) and name else cands[code]["hint"]
            funds[code] = {"name": name, "scheme_category": raw_cat, "requested": cands[code]["requested"],
                           "category": norm_category(raw_cat, cands[code]["requested"]), "df": df,
                           "dates": df["date"].to_numpy(), "navs": df["nav"].to_numpy(float),
                           "last": df["date"].max()}
            if i % 25 == 0:
                log.add(f"  {i}/{len(cands)} NAV histories loaded")
    for code, why in failed[:10]:
        log.warn(f"{code}: skipped ({why})")
    if len(failed) > 10:
        log.warn(f"... and {len(failed) - 10} more skipped")
    if funds:
        newest = max(f["last"] for f in funds.values())
        for f in funds.values():
            f["stale_days"] = int((newest - f["last"]).days)
            f["stale"] = f["stale_days"] > config.STALE_NAV_DAYS
    return funds, {"candidates": len(cands), "failed": len(failed)}


class _TruncatedProvider:
    """Hands out the benchmark series cut at T, so nothing after the rank date can reach a metric."""

    def __init__(self, provider, T):
        self.provider, self.T, self._cache = provider, pd.Timestamp(T), {}

    def get(self, key):
        if key is None or self.provider is None:
            return None
        if key not in self._cache:
            b = self.provider.get(key)
            if b is None:
                self._cache[key] = None
            else:
                df = b["df"][b["df"]["date"] <= self.T].reset_index(drop=True)
                self._cache[key] = dict(b, df=df) if len(df) else None
        return self._cache[key]


# --------------------------------------------------------------------------------------
# One rank date
# --------------------------------------------------------------------------------------
def assign_quartiles(scores):
    """Quartile 1 (best) to 4 from the average rank by score, descending; ties share the average rank."""
    s = pd.Series(scores, dtype=float)
    n = int(s.notna().sum())
    if n == 0:
        return pd.Series(np.nan, index=s.index)
    r = s.rank(ascending=False, method="average")
    return np.ceil(4.0 * r / n - 1e-9).clip(1, 4)


def process_date(T, funds, ctx):
    """-> (DataFrame with one row per fund, counts dict). No data after T reaches any metric."""
    T = pd.Timestamp(T)
    h_end = T + pd.Timedelta(days=ctx["h_days"])
    tp = _TruncatedProvider(ctx["bench"], T) if ctx["bench"] is not None else None
    w = config.SCORE_WEIGHTS
    rows, mrows = [], []
    for code, f in sorted(funds.items()):
        base = {"rank_date": T.date().isoformat(), "category": f["category"], "scheme_code": code,
                "scheme_name": f["name"]}
        if f["stale"]:
            rows.append(dict(base, status=ST_STALE, exclusion_reasons=(
                f"last NAV {f['last'].date()} is {f['stale_days']} days older than the newest NAV loaded")))
            continue
        if f["last"] < h_end - pd.Timedelta(days=WINDOW_TOLERANCE_DAYS):
            rows.append(dict(base, status=ST_WINDOW, exclusion_reasons=(
                f"NAV data ends {f['last'].date()}, before the forward window end {h_end.date()}")))
            continue
        trunc = f["df"][f["df"]["date"] <= T].reset_index(drop=True)
        if trunc.empty or years_of_history(trunc) < MIN_EVAL_HISTORY_YEARS:
            rows.append(dict(base, status=ST_NOEVAL, exclusion_reasons=(
                "no NAV on or before the rank date" if trunc.empty else
                f"only {years_of_history(trunc):.1f} years of history at the rank date")))
            continue
        m = compute_all_metrics(
            trunc, config.RISK_FREE_RATE, sip_years=config.SIP_YEARS, sip_monthly_amount=config.SIP_MONTHLY_AMOUNT,
            rolling_window_years=config.ROLLING_WINDOW_YEARS, align_ratio_window=config.RATIO_ALIGN_WINDOW,
            drawdown_window_years=config.DRAWDOWN_WINDOW_YEARS)
        m.update(benchmark.metrics_for_fund(trunc, tp, f["scheme_category"], f["requested"]))
        bench = tp.get(benchmark.category_key(f["scheme_category"], f["requested"])) if tp is not None else None
        m["downside_capture"] = (extra_metrics.downside_capture(trunc, bench["df"])
                                 if bench and w.get("downside_capture", 0) > 0 else None)
        ab = (extra_metrics.alpha_beta(trunc, bench["df"], config.RISK_FREE_RATE, years=config.ALPHA_BETA_YEARS,
                                       min_months=config.ALPHA_BETA_MIN_MONTHS,
                                       max_staleness_days=config.BENCHMARK_MAX_STALENESS_DAYS)
              if bench and (w.get("jensen_alpha", 0) > 0 or w.get("beta", 0) > 0) else extra_metrics.EMPTY_ALPHA_BETA)
        m.update(ab)
        m["portfolio_quality"] = None                    # holdings files are today's, not point-in-time
        m["quartile_consistency"] = None
        m["_rolling"] = None
        if w.get("quartile_consistency", 0) > 0:
            try:
                m["_rolling"] = benchmark._rolling_cagr(benchmark._month_end_nav(trunc), config.ROLLING_WINDOW_YEARS)
            except Exception:
                m["_rolling"] = None
        start = float(trunc["nav"].iloc[-1])
        end = _nav_on_or_before(f["dates"], f["navs"], h_end)
        fwd = (end / start) ** (1.0 / ctx["horizon"]) - 1.0 if (end and start > 0 and end > 0) else None
        m.update(base, nav_at_rank_date=start, nav_at_horizon=end, forward_return=fwd)
        mrows.append(m)

    counts = {"loaded": len(funds)}
    for st in (ST_STALE, ST_WINDOW, ST_NOEVAL):
        counts[st] = sum(1 for r in rows if r["status"] == st)
    if not mrows:
        counts.update(evaluable=0, filtered=0, ranked=0, in_stats=0, small_groups=[])
        return pd.DataFrame(rows), counts

    mdf = pd.DataFrame(mrows)
    mdf["forward_return"] = pd.to_numeric(mdf["forward_return"], errors="coerce")
    med = mdf.groupby("category")["forward_return"].transform("median")
    mdf["forward_excess"] = mdf["forward_return"] - med

    if w.get("quartile_consistency", 0) > 0:               # peers = the evaluable funds of the category at T
        for cat, g in mdf.groupby("category"):
            q = extra_metrics.quartile_consistency({c: s for c, s in zip(g["scheme_code"], g["_rolling"])},
                                                   min_peers=config.QUARTILE_MIN_PEERS)
            for i in g.index:
                mdf.at[i, "quartile_consistency"] = q.get(mdf.at[i, "scheme_code"], {}).get("quartile_consistency")
    mdf = mdf.drop(columns=["_rolling"])
    mdf["quartile_consistency"] = pd.to_numeric(mdf["quartile_consistency"], errors="coerce")

    reasons = {}
    if ctx["hard_filters"]:
        import shortlist                                   # lazy: the real shortlist.py pulls in many modules
        surv, reasons = shortlist.apply_hard_filters(mdf.copy(), return_reasons=True, log=lambda s: None)
    else:
        surv = mdf.copy()
    surv_codes = set(surv["scheme_code"].astype(str))
    removed = mdf[~mdf["scheme_code"].astype(str).isin(surv_codes)].copy()
    removed["status"] = ST_FILTERED
    removed["exclusion_reasons"] = [", ".join(reasons.get(c, [])) for c in removed["scheme_code"]]

    scored = []
    small = []
    for cat, g in surv.groupby("category"):
        sc = scoring.score_and_rank(g.reset_index(drop=True), config.SCORE_WEIGHTS, policy=config.MISSING_DATA_POLICY,
                                    min_coverage=config.MIN_SCORE_COVERAGE, method=config.SCORING_METHOD,
                                    min_group_size=config.MIN_GROUP_SIZE)
        ok = sc["status"] == ST_RANKED
        sc["in_statistics"] = ok & (int(ok.sum()) >= ctx["min_funds"])
        sc["quartile"] = np.nan
        if int(ok.sum()) >= ctx["min_funds"]:
            sc.loc[ok, "quartile"] = assign_quartiles(sc.loc[ok, MAIN_SCORE]).to_numpy()
        elif int(ok.sum()) > 0:
            small.append((cat, int(ok.sum())))
        scored.append(sc)
    out = [pd.DataFrame(rows)]
    if scored:
        out.append(pd.concat(scored, ignore_index=True))
    if len(removed):
        out.append(removed)
    full = pd.concat([o for o in out if len(o)], ignore_index=True)
    full["in_statistics"] = full["in_statistics"].fillna(False).astype(bool) if "in_statistics" in full else False
    counts.update(evaluable=len(mdf), filtered=len(removed),
                  ranked=int((full["status"] == ST_RANKED).sum()), in_stats=int(full["in_statistics"].sum()),
                  small_groups=small)
    return full, counts


# --------------------------------------------------------------------------------------
# Statistics (numpy / pandas only)
# --------------------------------------------------------------------------------------
def _centered_ranks(x):
    r = pd.Series(np.asarray(x, float)).rank(method="average").to_numpy(float)
    return r - r.mean()


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3:
        return float("nan")
    ra, rb = _centered_ranks(a), _centered_ranks(b)
    den = math.sqrt(float((ra ** 2).sum()) * float((rb ** 2).sum()))
    return float((ra * rb).sum() / den) if den > 0 else float("nan")


def ic_perm(dates, cats, funds, score, target, n_perm, seed, label, min_n=3):
    """Mean over rank dates of the Spearman correlation between score and target (each date pooled over its
    categories), with a one-sided permutation p-value (H1: a higher score goes with a higher target).

    The null shuffles the target between FUNDS inside each category, with the SAME relabelling on every rank date:
    a fund keeps its whole forward-return history together, and is only exchanged with funds that appear on exactly
    the same rank dates, so every (date, category) group keeps exactly its members. The same fund is seen on several
    overlapping dates; shuffling each date separately would ignore that and give p-values that are too small.
    Returns {n, n_dates, per_date {date: (ic, n)}, mean_ic, p}."""
    dates, cats, funds = (np.asarray(x).astype(str) for x in (dates, cats, funds))
    score, target = np.asarray(score, float), np.asarray(target, float)
    n = len(score)
    out = {"n": int(n), "n_dates": 0, "per_date": {}, "mean_ic": float("nan"), "p": float("nan")}
    if n < min_n:
        return out
    udates = sorted(set(dates))
    di = {d: i for i, d in enumerate(udates)}
    didx = np.array([di[d] for d in dates])
    D = len(udates)
    s_c, t_c = np.zeros(n), np.zeros(n)
    for k in range(D):
        m = didx == k
        s_c[m], t_c[m] = _centered_ranks(score[m]), _centered_ranks(target[m])
    num_obs = np.bincount(didx, weights=s_c * t_c, minlength=D)
    norm = np.sqrt(np.bincount(didx, weights=s_c ** 2, minlength=D) * np.bincount(didx, weights=t_c ** 2, minlength=D))
    seg_n = np.bincount(didx, minlength=D)
    valid = (norm > 0) & (seg_n >= min_n)
    if not valid.any():
        return out
    ic_d = np.where(valid, num_obs / np.where(norm > 0, norm, 1.0), np.nan)
    out["per_date"] = {udates[k]: (float(ic_d[k]), int(seg_n[k])) for k in range(D)}
    out["n_dates"] = int(valid.sum())
    out["mean_ic"] = float(np.nanmean(ic_d[valid]))
    if not n_perm or n_perm <= 0:
        return out

    rows_of = {}                                           # (category, fund) -> {date index: row}
    for r in range(n):
        rows_of.setdefault((cats[r], funds[r]), {})[int(didx[r])] = r
    blocks = {}                                            # (category, dates present) -> [rows of each fund]
    for (cat, _fund), by_date in rows_of.items():
        cols = tuple(sorted(by_date))
        blocks.setdefault((cat, cols), []).append([by_date[c] for c in cols])
    rng = _rng(seed, label)
    num = np.zeros((n_perm, D))
    for (_cat, cols), members in sorted(blocks.items()):
        R = np.asarray(members)                            # (funds, dates present)
        nf = R.shape[0]
        perm = np.argsort(rng.random((n_perm, nf)), axis=1) if nf > 1 else np.zeros((n_perm, 1), dtype=int)
        T = t_c[R][perm]                                   # (permutations, funds, dates): shuffled target ranks
        num[:, list(cols)] += (s_c[R][None, :, :] * T).sum(axis=1)
    null = (num[:, valid] / norm[valid]).mean(axis=1)
    out["p"] = float((1 + int((null >= out["mean_ic"] - 1e-12).sum())) / (n_perm + 1))
    return out


def bootstrap_spread(f1, v1, f4, v4, n_boot, seed, label):
    """(spread, lo, hi): mean(v1) - mean(v4) and a 90% interval. FUNDS are resampled with replacement and every
    resampled fund brings all of its rank dates (a cluster bootstrap), so the overlap between dates is respected.
    f1/v1: fund ids and values of the top-quartile rows; f4/v4: the same for the bottom quartile."""
    f1, f4 = [str(x) for x in f1], [str(x) for x in f4]
    v1, v4 = np.asarray(v1, float), np.asarray(v4, float)
    if len(v1) < 2 or len(v4) < 2:
        return float("nan"), float("nan"), float("nan")
    spread = float(v1.mean() - v4.mean())
    if not n_boot:
        return spread, float("nan"), float("nan")
    ids = sorted(set(f1) | set(f4))
    ix = {f: i for i, f in enumerate(ids)}
    nF = len(ids)
    s1, c1, s4, c4 = (np.zeros(nF) for _ in range(4))
    for f, v in zip(f1, v1):
        s1[ix[f]] += v
        c1[ix[f]] += 1
    for f, v in zip(f4, v4):
        s4[ix[f]] += v
        c4[ix[f]] += 1
    W = _rng(seed, label).multinomial(nF, np.full(nF, 1.0 / nF), size=n_boot).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        d = (W @ s1) / (W @ c1) - (W @ s4) / (W @ c4)
    d = d[np.isfinite(d)]
    if len(d) < 10:
        return spread, float("nan"), float("nan")
    return spread, float(np.percentile(d, 5)), float(np.percentile(d, 95))


def _within_group_pct(df, col, sign=1.0):
    """Percentile (0..1) of sign*col inside each (rank_date, category) group; NaN stays NaN."""
    v = df[col].astype(float) * sign
    g = df.assign(_v=v).groupby(["rank_date", "category"])["_v"]
    r = g.rank(method="average")
    n = g.transform("count")
    return ((r - 1) / (n - 1).replace(0, np.nan)).where(n > 1, 0.5).where(v.notna())


def analyse(all_df, args, weights):
    """All statistics for the report. all_df is the concatenation of every rank date's rows."""
    res = {"empty": True}
    S = all_df[(all_df["in_statistics"]) & all_df["forward_excess"].notna()].copy()
    if S.empty:
        return res
    res["empty"] = False
    S["group"] = S["rank_date"] + "|" + S["category"]
    res["n_stats"] = int(len(S))
    res["S"] = S
    n_perm, seed = args.permutations, args.seed

    main = ic_perm(S["rank_date"], S["category"], S["scheme_code"], S[MAIN_SCORE], S["forward_excess"], n_perm, seed, "main")
    res["main"] = main

    q = S[S["quartile"].notna()]
    qrows = []
    for k in (1, 2, 3, 4):
        g = q[q["quartile"] == k]
        qrows.append({"quartile": k, "n": int(len(g)), "mean_fwd": float(g["forward_return"].mean()) if len(g) else np.nan,
                      "mean_excess": float(g["forward_excess"].mean()) if len(g) else np.nan,
                      "hit": float((g["forward_excess"] > 0).mean()) if len(g) else np.nan})
    res["quartiles"] = qrows
    top, bot = q[q["quartile"] == 1], q[q["quartile"] == 4]
    res["spread"] = bootstrap_spread(top["scheme_code"], top["forward_excess"], bot["scheme_code"], bot["forward_excess"],
                                     args.bootstrap, seed, "spread")

    per_date = []
    for d, g in S.groupby("rank_date"):
        icd = main["per_date"].get(d, (float("nan"), 0))
        g1, g4 = g[g["quartile"] == 1], g[g["quartile"] == 4]
        per_date.append({"rank_date": d, "n": int(len(g)), "ic": icd[0],
                         "q1": float(g1["forward_excess"].mean()) if len(g1) else np.nan,
                         "q4": float(g4["forward_excess"].mean()) if len(g4) else np.nan,
                         "hit1": float((g1["forward_excess"] > 0).mean()) if len(g1) else np.nan})
    res["per_date"] = per_date

    per_cat = []
    for cat, g in S.groupby("category"):
        ics = [spearman(gg[MAIN_SCORE], gg["forward_excess"]) for _, gg in g.groupby("rank_date") if len(gg) >= 3]
        ics = [x for x in ics if np.isfinite(x)]
        g1, g4 = g[g["quartile"] == 1], g[g["quartile"] == 4]
        per_cat.append({"category": cat, "n": int(len(g)), "dates": g["rank_date"].nunique(),
                        "ic": float(np.mean(ics)) if ics else np.nan,
                        "q1": float(g1["forward_excess"].mean()) if len(g1) else np.nan,
                        "q4": float(g4["forward_excess"].mean()) if len(g4) else np.nan})
    res["per_cat"] = per_cat

    def one(col, sign, label, pct=True):
        sub = S[S[col].notna()].copy()
        if len(sub) < 10:
            return {"n": int(len(sub)), "mean_ic": np.nan, "p": np.nan, "n_dates": 0}
        score = _within_group_pct(sub, col, sign) if pct else sub[col] * sign
        return ic_perm(sub["rank_date"], sub["category"], sub["scheme_code"], score, sub["forward_excess"], n_perm, seed, label)

    base = [("The 0-100 score shown in the reports (final_score_0_100)", one("final_score_0_100", 1.0, "base_final", pct=False)),
            ("Trailing 3y CAGR alone", one("cagr_3y", 1.0, "base_cagr3")),
            ("Trailing 1y CAGR alone", one("cagr_1y", 1.0, "base_cagr1"))]
    res["baselines"] = base
    per_metric = []
    for m, wt in weights.items():
        if wt and wt > 0:
            if m not in S.columns or S[m].notna().sum() < 10:
                per_metric.append((m, wt, {"n": int(S[m].notna().sum()) if m in S.columns else 0, "mean_ic": np.nan,
                                           "p": np.nan, "n_dates": 0}))
                continue
            per_metric.append((m, wt, one(m, -1.0 if m in scoring.LOWER_IS_BETTER else 1.0, "metric_" + m)))
    res["per_metric"] = per_metric

    ev = all_df[all_df["status"].isin(EVALUABLE_STATUSES) & all_df["forward_excess"].notna()]
    kept, gone = ev[ev["status"] != ST_FILTERED], ev[ev["status"] == ST_FILTERED]
    res["filter_diag"] = {"kept_n": int(len(kept)), "kept_mean": float(kept["forward_excess"].mean()) if len(kept) else np.nan,
                          "gone_n": int(len(gone)), "gone_mean": float(gone["forward_excess"].mean()) if len(gone) else np.nan}
    return res


def reading(res, args):
    """One hedged sentence, driven by thresholds, never stronger than the numbers."""
    if res["empty"]:
        return "No statistics could be computed: no category had enough ranked funds."
    ic, p, (spread, lo, hi) = res["main"]["mean_ic"], res["main"]["p"], res["spread"]
    n = res["n_stats"]
    if n < 30 or not np.isfinite(ic):
        return (f"Only {n} fund-observations were available, too few to say anything reliable about whether the "
                f"ranking carried information.")
    if ic > 0 and np.isfinite(p) and p < 0.05 and np.isfinite(lo) and lo > 0:
        return (f"In this sample there is evidence that the ranking carried information: higher-scored funds had better "
                f"forward returns (mean IC {ic:.3f}, permutation p = {p:.3f}; Q1 beat Q4 by {_pct(spread)} a year, 90% "
                f"interval {_pct(lo)} to {_pct(hi)}). This is one period with overlapping windows and survivors only, "
                f"so it is not proof the pattern will repeat.")
    if ic < 0:
        return (f"In this sample the score was, if anything, negatively related to forward returns (mean IC {ic:.3f}); "
                f"higher-scored funds did NOT do better afterwards.")
    return (f"There is no reliable evidence in this sample that the ranking carried information (mean IC {ic:.3f}, "
            f"permutation p = {_num(p)}; Q1 minus Q4 spread {_pct(spread)}, 90% interval {_pct(lo)} to {_pct(hi)}). "
            f"That is not the same as proof that it carries none: the sample is small and covers one period.")


# --------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------
def build_report(res, all_df, counts, args, dates, load_info, win_info):
    L = ["# Walk-forward validation of the fund score", ""]
    L.append("_Screens PAST data. This is not investment advice and says nothing certain about the future._")
    L.append("")
    L.append("## Reading")
    L.append("")
    L.append(reading(res, args))
    L.append("")
    L.append("## Settings")
    L.append("")
    L += [
        f"- Rank dates: {', '.join(d.date().isoformat() for d in dates)} "
        + ("(the four quarter-ends of the rank year; the user fixed only the year)" if not args.rank_date else "(given with --rank-date)"),
        f"- Forward horizon: {args.horizon_years:g} years (forward return = annualised NAV change from the rank date)",
        "- Universe: today's Direct-Growth schemes of the requested categories; SURVIVORS only (decided by the user)",
        f"- Weights file: {config.WEIGHTS_FILE} (version {config.WEIGHTS_VERSION}); policy {config.MISSING_DATA_POLICY}; "
        f"method {config.SCORING_METHOD}; coverage floor {config.MIN_SCORE_COVERAGE:.0%}",
        "- Weights %: " + ", ".join(f"{m}={w * 100:g}" for m, w in config.SCORE_WEIGHTS.items() if w > 0),
        "- portfolio_quality: not available point-in-time (holdings files are today's), so it is missing for every "
        "fund and the missing-data policy rescales the other weights",
        f"- Hard filters (today's config.py thresholds, applied as of each rank date): {'off (--no-hard-filters)' if args.no_hard_filters else 'on'}",
        f"- Statistics use categories with at least {args.min_funds} ranked funds on a rank date",
        f"- Permutations {args.permutations}, bootstrap {args.bootstrap}, seed {args.seed}",
        f"- Categories: {', '.join(win_info['categories'])}; {load_info['candidates']} candidate funds, {load_info['failed']} could not be loaded",
        "",
    ]
    L.append("## Fund counts per rank date")
    L.append("")
    rows = []
    for d in dates:
        c = counts[d.date().isoformat()]
        rows.append([d.date().isoformat(), c["loaded"], c[ST_STALE], c[ST_WINDOW], c[ST_NOEVAL], c["evaluable"],
                     c["filtered"], c["ranked"], c["in_stats"]])
    L += _table(["Rank date", "Loaded", "Dropped: NAV stopped updating", "Dropped: window not covered",
                 "Not evaluable at date", "Evaluable", "Removed by hard filters", "Ranked", "In statistics"], rows)
    L.append("")
    small = [(d.date().isoformat(), cat, n) for d in dates for cat, n in counts[d.date().isoformat()]["small_groups"]]
    if small:
        L.append("Categories with too few ranked funds to be included in the statistics: "
                 + "; ".join(f"{d} {cat} ({n})" for d, cat, n in small) + ".")
        L.append("")
    if res["empty"]:
        L += ["## Results", "", "No category reached the minimum size, so there are no statistics to show.", ""]
    else:
        L.append("## Per rank date")
        L.append("")
        L += _table(["Rank date", "Funds", "IC (score vs forward excess)", "Q1 mean excess", "Q4 mean excess", "Q1 hit rate"],
                    [[r["rank_date"], r["n"], _num(r["ic"]), _pct(r["q1"]), _pct(r["q4"]), _pct(r["hit1"], 0)]
                     for r in res["per_date"]])
        L.append("")
        m = res["main"]
        L.append(f"**Mean IC over dates: {_num(m['mean_ic'])}** (one-sided permutation p = {_num(m['p'])}; "
                 f"{res['n_stats']} fund-observations over {m['n_dates']} rank date(s)). IC is the Spearman rank "
                 f"correlation between the tool's ranking score (`composite_score`, the order of the rank column) and the "
                 f"forward return minus the category median; 0 means no "
                 f"relationship. The same funds appear on several overlapping dates, so the p-value shuffles whole funds (the "
                 f"same relabelling on every date). Even so, the dates are not independent tests: the real amount of "
                 f"information is closer to the number of funds than to the number of fund-dates.")
        L.append("")
        L.append("## Quartiles of the score (pooled over dates and categories)")
        L.append("")
        L += _table(["Quartile", "Funds", "Mean forward return (a year)", "Mean excess vs category median", "Hit rate (beat median)"],
                    [[("Q%d%s" % (r["quartile"], " (top)" if r["quartile"] == 1 else " (bottom)" if r["quartile"] == 4 else "")),
                      r["n"], _pct(r["mean_fwd"]), _pct(r["mean_excess"]), _pct(r["hit"], 0)] for r in res["quartiles"]])
        L.append("")
        sp, lo, hi = res["spread"]
        L.append(f"Q1 minus Q4 mean excess: **{_pct(sp)}** a year, 90% interval {_pct(lo)} to {_pct(hi)} (funds resampled "
                 f"with replacement, each bringing all of its rank dates, so the overlap between dates is respected).")
        L.append("")
        L.append("## Per category")
        L.append("")
        L += _table(["Category", "Fund-observations", "Dates", "Mean IC within category", "Q1 mean excess", "Q4 mean excess"],
                    [[r["category"], r["n"], r["dates"], _num(r["ic"]), _pct(r["q1"]), _pct(r["q4"])] for r in res["per_cat"]])
        L.append("")
        L.append("## Does the score add anything over plain past return?")
        L.append("")
        rows = [["**The tool's ranking (composite_score)**", res["main"]["n"], _num(res["main"]["mean_ic"]), _num(res["main"]["p"])]]
        rows += [[n, b["n"], _num(b["mean_ic"]), _num(b["p"])] for n, b in res["baselines"]]
        L += _table(["Ranking used", "Fund-observations", "Mean IC", "Permutation p"], rows)
        L.append("")
        L.append("Differences between these rows are not tested; with this sample size they are usually within noise.")
        L.append("")
        L.append("## Each weighted metric on its own")
        L.append("")
        L += _table(["Metric", "Weight %", "Fund-observations", "Mean IC", "Permutation p"],
                    [[METRIC_LABELS.get(mm, mm), f"{w * 100:g}", b["n"], _num(b["mean_ic"]), _num(b["p"])]
                     for mm, w, b in res["per_metric"]])
        L.append("")
        L.append("Direction-adjusted (lower-is-better metrics are flipped). This is many small tests on a small sample: "
                 "some will look good or bad by chance alone, so do not re-tune weights from this table.")
        L.append("")
        fd = res["filter_diag"]
        L.append("## Hard-filter diagnostic")
        L.append("")
        L += _table(["Group", "Fund-observations", "Mean forward excess vs category median"],
                    [["Kept by the filters", fd["kept_n"], _pct(fd["kept_mean"])],
                     ["Removed by the filters", fd["gone_n"], _pct(fd["gone_mean"])]])
        L.append("")
        L.append("Descriptive only. If removed funds did as well as kept ones, the filters are not helping in this sample.")
        L.append("")
    L.append("## What this can and cannot tell you")
    L.append("")
    L += [
        "- **Survivorship.** Only funds that still exist today were used. Funds that closed or merged were mostly weak, "
        "so their absence usually raises the forward return of low-ranked funds and tends to UNDERSTATE how well a "
        "score separates winners from losers. The size of this effect cannot be measured here.",
        "- **Overlapping windows.** The rank dates are a few months apart and the forward windows are 2 years long, so "
        "they share most of their data. They are not independent tests.",
        "- **One market regime.** Everything covers the same stretch of market. A ranking that worked (or failed) here "
        "may behave differently in another.",
        "- **Benchmark.** Without a TRI csv the benchmark is an index-fund proxy, which may not have existed at the rank "
        "date (then the benchmark metrics are missing and the weights are rescaled) and trails the true index slightly.",
        "- **Portfolio quality is not tested**, and the hard-filter thresholds are today's, not those you might have used then.",
        "- **Significance.** The p-value and interval above are what the sample supports. No claim of significance "
        "should be made without them, and they do not correct for the many things tried.",
        "- It tests the **ranking within a category**, not whether to invest, how much, or in which category.",
        "",
        "_Past performance does not guarantee future results. Not investment advice._",
        "",
    ]
    return "\n".join(L)


def summary_frame(res, all_df, dates):
    rows = []
    S = res.get("S")
    for d in dates:
        ds = d.date().isoformat()
        ev = all_df[(all_df["rank_date"] == ds) & all_df["status"].isin(EVALUABLE_STATUSES)]
        for cat in sorted(ev["category"].unique()):
            e = ev[ev["category"] == cat]
            g = S[(S["rank_date"] == ds) & (S["category"] == cat)] if S is not None else pd.DataFrame()
            ic = spearman(g[MAIN_SCORE], g["forward_excess"]) if len(g) >= 3 else np.nan
            rows.append({"scope": ds, "category": cat, "n_evaluable": len(e), "n_in_statistics": len(g), "ic": ic,
                         "q1_mean_excess": g.loc[g["quartile"] == 1, "forward_excess"].mean() if len(g) else np.nan,
                         "q4_mean_excess": g.loc[g["quartile"] == 4, "forward_excess"].mean() if len(g) else np.nan})
    if S is not None and len(S):
        for r in res["per_date"]:
            rows.append({"scope": r["rank_date"], "category": "ALL (pooled)", "n_evaluable": np.nan, "n_in_statistics": r["n"],
                         "ic": r["ic"], "q1_mean_excess": r["q1"], "q4_mean_excess": r["q4"]})
        rows.append({"scope": "ALL DATES", "category": "ALL (pooled)", "n_evaluable": np.nan, "n_in_statistics": res["n_stats"],
                     "ic": res["main"]["mean_ic"], "q1_mean_excess": res["quartiles"][0]["mean_excess"],
                     "q4_mean_excess": res["quartiles"][3]["mean_excess"]})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------
def _parse_args(argv):
    ap = argparse.ArgumentParser(prog="walk_forward.py", description="Walk-forward validation of the fund score "
                                 "(see the top of this file).")
    ap.add_argument("--rank-year", type=int, default=2023, help="run at the four quarter-ends of this year (default 2023)")
    ap.add_argument("--rank-date", action="append", default=[], help="YYYY-MM-DD rank date (repeatable; overrides --rank-year)")
    ap.add_argument("--horizon-years", type=float, default=2.0, help="forward horizon in years (default 2)")
    ap.add_argument("--category", action="append", default=[], help="category to test (repeatable; default: all but sectoral)")
    ap.add_argument("--max-funds-per-category", type=int, default=200)
    ap.add_argument("--weights", help="weights file (default: weights.ini next to config.py)")
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--refresh", action="store_true", help="re-download NAV data instead of using the cache")
    ap.add_argument("--offline", action="store_true", help="use only the NAV files already cached under data/; no network")
    ap.add_argument("--no-hard-filters", action="store_true", help="do not apply the config.py hard filters")
    ap.add_argument("--permutations", type=int, default=5000)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--min-funds", type=int, default=None, help="minimum ranked funds per category and date (default: min_group_size in weights.ini)")
    return ap.parse_args(argv)


def _validate(args):
    try:
        if args.weights:
            config.apply_weights(args.weights)
    except weights_loader.WeightsError as exc:
        raise InputError(str(exc))
    if not (0 < args.horizon_years <= 10):
        raise InputError("--horizon-years must be between 0 and 10")
    for name in ("permutations", "bootstrap"):
        if getattr(args, name) < 0:
            raise InputError(f"--{name} cannot be negative")
    if args.workers < 1 or args.max_funds_per_category < 1:
        raise InputError("--workers and --max-funds-per-category must be at least 1")
    if args.min_funds is None:
        args.min_funds = config.MIN_GROUP_SIZE
    if args.min_funds < 3:
        raise InputError("--min-funds must be at least 3")
    if args.rank_date:
        dates = []
        for text in args.rank_date:
            d = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
            if pd.isna(d):
                raise InputError(f"--rank-date '{text}' is not a valid YYYY-MM-DD date")
            dates.append(d)
    else:
        if not (1990 <= args.rank_year <= 2100):
            raise InputError(f"--rank-year {args.rank_year} is not a sensible year")
        dates = quarter_ends(args.rank_year)
    cats = args.category or [c for c in fund_universe.supported_categories() if c != "sectoral"]
    return sorted(set(dates)), cats


def main(argv=None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    log = Log()
    try:
        dates, cats = _validate(args)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    h_days = int(args.horizon_years * 365.25)
    os.makedirs(args.output_dir, exist_ok=True)
    log.add(f"Walk-forward validation: rank dates {', '.join(d.date().isoformat() for d in dates)}; "
            f"horizon {args.horizon_years:g}y; survivors only")
    log.add(f"Weights file {config.WEIGHTS_FILE} (version {config.WEIGHTS_VERSION}); policy {config.MISSING_DATA_POLICY}; "
            f"method {config.SCORING_METHOD}")

    saved = (fetch_nav_data.get_nav_history, config.SCHEME_MASTER_CACHE_DAYS)
    try:
        if args.offline:
            if not os.path.exists(fund_universe.ALL_SCHEMES_CACHE):
                print(f"ERROR: --offline needs the cached scheme list {fund_universe.ALL_SCHEMES_CACHE}; "
                      f"run once with internet access first", file=sys.stderr)
                return 2
            fetch_nav_data.get_nav_history = _offline_reader     # benchmark proxies are read from the cache too
            config.SCHEME_MASTER_CACHE_DAYS = 10 ** 6
            log.add("Offline: only cached files under data/ are used")
        try:
            funds, load_info = load_universe(cats, args, log)
        except Exception as exc:
            print(f"ERROR: could not build the fund list ({exc})", file=sys.stderr)
            return 2
        if not funds:
            log.warn("no fund could be loaded; nothing to evaluate")
            log.write(os.path.join(args.output_dir, "walk_forward_log.txt"))
            return 1
        newest = max(f["last"] for f in funds.values())
        for d in dates:
            need = d + pd.Timedelta(days=h_days) - pd.Timedelta(days=WINDOW_TOLERANCE_DAYS)
            if newest < need:
                print(f"ERROR: rank date {d.date()} with a {args.horizon_years:g}-year horizon needs NAV data up to "
                      f"{need.date()} or later, but the newest NAV loaded is {newest.date()}. Choose an earlier "
                      f"--rank-date / --rank-year or a shorter --horizon-years (or refresh the data).", file=sys.stderr)
                return 2
        log.add(f"{len(funds)} funds loaded; newest NAV {newest.date()}; "
                f"{sum(1 for f in funds.values() if f['stale'])} stopped updating (survivor rule)")

        bench = benchmark.BenchmarkProvider(force_refresh=bool(args.refresh and not args.offline)) \
            if config.BENCHMARK_ENABLED else None
        ctx = {"h_days": h_days, "horizon": args.horizon_years, "bench": bench, "min_funds": args.min_funds,
               "hard_filters": not args.no_hard_filters}
        frames, counts = [], {}
        for d in dates:
            log.add(f"\n=== Rank date {d.date()} ===")
            full, c = process_date(d, funds, ctx)
            frames.append(full)
            counts[d.date().isoformat()] = c
            log.add(f"  loaded {c['loaded']}; stale {c[ST_STALE]}; window not covered {c[ST_WINDOW]}; "
                    f"not evaluable {c[ST_NOEVAL]}; evaluable {c['evaluable']}; removed by hard filters {c['filtered']}; "
                    f"ranked {c['ranked']}; in statistics {c['in_stats']}")
        if bench is not None:
            for line in bench.describe():
                log.add("Benchmark: " + line.strip())
    finally:
        fetch_nav_data.get_nav_history, config.SCHEME_MASTER_CACHE_DAYS = saved

    all_df = pd.concat([f for f in frames if len(f)], ignore_index=True)
    for col in OUT_COLS:
        if col not in all_df.columns:
            all_df[col] = np.nan
    all_df["in_statistics"] = all_df["in_statistics"].fillna(False).astype(bool)
    all_df["rank"] = pd.to_numeric(all_df["rank"], errors="coerce")
    for col in ("forward_return", "forward_excess", "final_score_0_100", "composite_score"):
        all_df[col] = pd.to_numeric(all_df[col], errors="coerce")

    res = analyse(all_df, args, config.SCORE_WEIGHTS)
    out = args.output_dir
    all_df[OUT_COLS].to_csv(os.path.join(out, "walk_forward.csv"), index=False)
    summary_frame(res, all_df, dates).to_csv(os.path.join(out, "walk_forward_summary.csv"), index=False)
    report = build_report(res, all_df, counts, args, dates, load_info, {"categories": cats})
    with open(os.path.join(out, "walk_forward.md"), "w", encoding="utf-8") as fh:
        fh.write(report)
    log.add("")
    log.add(reading(res, args))
    log.add(f"Files written to {os.path.abspath(out)}: walk_forward.csv, walk_forward_summary.csv, walk_forward.md, "
            f"walk_forward_log.txt")
    log.write(os.path.join(out, "walk_forward_log.txt"))
    return 1 if res["empty"] else 0


if __name__ == "__main__":
    sys.exit(main())
