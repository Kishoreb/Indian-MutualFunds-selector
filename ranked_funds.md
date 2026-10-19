# Mutual fund ranking

Generated 2026-10-19 07:49. Weights file `D:\Finance\Shares\Tools\AI\MFselector-new\weights.ini` (version 2).

> This is a research and comparison tool, not investment advice and not a recommendation to buy or sell. Scores rank funds only against the other funds in the same run and are based on PAST data; high past returns do not guarantee future returns. A percentile or z-score is relative to the funds supplied, not an absolute measure of safety. Short investment horizons (1-3 years) carry substantial equity risk. Small-cap, sectoral and thematic funds can be concentrated and high-risk; compare within a category and check suitability, exit load, tax and expense ratio yourself.

## Method

- **Scoring method:** zscore (a 0-100 percentile-based `final score` is always shown too).
- **Missing data:** `renormalize_available` -- a fund's score is the weighted average over the metrics it has (weights rescaled to 100%).
- **Coverage floor:** a fund needs 70% of the weight measured to be ranked; otherwise it is listed as INSUFFICIENT_DATA.
- **Low-confidence flag:** a category with fewer than 8 ranked funds is marked LOW CONFIDENCE.
- **Ranked within category.** Funds in different categories are never ranked together except in the clearly labelled exploratory list.
- **Risk-free rate:** 6.5%; rolling window 3 years (month-end); excess-return period 3 years; SIP simulated over 3 years.
- **Returns** are computed from Direct-Growth NAVs (mfapi.in / AMFI); drawdown is the worst peak-to-trough fall in the available NAV history.
- **Benchmark:** elss: Nifty 500 TRI via index-fund proxy [Motilal Oswal Nifty 500 Index Fund - Direct Plan - Growth] (7.1y history)
- **Benchmark:** large & mid cap: Nifty LargeMidcap 250 TRI via index-fund proxy [Edelweiss NIFTY Large Midcap 250 Index Fund - Direct Plan - Growth] (4.9y history)
- **Benchmark:** mid cap: Nifty Midcap 150 TRI via index-fund proxy [Motilal Oswal Nifty Midcap 150 Index Fund - Direct Plan - Growth] (7.1y history)
- **Data source:** NAV history from mfapi.in (mirrors AMFI); newest NAV dates are shown per category
- **Data source:** holdings files under data/holdings/ where present

### Weights

| Metric | Weight % | Better when |
|---|---|---|
| 1-year return (CAGR) | 5 | higher |
| 3-year return (CAGR) | 15 | higher |
| 5-year return (CAGR) | 15 | higher |
| Sharpe-style ratio | 5 | higher |
| Sortino ratio | 10 | higher |
| Rolling 3y windows positive | 5 | higher |
| SIP XIRR | 5 | higher |
| Maximum drawdown | 10 | smaller fall |
| 3y excess return vs benchmark | 10 | higher |
| Rolling windows beating benchmark | 10 | higher |
| Portfolio quality (0-100) | 10 | higher |
| Downside capture | 0 | lower |
| Time in top half of peers | 0 | higher |

Expense ratio is deliberately not scored.

## mid cap

Newest NAV date in this group: 2026-10-16. 27 fund(s) ranked.

