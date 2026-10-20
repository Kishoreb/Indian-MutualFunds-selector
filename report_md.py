"""
report_md.py
------------
Human-readable outputs for a ranking run:
  * RunLog              collects everything that happened (printed live and written to run_log.txt)
  * write_markdown()    ranked_funds.md: methodology, weights, ranking tables per category and, for each
                        top fund, every metric's raw value, 0-100 score, weight and points, plus a short
                        rule-based explanation (strengths, weak spots, gaps, risks). No LLM involved.
"""

from datetime import datetime

import numpy as np
import pandas as pd

LABELS = {
    "cagr_1y": "1-year return (CAGR)", "cagr_3y": "3-year return (CAGR)", "cagr_5y": "5-year return (CAGR)",
    "risk_return_ratio": "Sharpe-style ratio", "sortino_ratio": "Sortino ratio",
    "rolling_positive_pct": "Rolling 3y windows positive", "sip_xirr": "SIP XIRR",
    "max_drawdown": "Maximum drawdown", "benchmark_excess_return": "3y excess return vs benchmark",
    "rolling_beat_benchmark_pct": "Rolling windows beating benchmark", "portfolio_quality": "Portfolio quality (0-100)",
    "downside_capture": "Downside capture", "quartile_consistency": "Time in top half of peers",
    "jensen_alpha": "Jensen's alpha (per year, vs benchmark)", "beta": "Beta vs benchmark",
}
DIRECTION = {m: "higher" for m in LABELS}
DIRECTION["downside_capture"] = "lower"
DIRECTION["beta"] = "lower"
DIRECTION["max_drawdown"] = "smaller fall"
PCT = {"cagr_1y", "cagr_3y", "cagr_5y", "rolling_positive_pct", "sip_xirr", "max_drawdown",
       "benchmark_excess_return", "rolling_beat_benchmark_pct", "downside_capture", "quartile_consistency"}

DISCLAIMER = (
    "This is a research and comparison tool, not investment advice and not a recommendation to buy or sell. "
    "Scores rank funds only against the other funds in the same run and are based on PAST data; high past "
    "returns do not guarantee future returns. A percentile or z-score is relative to the funds supplied, not an "
    "absolute measure of safety. Short investment horizons (1-3 years) carry substantial equity risk. "
    "Small-cap, sectoral and thematic funds can be concentrated and high-risk; compare within a category and "
    "check suitability, exit load, tax and expense ratio yourself.")


class RunLog:
    def __init__(self, echo=print):
        self.lines, self.echo = [], echo
        self.started = datetime.now()

    def add(self, text="", echo=True):
        self.lines.append(text)
        if echo and self.echo:
            self.echo(text)

    def warn(self, text):
        self.add(f"WARNING: {text}")

    def text(self):
        return "\n".join(self.lines) + "\n"

    def write(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.text())


def fmt(metric, v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v):
        return "n/a"
    if metric in ("benchmark_excess_return", "jensen_alpha"):
        return f"{v * 100:+.2f} pp"
    if metric in PCT:
        return f"{v * 100:.1f}%"
    if metric == "portfolio_quality":
        return f"{v:.0f}"
    return f"{v:.2f}"


def _cell(text):
    return str(text).replace("|", "/").replace("\n", " ")


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return out


def explain(row, weights, policy):
    """Rule-based explanation of one fund's score. Returns a list of sentences."""
    act = [m for m, w in weights.items() if w > 0]
    sc = {m: row.get(f"score_{m}") for m in act}
    have = {m: s for m, s in sc.items() if s is not None and not pd.isna(s)}
    out = []
    strong = sorted((m for m, s in have.items() if s >= 70), key=lambda m: -have[m] * weights[m])[:3]
    weak = sorted((m for m, s in have.items() if s <= 30), key=lambda m: have[m] * 1.0)[:3]
    if strong:
        out.append("Strengths: " + ", ".join(f"{LABELS[m].lower()} ({fmt(m, row.get(m))}, score {have[m]:.0f})" for m in strong) + ".")
    if weak:
        out.append("Weak spots: " + ", ".join(f"{LABELS[m].lower()} ({fmt(m, row.get(m))}, score {have[m]:.0f})" for m in weak) + ".")
    if not strong and not weak:
        out.append("Mid-table on every measured metric.")
    miss = [m for m in act if m not in have]
    if miss:
        how = "their weight was spread over the measured metrics" if policy == "renormalize_available" \
            else "they were scored as average"
        out.append("Not measured: " + ", ".join(LABELS[m].lower() for m in miss) + f" ({how}).")
    cat = str(row.get("scheme_category", "")).lower()
    dd = row.get("max_drawdown")
    risks = []
    if pd.notna(dd) and dd <= -0.35:
        risks.append(f"it fell {abs(dd) * 100:.0f}% peak to trough at its worst")
    beta = row.get("beta")
    if beta is not None and pd.notna(beta) and beta >= 1.2:
        risks.append(f"its beta is {beta:.2f}: it has moved about {beta:.1f}x the benchmark, up and down")
    if any(k in cat for k in ("small cap", "sectoral", "thematic")):
        risks.append("this category can be concentrated and volatile")
    if risks:
        out.append("Risk notes: " + "; ".join(risks) + ".")
    return out


