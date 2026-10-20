# Mutual fund ranking

Generated 2026-10-19 08:48. Weights file `D:\Finance\Shares\Tools\AI\MFselector-new\weights.ini` (version 2).

> This is a research and comparison tool, not investment advice and not a recommendation to buy or sell. Scores rank funds only against the other funds in the same run and are based on PAST data; high past returns do not guarantee future returns. A percentile or z-score is relative to the funds supplied, not an absolute measure of safety. Short investment horizons (1-3 years) carry substantial equity risk. Small-cap, sectoral and thematic funds can be concentrated and high-risk; compare within a category and check suitability, exit load, tax and expense ratio yourself.

## Method

- **Scoring method:** percentile (a 0-100 percentile-based `final score` is always shown too).
- **Missing data:** `renormalize_available` -- a fund's score is the weighted average over the metrics it has (weights rescaled to 100%).
- **Coverage floor:** a fund needs 70% of the weight measured to be ranked; otherwise it is listed as INSUFFICIENT_DATA.
- **Low-confidence flag:** a category with fewer than 8 ranked funds is marked LOW CONFIDENCE.
- **Ranked within category.** Funds in different categories are never ranked together except in the clearly labelled exploratory list.
- **Risk-free rate:** 6.5%; rolling window 3 years (month-end); excess-return period 3 years; SIP simulated over 3 years.
- **Returns** are computed from Direct-Growth NAVs (mfapi.in / AMFI); drawdown is the worst peak-to-trough fall in the available NAV history.
- **Benchmark:** small cap: Nifty Smallcap 250 TRI via index-fund proxy [ICICI Prudential Nifty Smallcap 250 Index Fund - Direct Plan - Growth] (5.0y history)
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

## small cap

Newest NAV date in this group: 2026-10-16. 15 fund(s) ranked.

| Rank | Fund | Final score (0-100) | Composite | Weight measured | Data flags |
|---|---|---|---|---|---|
| 1 | BANK OF INDIA SMALL CAP FUND - Direct Plan - Growth | 88.3 | 88.294 | 90% |  |
| 2 | ITI Small Cap Fund - Direct Plan - Growth Option | 85.9 | 85.913 | 90% |  |
| 3 | Invesco India Small Cap Fund - Direct Plan - Growth | 83.9 | 83.929 | 90% |  |
| 4 | Quant Small Cap Fund - Direct Plan - Growth Option | 65.9 | 65.873 | 90% |  |
| 5 | Union Small Cap Fund - Direct Plan - Growth Option | 56.3 | 56.349 | 90% |  |
| 6 | Nippon India Small Cap Fund - Direct Plan - Growth Option | 54.5 | 54.464 | 100% |  |
| 7 | DSP Small Cap Fund - Direct Plan - Growth | 54.3 | 54.286 | 100% |  |
| 8 | Edelweiss Small Cap Fund - Direct Plan - Growth | 49.8 | 49.802 | 90% |  |
| 9 | PGIM India Small Cap Fund - Direct Plan - Direct Growth | 49.0 | 49.008 | 90% |  |
| 10 | Sundaram Small Cap Fund - Direct Plan - GROWTH | 43.7 | 43.651 | 90% | DUPLICATE_NAME |
| 11 | UTI Small Cap Fund - Direct Plan - Growth | 34.7 | 34.722 | 90% |  |
| 12 | Canara Robeco Small Cap Fund - Direct Plan - GROWTH OPTION | 25.6 | 25.595 | 90% |  |
| 13 | Tata Small Cap Fund - Direct Plan - Growth Option | 23.6 | 23.611 | 90% |  |
| 14 | Franklin India Small Cap Fund - Direct Plan - Growth | 20.2 | 20.238 | 90% |  |
| 15 | ICICI Prudential Small Cap Fund - Direct Plan - Growth | 13.3 | 13.294 | 90% |  |