| Rank | Fund | Final score (0-100) | Composite | Weight measured | Data flags |
|---|---|---|---|---|---|
| 1 | Motilal Oswal Large and Midcap Fund - Direct Plan - Growth | 85.0 | 1.405 | 90% |  |
| 2 | Invesco India Large & Mid Cap Fund - Direct Plan - Growth | 86.8 | 1.301 | 90% |  |
| 3 | Invesco India Mid Cap Fund - Direct Plan - Growth | 82.4 | 1.272 | 90% | CATEGORY_MISMATCH |
| 4 | Edelweiss Mid Cap Fund - Direct Plan - Growth | 72.6 | 0.883 | 90% | CATEGORY_MISMATCH |
| 5 | ITI Mid Cap Fund - Direct Plan - Growth Option | 73.7 | 0.686 | 90% | CATEGORY_MISMATCH |
| 6 | ICICI Prudential Mid Cap Fund - Direct Plan - Growth | 63.9 | 0.577 | 90% | CATEGORY_MISMATCH |
| 7 | Bandhan Large & Mid Cap Fund - Direct Plan - Growth | 68.3 | 0.555 | 90% |  |
| 8 | Nippon India Growth Mid Cap Fund - Direct Plan - Growth Option | 69.2 | 0.467 | 90% | CATEGORY_MISMATCH |
| 9 | HSBC Large & Mid Cap Fund - Direct Plan - Growth | 64.7 | 0.414 | 90% |  |
| 10 | HDFC Mid Cap Fund - Direct Plan - Growth Option | 56.8 | 0.314 | 90% | CATEGORY_MISMATCH |
| 11 | Mahindra Manulife Mid Cap Fund - Direct Plan - Growth | 63.5 | 0.260 | 90% | CATEGORY_MISMATCH |
| 12 | Quant Large & Mid Cap Fund - Direct Plan - Growth Option | 47.3 | -0.049 | 90% |  |
| 13 | Kotak Mid Cap Fund - Direct Plan - Growth | 46.9 | -0.146 | 90% | CATEGORY_MISMATCH |
| 14 | Axis Large & Mid Cap Fund - Direct Plan - Growth Option | 50.2 | -0.163 | 90% |  |
| 15 | Edelweiss Large & Mid Cap Fund - Direct Plan - Growth | 45.5 | -0.270 | 90% |  |

**Excluded before scoring:**
- BNP Paribas Mid Cap Fund - Direct Plan - Growth Option (120002): STALE_NAV(1678d)
- DHFL Pramerica Mid Cap Fund - Series 1 - Direct Plan - Growth (138950): STALE_NAV(3224d)
- DWS Mid Cap Fund - Series 1 - Direct Plan - Growth (133144): STALE_NAV(3880d)
- HSBC Mid Cap Fund - Direct - Growth (149154): STALE_NAV(1421d)
- IDBI Midcap Fund Growth Direct (140461): STALE_NAV(1177d)
- ING Midcap Fund - Direct Plan - Growth Option (119909): STALE_NAV(4390d)
- L&T Large and Midcap Fund-Direct Plan-Growth (119397): STALE_NAV(1422d)
- L&T Mid Cap Fund-Direct Plan-Growth (119807): STALE_NAV(1422d)
- Principal Midcap Fund - Direct Plan- Growth (147778): STALE_NAV(1751d)
- Abakkus Large & Mid Cap Fund - Direct Plan - Growth (154477): insufficient history, 3y CAGR too low, 5y CAGR too low, volatility too high
- BANDHAN MID CAP FUND - Direct Plan - Growth (150404): insufficient history, 5y CAGR too low
- BANK OF INDIA MID CAP FUND - Direct Plan - Growth (153728): insufficient history, 3y CAGR too low, 5y CAGR too low
- Bajaj Finserv Large & Mid Cap Fund - Direct Plan - Growth (152408): insufficient history, 3y CAGR too low, 5y CAGR too low
- Baroda BNP Paribas Mid Cap Fund - Direct Plan - Growth Option (150212): insufficient history, 5y CAGR too low
- Canara Robeco Mid Cap Fund - Direct Plan - Growth Option (150817): insufficient history, 5y CAGR too low
- HSBC Midcap Fund - Direct Plan - Growth (151036): insufficient history, 5y CAGR too low
- Helios Large & Mid Cap Fund - Direct Plan - Growth (152941): insufficient history, 3y CAGR too low, 5y CAGR too low
- Helios Mid Cap Fund - Direct Plan - Growth (153326): insufficient history, 3y CAGR too low, 5y CAGR too low
- ITI Large & Mid Cap Fund - Direct Plan - Growth Option (152821): insufficient history, 3y CAGR too low, 5y CAGR too low
- JM Large & Mid Cap Fund - Direct Plan - Growth Option (153629): insufficient history, 3y CAGR too low, 5y CAGR too low
- JM Mid Cap Fund - Direct Plan - Growth Option (150815): insufficient history, 5y CAGR too low
- LIC MF Mid Cap Fund - Direct Plan - Growth (152002): insufficient history, 5y CAGR too low
- PGIM India Large and Midcap Fund - Direct Plan - Direct Growth (152382): insufficient history, 3y CAGR too low, 5y CAGR too low
- Aditya Birla Sun Life Large & Mid Cap Fund - Direct Plan - GROWTH (119436): 3y CAGR too low, 5y CAGR too low
- Franklin India Large & Mid Cap Fund - Direct Plan - Growth (118510): 3y CAGR too low, 5y CAGR too low
- Navi Large & Midcap Fund - Direct Plan - Growth (135677): 3y CAGR too low, 5y CAGR too low
- BANK OF INDIA MID CAP TAX FUND SERIES 1 - Direct Plan - Growth (141950): 5y CAGR too low
- BANK OF INDIA MID CAP TAX FUND Series 2 - Direct Plan - Growth (144315): 5y CAGR too low
- Canara Robeco Large and Mid Cap Fund - Direct Plan - GROWTH OPTION (118278): 5y CAGR too low
- DSP Midcap Fund - Direct Plan - Growth (119071): 5y CAGR too low
- LIC MF Large & Mid Cap Fund - Direct Plan - Growth (133710): 5y CAGR too low
- Mirae Asset Large & Midcap Fund - Direct Plan - Growth (118834): 5y CAGR too low
- PGIM India Midcap Fund - Direct Plan - Direct Growth (125307): 5y CAGR too low