def _ranking_rows(df, top_n):
    rows = []
    for _, r in df[df["status"] == "RANKED"].head(top_n).iterrows():
        rows.append([int(r["rank"]), r.get("scheme_name", ""), f"{r['final_score_0_100']:.1f}",
                     f"{r['composite_score']:.3f}", f"{r['score_coverage'] * 100:.0f}%", r.get("data_flags", "") or ""])
    return rows


def write_markdown(path, groups, cfg, run, exploratory=None, top_n=15, detail_n=5, sources=None, benchmarks=None,
                   input_note=None, extra_sections=None):
    """groups: [{name, ranked (DataFrame), excluded [(code, name, reasons)], as_of}]; cfg: config module.
    input_note: when the metrics came from a supplied CSV (rank_funds.py) rather than being computed from NAVs,
    a sentence describing that input; it replaces the NAV-based method lines. extra_sections: list of
    (heading, [lines]) appended before the closing notes."""
    LABELS["rolling_positive_pct"] = f"Rolling {cfg.ROLLING_WINDOW_YEARS:g}y windows positive"
    L = []
    L.append("# Mutual fund ranking")
    L.append("")
    L.append(f"Generated {run.started:%Y-%m-%d %H:%M}. Weights file `{cfg.WEIGHTS_FILE}` (version {cfg.WEIGHTS_VERSION}).")
    L.append("")
    L.append("> " + DISCLAIMER)
    L.append("")
    L.append("## Method")
    L.append("")
    L.append(f"- **Scoring method:** {cfg.SCORING_METHOD} (a 0-100 percentile-based `final score` is always shown too).")
    pol = ("a fund's score is the weighted average over the metrics it has (weights rescaled to 100%)"
           if cfg.MISSING_DATA_POLICY == "renormalize_available" else "a missing metric counts as an average score")
    L.append(f"- **Missing data:** `{cfg.MISSING_DATA_POLICY}` -- {pol}.")
    L.append(f"- **Coverage floor:** a fund needs {cfg.MIN_SCORE_COVERAGE * 100:.0f}% of the weight measured to be ranked; "
             f"otherwise it is listed as INSUFFICIENT_DATA.")
    L.append(f"- **Low-confidence flag:** a category with fewer than {cfg.MIN_GROUP_SIZE} ranked funds is marked LOW CONFIDENCE.")
    L.append("- **Ranked within category.** Funds in different categories are never ranked together except in the "
             "clearly labelled exploratory list.")
    if input_note:
        L.append(f"- **Input data:** {input_note}")
    else:
        L.append(f"- **Risk-free rate:** {cfg.RISK_FREE_RATE * 100:.1f}%; rolling window {cfg.ROLLING_WINDOW_YEARS:g} years (month-end); "
                 f"excess-return period {cfg.BENCHMARK_EXCESS_YEARS:g} years; SIP simulated over {cfg.SIP_YEARS:g} years.")
        dd_years = getattr(cfg, "DRAWDOWN_WINDOW_YEARS", None)
        dd_text = (f"the worst peak-to-trough fall in the last {dd_years:g} years (the same window for every fund)"
                   if dd_years else "the worst peak-to-trough fall in the fund's whole NAV history")
        L.append(f"- **Returns** are computed from Direct-Growth NAVs (mfapi.in / AMFI); drawdown is {dd_text}.")
        if any(cfg.SCORE_WEIGHTS.get(m, 0) > 0 for m in ("jensen_alpha", "beta")):
            L.append(f"- **Alpha / beta:** regression of monthly excess returns on the benchmark's over the last "
                     f"{cfg.ALPHA_BETA_YEARS:g} years (needs {cfg.ALPHA_BETA_MIN_MONTHS}+ months).")
    for b in benchmarks or []:
        L.append(f"- **Benchmark:** {b.strip()}")
    for s in sources or []:
        L.append(f"- **Data source:** {s}")
    L.append("")
    L.append("### Weights")
    L.append("")
    rows = [[LABELS[m], f"{w * 100:g}", DIRECTION[m]] for m, w in cfg.SCORE_WEIGHTS.items()]
    L += _table(["Metric", "Weight %", "Better when"], rows)
    L.append("")
    L.append("Expense ratio is deliberately not scored.")
    L.append("")

    for g in groups:
        df = g["ranked"]
        n_rank = int((df["status"] == "RANKED").sum()) if len(df) else 0
        L.append(f"## {g['name']}")
        L.append("")
        asof = g.get("as_of")
        L.append(f"Newest NAV date in this group: {asof.date() if asof is not None and not pd.isna(asof) else 'unknown'}. "
                 f"{n_rank} fund(s) ranked.")
        if len(df) and str(df['confidence'].iloc[0]).startswith("LOW"):
            L.append("")
            L.append(f"**LOW CONFIDENCE:** {df['confidence'].iloc[0]}")
        L.append("")
        if n_rank:
            L += _table(["Rank", "Fund", "Final score (0-100)", "Composite", "Weight measured", "Data flags"],
                        _ranking_rows(df, top_n))
            L.append("")
            note = []
            if n_rank > top_n:
                note.append(f"Showing the top {top_n} of {n_rank} ranked funds; shortlisted_funds.csv has all of them.")
            if cfg.SCORING_METHOD == "zscore":
                note.append("Rank follows the Composite column (z-scores). The 0-100 final score is percentile-based, "
                            "so two neighbouring funds can appear in a slightly different order; "
                            "set scoring_method = percentile in weights.ini to make rank follow the final score.")
            if note:
                L.append("_" + " ".join(note) + "_")
                L.append("")
        insuff = df[df["status"] == "INSUFFICIENT_DATA"] if len(df) else df
        if len(insuff):
            L.append("**Not ranked (INSUFFICIENT_DATA):** " + "; ".join(
                f"{r['scheme_name']} ({r['score_coverage'] * 100:.0f}% measured)" for _, r in insuff.iterrows()))
            L.append("")
        if g.get("excluded"):
            L.append("**Excluded before scoring:**")
            for code, name, why in g["excluded"]:
                L.append(f"- {name} ({code}): {', '.join(why)}")
            L.append("")
        for _, r in df[df["status"] == "RANKED"].head(detail_n).iterrows():
            L.append(f"### #{int(r['rank'])} {r['scheme_name']}")
            L.append("")
            cov = r["score_coverage"]
            trows = []
            for m, w in cfg.SCORE_WEIGHTS.items():
                if w <= 0:
                    continue
                s, pts = r.get(f"score_{m}"), r.get(f"contrib_{m}")
                eff = (w / cov) if (cfg.MISSING_DATA_POLICY == "renormalize_available" and cov) else w
                measured = s is not None and not pd.isna(s)
                trows.append([LABELS[m], fmt(m, r.get(m)), f"{s:.0f}" if measured else "n/a",
                              f"{w * 100:g}", f"{eff * 100:.1f}" if measured else "-",
                              f"{pts:.1f}" if measured and pts is not None and not pd.isna(pts) else "-"])
            L += _table(["Metric", "Value", "Score 0-100", "Weight %", "Effective weight %", "Points"], trows)
            L.append("")
            L.append(f"Final score {r['final_score_0_100']:.1f} (points add up to this); weight measured "
                     f"{cov * 100:.0f}%. Category: {r.get('scheme_category', '')}.")
            L.append("")
            for s in explain(r, cfg.SCORE_WEIGHTS, cfg.MISSING_DATA_POLICY):
                L.append(f"- {s}")
            if r.get("data_flags"):
                L.append(f"- Data flags: {r['data_flags']}")
            if r.get("pq_note"):
                L.append(f"- Portfolio quality: {r['pq_note']}")
            L.append("")

    if exploratory is not None and len(exploratory):
        L.append("## EXPLORATORY cross-category list")
        L.append("")
        L.append("**Exploratory only.** These funds have different mandates and risk profiles (a small-cap fund is not "
                 "comparable to a large-cap fund). Use the per-category rankings above for real comparisons; read the "
                 "category column here.")
        L.append("")
        rows = []
        for _, r in exploratory[exploratory["status"] == "RANKED"].head(top_n).iterrows():
            rows.append([int(r["rank"]), r.get("scheme_name", ""), r.get("scheme_category", ""),
                         f"{r['final_score_0_100']:.1f}", fmt("max_drawdown", r.get("max_drawdown")),
                         f"{r['volatility'] * 100:.0f}%" if pd.notna(r.get("volatility")) else "n/a"])
        L += _table(["Rank", "Fund", "Category", "Final score", "Max drawdown", "Volatility"], rows)
        L.append("")

    for heading, lines in extra_sections or []:
        L.append(f"## {heading}")
        L.append("")
        L += list(lines)
        L.append("")

    L.append("## Notes on missing data")
    L.append("")
    L.append("Nothing is estimated: a metric that cannot be computed (too little history, no benchmark, no holdings file) "
             "is left missing and handled by the missing-data policy above. Portfolio quality is missing for funds "
             "with no matching, recent AMC holdings file. See the run log for the full list of warnings.")
    L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