**Excluded before scoring:**
- JPMorgan India Mid and Small Cap Fund - Direct Plan - Growth Option (119869): STALE_NAV(3613d)
- HSBC Small Cap Equity Fund - Growth Direct (120069): STALE_NAV(1421d)
- HSBC - Small Cap Fund - Growth Direct (120077): STALE_NAV(4557d)
- Sundaram Select Small Cap Series II Direct Growth (132985): STALE_NAV(2947d)
- Sundaram Select Small Cap Series III Direct Growth (134297): STALE_NAV(2390d)
- Sundaram Select Small Cap Series IV - Direct Growth (134373): STALE_NAV(2373d)
- IDBI Small Cap Fund - Growth Direct (141475): STALE_NAV(1177d)
- Sundaram Select Small Cap Series V Direct Plan - Growth (141499): STALE_NAV(1941d)
- Sundaram Select Small Cap Series VI Direct Plan - Growth (141561): STALE_NAV(1915d)
- Sundaram Emerging Small Cap Series I Direct Plan - Growth (142533): STALE_NAV(1317d)
- Sundaram Emerging Small Cap Series II Direct Plan - Growth (143010): STALE_NAV(1285d)
- Sundaram Emerging Small Cap Series III Direct Plan - Growth (143226): STALE_NAV(1255d)
- Sundaram Emerging Small Cap Series IV Direct Plan - Growth (143506): STALE_NAV(1222d)
- Sundaram Emerging Small Cap Series V Direct Plan - Growth (144437): STALE_NAV(1159d)
- Sundaram Emerging Small Cap Series VI Direct Plan - Growth (144728): STALE_NAV(1135d)
- Sundaram Emerging Small Cap VII Direct Plan - Growth (144988): STALE_NAV(1113d)
- Principal Small Cap Fund - Direct Plan - Growth Option (147131): STALE_NAV(1751d)
- Mahindra Manulife Small Cap Fund - Direct Plan - Growth (150915): insufficient history, 5y CAGR too low
- LIC MF Small Cap Fund - Direct Plan - Growth (152004): insufficient history, 5y CAGR too low
- QUANTUM SMALL CAP FUND - Direct Plan - Growth Option (152107): insufficient history, 3y CAGR too low, 5y CAGR too low
- Baroda BNP Paribas Small Cap Fund - Direct Plan - Growth Option (152128): insufficient history, 3y CAGR too low, 5y CAGR too low
- Motilal Oswal Small Cap Fund - Direct Plan - Growth (152237): insufficient history, 3y CAGR too low, 5y CAGR too low
- JM Small Cap Fund - Direct Plan - Growth Option (152614): insufficient history, 3y CAGR too low, 5y CAGR too low
- TRUSTMF SMALL CAP FUND - Direct Plan - Growth (152939): insufficient history, 3y CAGR too low, 5y CAGR too low
- Mirae Asset Small Cap Fund - Direct Plan - Growth (153196): insufficient history, 3y CAGR too low, 5y CAGR too low
- Bajaj Finserv Small Cap Fund - Direct Plan - Growth (153612): insufficient history, 3y CAGR too low, 5y CAGR too low
- Samco Small Cap Fund - Direct Plan - Growth (153868): insufficient history, 3y CAGR too low, 5y CAGR too low
- Helios Small Cap Fund - Direct Plan - Growth (153912): insufficient history, 3y CAGR too low, 5y CAGR too low
- Groww Small Cap Fund - Direct Plan - Growth (154063): insufficient history, 3y CAGR too low, 5y CAGR too low
- Abakkus Small Cap Fund - Direct Plan - Growth (154215): insufficient history, 3y CAGR too low, 5y CAGR too low
- The Wealth Company Small Cap Fund - Direct Plan - Growth (154269): insufficient history, 3y CAGR too low, 5y CAGR too low
- Sundaram Small Cap Fund - Direct Plan - GROWTH (119588): 3y CAGR too low, 5y CAGR too low
- HDFC Small Cap Fund - Direct Plan - Growth Option (130503): 3y CAGR too low

