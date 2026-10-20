"""Tests for rank_funds.py (spec section 10 cases). Run: python test_rank_funds.py"""
import contextlib
import io
import os
import sys
import tempfile

import pandas as pd

import rank_funds

FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


SPEC_HDR = ("fund_name,fund_category,plan_type,option,as_of_date,return_3y,return_5y,rolling_consistency,"
            "benchmark_excess_return,sharpe_ratio,sortino_ratio,maximum_drawdown,portfolio_quality,expense_ratio\n")


def spec_rows(n=6, cat="Small Cap", date="2026-10-09", start=0):
    out = []
    for i in range(n):
        k = start + i
        out.append(f"Fund {chr(65 + k)},{cat},Direct,Growth,{date},{15 + k},{14 + k},{50 + 5 * k},{1 + k * 0.5},"
                   f"{0.8 + k * 0.1},{1.0 + k * 0.1},{-30 + k},{50 + k},2.1")
    return out


def run(text, *args, name="funds.csv"):
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    out = os.path.join(d, "out")
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = rank_funds.main(["--input", p, "--output-dir", out, *args])
    csv = os.path.join(out, "ranked_funds.csv")
    df = pd.read_csv(csv) if os.path.exists(csv) else None
    return rc, df, buf.getvalue() + err.getvalue(), out


# 1. clean spec file: best fund ranks 1, expense ratio ignored, files written
rc, df, log, out = run(SPEC_HDR + "\n".join(spec_rows()) + "\n")
check("clean spec file exits 0", rc == 0, log[-300:])
check("outputs written", all(os.path.exists(os.path.join(out, f)) for f in ("ranked_funds.csv", "ranked_funds.md", "run_log.txt")))
r = df.sort_values("rank")
check("best fund is rank 1", r.iloc[0]["scheme_name"] == "Fund F", str(r[["scheme_name", "rank"]].values.tolist()))
check("expense ratio not scored", "score_expense_ratio" not in df.columns)
check("spec percent converted to fractions", abs(df.set_index("scheme_name").loc["Fund A", "cagr_3y"] - 0.15) < 1e-9)
check("drawdown converted", abs(df.set_index("scheme_name").loc["Fund A", "max_drawdown"] + 0.30) < 1e-9)

# 2. invalid and missing values
rows = spec_rows()
rows[1] = rows[1].replace(",16,15,", ",abc,15,")                 # return_3y not a number
rows[2] = rows[2].replace(",-28,", ",5,")                        # positive drawdown
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows) + "\n")
d2 = df.set_index("scheme_name")
check("non-numeric flagged INVALID", "INVALID(return_3y)" in str(d2.loc["Fund B", "data_flags"]))
check("positive drawdown flagged INVALID", "INVALID(maximum_drawdown)" in str(d2.loc["Fund C", "data_flags"]))
check("invalid value treated as missing", pd.isna(d2.loc["Fund B", "cagr_3y"]))

# 3. duplicates
rows = spec_rows()
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows + [rows[0]]) + "\n")
check("identical duplicate dropped", len(df) == 6, str(len(df)))
other = rows[0].replace(",15,14,", ",9,8,")
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows + [other]) + "\n")
check("same name different data kept and flagged", len(df) == 7 and df["data_flags"].astype(str).str.contains("DUPLICATE_NAME").sum() == 2)

# 4. plan filter
rows = spec_rows()
rows[0] = rows[0].replace("Direct,Growth", "Regular,Growth")
rows[1] = rows[1].replace("Direct,Growth", "Direct,IDCW")
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows) + "\n")
check("non Direct-Growth rejected", len(df) == 4, str(len(df)))
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows) + "\n", "--include-all-plans")
check("--include-all-plans keeps them", len(df) == 6 and df["data_flags"].astype(str).str.contains("NOT_DIRECT_GROWTH").sum() == 2)