### #1 Motilal Oswal Large and Midcap Fund - Direct Plan - Growth

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 2.6% | 81 | 5 | 5.6 | 4.5 |
| 3-year return (CAGR) | 20.1% | 92 | 15 | 16.7 | 15.4 |
| 5-year return (CAGR) | 17.5% | 100 | 15 | 16.7 | 16.7 |
| Sharpe-style ratio | 0.63 | 85 | 5 | 5.6 | 4.7 |
| Sortino ratio | 1.07 | 85 | 10 | 11.1 | 9.4 |
| Rolling 3y windows positive | 100.0% | 81 | 5 | 5.6 | 4.5 |
| SIP XIRR | 12.4% | 100 | 5 | 5.6 | 5.6 |
| Maximum drawdown | -37.4% | 38 | 10 | 11.1 | 4.3 |
| 3y excess return vs benchmark | +9.79 pp | 96 | 10 | 11.1 | 10.7 |
| Rolling windows beating benchmark | 100.0% | 85 | 10 | 11.1 | 9.4 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 85.0 (points add up to this); weight measured 90%. Category: Equity Scheme - Large & Mid Cap Fund.

- Strengths: 5-year return (cagr) (17.5%, score 100), 3-year return (cagr) (20.1%, score 92), 3y excess return vs benchmark (+9.79 pp, score 96).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Risk notes: it fell 37% peak to trough at its worst.
- Portfolio quality: no holdings file matched this scheme

### #2 Invesco India Large & Mid Cap Fund - Direct Plan - Growth

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 0.7% | 42 | 5 | 5.6 | 2.4 |
| 3-year return (CAGR) | 20.2% | 96 | 15 | 16.7 | 16.0 |
| 5-year return (CAGR) | 15.0% | 81 | 15 | 16.7 | 13.5 |
| Sharpe-style ratio | 0.73 | 100 | 5 | 5.6 | 5.6 |
| Sortino ratio | 1.21 | 100 | 10 | 11.1 | 11.1 |
| Rolling 3y windows positive | 100.0% | 81 | 5 | 5.6 | 4.5 |
| SIP XIRR | 11.3% | 92 | 5 | 5.6 | 5.1 |
| Maximum drawdown | -35.3% | 73 | 10 | 11.1 | 8.1 |
| 3y excess return vs benchmark | +9.86 pp | 100 | 10 | 11.1 | 11.1 |
| Rolling windows beating benchmark | 100.0% | 85 | 10 | 11.1 | 9.4 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 86.8 (points add up to this); weight measured 90%. Category: Equity Schemes - Large & Mid Cap Fund.

- Strengths: 3-year return (cagr) (20.2%, score 96), 5-year return (cagr) (15.0%, score 81), sortino ratio (1.21, score 100).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Risk notes: it fell 35% peak to trough at its worst.
- Portfolio quality: no holdings file matched this scheme