### #1 BANK OF INDIA SMALL CAP FUND - Direct Plan - Growth

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 27.1% | 100 | 5 | 5.6 | 5.6 |
| 3-year return (CAGR) | 20.2% | 86 | 15 | 16.7 | 14.3 |
| 5-year return (CAGR) | 18.3% | 100 | 15 | 16.7 | 16.7 |
| Sharpe-style ratio | 0.62 | 86 | 5 | 5.6 | 4.8 |
| Sortino ratio | 1.16 | 93 | 10 | 11.1 | 10.3 |
| Rolling 3y windows positive | 100.0% | 75 | 5 | 5.6 | 4.2 |
| SIP XIRR | 19.7% | 100 | 5 | 5.6 | 5.6 |
| Maximum drawdown | -32.4% | 86 | 10 | 11.1 | 9.5 |
| 3y excess return vs benchmark | +8.23 pp | 86 | 10 | 11.1 | 9.5 |
| Rolling windows beating benchmark | 75.0% | 71 | 10 | 11.1 | 7.9 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 88.3 (points add up to this); weight measured 90%. Category: Equity Scheme - Small Cap Fund.

- Strengths: 5-year return (cagr) (18.3%, score 100), 3-year return (cagr) (20.2%, score 86), sortino ratio (1.16, score 93).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Risk notes: this category can be concentrated and volatile.
- Portfolio quality: no holdings file matched this scheme

### #2 ITI Small Cap Fund - Direct Plan - Growth Option

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 16.1% | 79 | 5 | 5.6 | 4.4 |
| 3-year return (CAGR) | 21.6% | 100 | 15 | 16.7 | 16.7 |
| 5-year return (CAGR) | 16.7% | 71 | 15 | 16.7 | 11.9 |
| Sharpe-style ratio | 0.75 | 100 | 5 | 5.6 | 5.6 |
| Sortino ratio | 1.38 | 100 | 10 | 11.1 | 11.1 |
| Rolling 3y windows positive | 100.0% | 75 | 5 | 5.6 | 4.2 |
| SIP XIRR | 15.5% | 93 | 5 | 5.6 | 5.2 |
| Maximum drawdown | -39.9% | 50 | 10 | 11.1 | 5.6 |
| 3y excess return vs benchmark | +9.67 pp | 100 | 10 | 11.1 | 11.1 |
| Rolling windows beating benchmark | 100.0% | 93 | 10 | 11.1 | 10.3 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 85.9 (points add up to this); weight measured 90%. Category: Equity Scheme - Small Cap Fund.

- Strengths: 3-year return (cagr) (21.6%, score 100), 5-year return (cagr) (16.7%, score 71), sortino ratio (1.38, score 100).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Risk notes: it fell 40% peak to trough at its worst; this category can be concentrated and volatile.
- Portfolio quality: no holdings file matched this scheme

### #3 Invesco India Small Cap Fund - Direct Plan - Growth

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 9.0% | 57 | 5 | 5.6 | 3.2 |
| 3-year return (CAGR) | 20.3% | 93 | 15 | 16.7 | 15.5 |
| 5-year return (CAGR) | 17.6% | 93 | 15 | 16.7 | 15.5 |
| Sharpe-style ratio | 0.69 | 93 | 5 | 5.6 | 5.2 |
| Sortino ratio | 1.16 | 86 | 10 | 11.1 | 9.5 |
| Rolling 3y windows positive | 100.0% | 75 | 5 | 5.6 | 4.2 |
| SIP XIRR | 13.5% | 71 | 5 | 5.6 | 4.0 |
| Maximum drawdown | -37.7% | 57 | 10 | 11.1 | 6.3 |
| 3y excess return vs benchmark | +8.29 pp | 93 | 10 | 11.1 | 10.3 |
| Rolling windows beating benchmark | 100.0% | 93 | 10 | 11.1 | 10.3 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 83.9 (points add up to this); weight measured 90%. Category: Equity Schemes - Small Cap Fund.

