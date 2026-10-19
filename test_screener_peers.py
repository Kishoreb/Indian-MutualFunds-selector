"""
Offline tests for the peer ranking inside mf_holdings_screener.py now that scoring can leave a
fund UNRANKED (too little data to reach the coverage floor in weights.ini). Before this was
handled, a single thin-data peer made rank_peers() fail on a missing rank.

    python test_screener_peers.py

Synthetic numbers only; nothing here says anything about real funds.
"""
import sys

import numpy as np

import config
import mf_holdings_screener as mfs

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"ok  {name}")


def full_fund(code, quality):
    """quality 0..1 moves every metric the same way, so the order is known in advance."""
    return {"scheme_code": str(code), "history_years": 7.0,
            "cagr_1y": 0.10 + 0.2 * quality, "cagr_3y": 0.10 + 0.15 * quality, "cagr_5y": 0.10 + 0.1 * quality,
            "risk_return_ratio": 0.5 + quality, "sortino_ratio": 0.8 + 1.5 * quality,
            "rolling_positive_pct": 0.6 + 0.4 * quality, "sip_xirr": 0.08 + 0.2 * quality,
            "max_drawdown": -0.45 + 0.2 * quality,
            "benchmark_excess_return": -0.03 + 0.08 * quality, "rolling_beat_benchmark_pct": 0.3 + 0.5 * quality}


def thin_fund(code):
    """3+ years of history but only two metrics measurable: 25% of the weight, under the 70% floor."""
    return {"scheme_code": str(code), "history_years": 3.5, "cagr_3y": 0.15, "max_drawdown": -0.30}


def run():
    check("default policy is renormalize with a 70% floor (weights.ini)",
          config.MISSING_DATA_POLICY == "renormalize_available" and abs(config.MIN_SCORE_COVERAGE - 0.7) < 1e-9)

    peers = [full_fund(100 + i, i / 11) for i in range(12)]          # 100 worst ... 111 best
    peers += [thin_fund(901), thin_fund(902)]
    young = full_fund(950, 0.5)
    young["history_years"] = 2.0                                      # under min_peer_history_years
    peers.append(young)

    out = mfs.rank_peers(peers)                                       # used to raise on the missing ranks
    check("thin-data funds get no peer entry", "901" not in out and "902" not in out)
    check("a fund with too little history is left out", "950" not in out)
    check("the 12 full funds are ranked", len(out) == 12 and all(v["size"] == 12 for v in out.values()))
    check("size counts only ranked funds; unranked is reported", all(v["unranked"] == 2 for v in out.values()))
    check("best fund is rank 1 / percentile 100", out["111"]["rank"] == 1 and out["111"]["percentile"] == 100.0)
    check("worst fund is rank 12 / percentile 0", out["100"]["rank"] == 12 and out["100"]["percentile"] == 0.0)
    check("ranks are 1..12 with no gaps", sorted(v["rank"] for v in out.values()) == list(range(1, 13)))
    check("percentiles fall as rank worsens", all(
        out[str(100 + i)]["percentile"] < out[str(101 + i)]["percentile"] for i in range(11)))
    check("peer medians come from the ranked funds only", abs(out["100"]["median_3y"] - np.median(
        [p["cagr_3y"] for p in peers[:12]])) < 1e-9)

    # nothing rankable at all -> empty, not an error
    check("only thin funds -> empty ranking", mfs.rank_peers([thin_fund(1), thin_fund(2)]) == {})
    check("no funds with enough history -> empty ranking", mfs.rank_peers([young]) == {})

    # the old behaviour (missing = average, nobody left out) is still available: 'average' + floor 0
    old = (config.MISSING_DATA_POLICY, config.MIN_SCORE_COVERAGE)
    try:
        config.MISSING_DATA_POLICY, config.MIN_SCORE_COVERAGE = "average", 0.0
        out_avg = mfs.rank_peers(peers)
        check("under the 'average' policy thin funds are ranked too", "901" in out_avg and out_avg["901"]["size"] == 14)
    finally:
        config.MISSING_DATA_POLICY, config.MIN_SCORE_COVERAGE = old

    # the verdict says why an unranked fund has no peer evidence, and still uses what it has
    facts = {"mapped": True, "zero_value": False, "history_years": 3.5, "nav_age_days": 1, "cagr_3y": 0.15,
             "cagr_5y": None, "max_drawdown": -0.3, "category_short": "Small Cap Fund", "peer": None,
             "peer_unranked": True, "benchmark_excess_return": 0.02, "rolling_beat_benchmark_pct": 0.7,
             "benchmark_name": "Nifty Smallcap 250 TRI"}
    d = mfs.decide(facts)
    check("unranked fund: note explains the missing peer rank",
          any("Not ranked against its peers" in n for n in d["notes"]))
    check("unranked fund: benchmark evidence still counts (Medium confidence)",
          d["confidence"] == "Medium" and d["verdict"] == mfs.V_CONTINUE)
    facts2 = dict(facts, peer_unranked=False)
    check("no note when the fund simply has no peer group",
          not any("Not ranked against its peers" in n for n in mfs.decide(facts2)["notes"]))

    # same input -> same output
    check("ranking is deterministic", mfs.rank_peers(peers) == mfs.rank_peers(list(peers)))


if __name__ == "__main__":
    run()
    print(f"\nAll {passed} checks passed")
    sys.exit(0)