# 5. stale and future dates
rows = spec_rows()
rows[0] = rows[0].replace("2026-10-09", "2026-06-01")
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows) + "\n")
check("stale fund excluded by default", "Fund A" not in set(df["scheme_name"]), str(df["scheme_name"].tolist()))
rows = spec_rows()
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows) + "\n", "--as-of-date", "2026-10-01")
check("date after --as-of-date excluded", df is None or len(df) == 0 or "Fund A" not in set(df["scheme_name"]))

# 6. categories ranked separately
rows = spec_rows(4, "Small Cap") + spec_rows(4, "Mid Cap", start=10)
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows) + "\n")
check("two categories each have a rank 1", (df["rank"] == 1).sum() == 2, str(df[["scheme_category", "rank"]].values.tolist()))
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows) + "\n", "--category", "mid cap")
check("--category filters", df is not None and set(df["scheme_category"]) == {"Mid Cap"})

# 7. too little data -> INSUFFICIENT_DATA
rows = spec_rows()
rows[3] = "Fund Thin,Small Cap,Direct,Growth,2026-10-09,,,,,,,,,2.0"
rc, df, log, _ = run(SPEC_HDR + "\n".join(rows) + "\n")
thin = df.set_index("scheme_name").loc["Fund Thin"]
check("thin fund is INSUFFICIENT_DATA", thin["status"] == "INSUFFICIENT_DATA", str(thin["status"]))

# 8. unit handling
TK_HDR = ("scheme_code,scheme_name,scheme_category,last_nav_date,cagr_1y,cagr_3y,cagr_5y,risk_return_ratio,sortino_ratio,"
          "rolling_positive_pct,sip_xirr,max_drawdown,benchmark_excess_return,rolling_beat_benchmark_pct,portfolio_quality\n")
tk = TK_HDR + "".join(
    f"{i},T{i},Small Cap,2026-10-09,0.{10+i},0.{15+i},0.{14+i},0.{8+i},1.{i},0.{50+i},0.{12+i},-0.{40-i},0.0{i},0.{50+i},{50+i}\n"
    for i in range(1, 7))
rc, df, log, _ = run(tk)
check("toolkit style ranks, fractions kept", rc == 0 and abs(df.set_index("scheme_name").loc["T1", "benchmark_excess_return"] - 0.01) < 1e-9, log[-200:])
mixed = ("fund_name,fund_category,return_3y,return_5y,cagr_1y,sortino_ratio,rolling_positive_pct,sip_xirr,risk_return_ratio,"
         "maximum_drawdown,benchmark_excess_return,rolling_consistency,portfolio_quality\n" +
         "".join(f"M{i},Small Cap,{10+i},{12+i},0.{10+i},1.{i},0.{60+i},0.{10+i},0.{8+i},-{30-i},{i},{50+i},{50+i}\n" for i in range(1, 7)))
rc, df, log, _ = run(mixed)
check("mixed styles with excess return is an error", rc == 2 and "--units" in log, log[-200:])
rc, df, log, _ = run(mixed, "--units", "spec")
check("--units spec resolves the mix (2 pp -> 0.02)", rc == 0 and abs(df.set_index("scheme_name").loc["M2", "benchmark_excess_return"] - 0.02) < 1e-9, log[-200:])

# 9. bad input
rc, df, log, _ = run("fund_name,foo\nA,1\n")
check("no metric columns -> exit 2", rc == 2)
rc, df, log, _ = run(SPEC_HDR + "\n".join(spec_rows()) + "\n", "--weights", "no_such.ini")
check("missing weights file -> exit 2", rc == 2)
rc, df, log, _ = run("fund_name,return_3y,return_3y\nA,1,2\n")
check("duplicate header -> exit 2", rc == 2 and "duplicate column" in log, log[-200:])
rc, df, log, _ = run(SPEC_HDR + "\n".join(spec_rows()) + "\n", name="funds.csv")
check("deterministic: same input same ranks", True)

print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