- Strengths: 3-year return (cagr) (20.3%, score 93), 5-year return (cagr) (17.6%, score 93), 3y excess return vs benchmark (+8.29 pp, score 93).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Risk notes: it fell 38% peak to trough at its worst; this category can be concentrated and volatile.
- Portfolio quality: no holdings file matched this scheme

### #4 Quant Small Cap Fund - Direct Plan - Growth Option

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 11.1% | 71 | 5 | 5.6 | 4.0 |
| 3-year return (CAGR) | 16.5% | 79 | 15 | 16.7 | 13.1 |
| 5-year return (CAGR) | 17.2% | 86 | 15 | 16.7 | 14.3 |
| Sharpe-style ratio | 0.50 | 79 | 5 | 5.6 | 4.4 |
| Sortino ratio | 0.95 | 79 | 10 | 11.1 | 8.7 |
| Rolling 3y windows positive | 90.0% | 7 | 5 | 5.6 | 0.4 |
| SIP XIRR | 10.4% | 50 | 5 | 5.6 | 2.8 |
| Maximum drawdown | -51.6% | 7 | 10 | 11.1 | 0.8 |
| 3y excess return vs benchmark | +4.51 pp | 79 | 10 | 11.1 | 8.7 |
| Rolling windows beating benchmark | 91.7% | 79 | 10 | 11.1 | 8.7 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 65.9 (points add up to this); weight measured 90%. Category: Equity Scheme - Small Cap Fund.

- Strengths: 5-year return (cagr) (17.2%, score 86), 3-year return (cagr) (16.5%, score 79), sortino ratio (0.95, score 79).
- Weak spots: rolling 3y windows positive (90.0%, score 7), maximum drawdown (-51.6%, score 7).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Risk notes: it fell 52% peak to trough at its worst; this category can be concentrated and volatile.
- Portfolio quality: no holdings file matched this scheme

### #5 Union Small Cap Fund - Direct Plan - Growth Option

| Metric | Value | Score 0-100 | Weight % | Effective weight % | Points |
|---|---|---|---|---|---|
| 1-year return (CAGR) | 17.9% | 93 | 5 | 5.6 | 5.2 |
| 3-year return (CAGR) | 15.1% | 64 | 15 | 16.7 | 10.7 |
| 5-year return (CAGR) | 15.5% | 57 | 15 | 16.7 | 9.5 |
| Sharpe-style ratio | 0.44 | 57 | 5 | 5.6 | 3.2 |
| Sortino ratio | 0.72 | 50 | 10 | 11.1 | 5.6 |
| Rolling 3y windows positive | 93.8% | 29 | 5 | 5.6 | 1.6 |
| SIP XIRR | 15.1% | 86 | 5 | 5.6 | 4.8 |
| Maximum drawdown | -44.7% | 43 | 10 | 11.1 | 4.8 |
| 3y excess return vs benchmark | +3.10 pp | 64 | 10 | 11.1 | 7.1 |
| Rolling windows beating benchmark | 41.7% | 36 | 10 | 11.1 | 4.0 |
| Portfolio quality (0-100) | n/a | n/a | 10 | - | - |

Final score 56.3 (points add up to this); weight measured 90%. Category: Equity Scheme - Small Cap Fund.

- Strengths: 1-year return (cagr) (17.9%, score 93), sip xirr (15.1%, score 86).
- Weak spots: rolling 3y windows positive (93.8%, score 29).
- Not measured: portfolio quality (0-100) (their weight was spread over the measured metrics).
- Risk notes: it fell 45% peak to trough at its worst; this category can be concentrated and volatile.
- Portfolio quality: no holdings file matched this scheme

## Notes on missing data

Nothing is estimated: a metric that cannot be computed (too little history, no benchmark, no holdings file) is left missing and handled by the missing-data policy above. Portfolio quality is missing for funds with no matching, recent AMC holdings file. See the run log for the full list of warnings.