### #3 Invesco India Mid Cap Fund - Direct Plan - Growth

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 0.9% | 46 | 5 | 5.6 | 2.6 |
| 3-year return (CAGR) | 21.0% | 100 | 15 | 16.7 | 16.7 |
| 5-year return (CAGR) | 16.9% | 96 | 15 | 16.7 | 16.0 |
| Sharpe-style ratio | 0.72 | 96 | 5 | 5.6 | 5.3 |
| Sortino ratio | 1.21 | 96 | 10 | 11.1 | 10.7 |
| Rolling 3y windows positive | 99.2% | 56 | 5 | 5.6 | 3.1 |
| SIP XIRR | 12.3% | 96 | 5 | 5.6 | 5.3 |
| Maximum drawdown | -34.1% | 81 | 10 | 11.1 | 9.0 |
| 3y excess return vs benchmark | +8.00 pp | 92 | 10 | 11.1 | 10.3 |
| Rolling windows beating benchmark | 54.0% | 31 | 10 | 11.1 | 3.4 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 82.4 (points add up to this); weight measured 90%. Category: Equity Schemes - Mid Cap Fund.

- Strengths: 3-year return (cagr) (21.0%, score 100), 5-year return (cagr) (16.9%, score 96), sortino ratio (1.21, score 96).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Data flags: CATEGORY_MISMATCH
- Portfolio quality: no holdings file matched this scheme

### #4 Edelweiss Mid Cap Fund - Direct Plan - Growth

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 1.5% | 54 | 5 | 5.6 | 3.0 |
| 3-year return (CAGR) | 18.8% | 88 | 15 | 16.7 | 14.7 |
| 5-year return (CAGR) | 15.8% | 88 | 15 | 16.7 | 14.7 |
| Sharpe-style ratio | 0.68 | 92 | 5 | 5.6 | 5.1 |
| Sortino ratio | 1.12 | 88 | 10 | 11.1 | 9.8 |
| Rolling 3y windows positive | 96.4% | 31 | 5 | 5.6 | 1.7 |
| SIP XIRR | 8.7% | 81 | 5 | 5.6 | 4.5 |
| Maximum drawdown | -39.2% | 27 | 10 | 11.1 | 3.0 |
| 3y excess return vs benchmark | +5.79 pp | 85 | 10 | 11.1 | 9.4 |
| Rolling windows beating benchmark | 96.0% | 60 | 10 | 11.1 | 6.6 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 72.6 (points add up to this); weight measured 90%. Category: Equity Scheme - Mid Cap Fund.

- Strengths: 3-year return (cagr) (18.8%, score 88), 5-year return (cagr) (15.8%, score 88), sortino ratio (1.12, score 88).
- Weak spots: maximum drawdown (-39.2%, score 27).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Risk notes: it fell 39% peak to trough at its worst.
- Data flags: CATEGORY_MISMATCH
- Portfolio quality: no holdings file matched this scheme

### #5 ITI Mid Cap Fund - Direct Plan - Growth Option

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 3.0% | 85 | 5 | 5.6 | 4.7 |
| 3-year return (CAGR) | 17.6% | 81 | 15 | 16.7 | 13.5 |
| 5-year return (CAGR) | 14.1% | 65 | 15 | 16.7 | 10.9 |
| Sharpe-style ratio | 0.57 | 77 | 5 | 5.6 | 4.3 |
| Sortino ratio | 0.94 | 77 | 10 | 11.1 | 8.5 |
| Rolling 3y windows positive | 100.0% | 81 | 5 | 5.6 | 4.5 |
| SIP XIRR | 7.2% | 62 | 5 | 5.6 | 3.4 |
| Maximum drawdown | -22.7% | 96 | 10 | 11.1 | 10.7 |
| 3y excess return vs benchmark | +4.53 pp | 73 | 10 | 11.1 | 8.1 |
| Rolling windows beating benchmark | 87.5% | 46 | 10 | 11.1 | 5.1 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 73.7 (points add up to this); weight measured 90%. Category: Equity Scheme - Mid Cap Fund.

- Strengths: 3-year return (cagr) (17.6%, score 81), maximum drawdown (-22.7%, score 96), sortino ratio (0.94, score 77).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Data flags: CATEGORY_MISMATCH
- Portfolio quality: no holdings file matched this scheme

## Notes on missing data

Nothing is estimated: a metric that cannot be computed (too little history, no benchmark, no holdings file) is left missing and handled by the missing-data policy above. Portfolio quality is missing for funds with no matching, recent AMC holdings file. See the run log for the full list of warnings.
