# Indian Mutual Fund Ranking — Scoring Specification

## 1. Purpose

Implement a Python program that calculates transparent, reproducible scores for Indian mutual funds using configurable parameter weights stored in an external file.

The program is intended to compare mutual funds, primarily **within the same category** (for example, small-cap funds against small-cap funds). It must not treat historical performance as a guarantee of future returns.

The scoring system below is a starting specification. It is not an official industry standard or investment recommendation.

## 2. Configuration-driven weights

All parameter weights must be loaded from an external configuration file, not hard-coded in the Python program. JSON or YAML is acceptable; JSON is recommended if a dependency-free configuration format is desired.

Suggested `scoring_weights.json`:

```json
{
  "version": 1,
  "weights_percent": {
    "return_3y": 25,
    "return_5y": 15,
    "rolling_consistency": 15,
    "benchmark_excess_return": 10,
    "risk_adjusted_return": 10,
    "maximum_drawdown": 10,
    "expense_ratio": 5,
    "portfolio_quality": 10
  },
  "missing_data_policy": "renormalize_available",
  "minimum_coverage_percent": 70,
  "comparison_group": "category"
}
```

### Configuration requirements

- Read the configuration at runtime from a file path supplied through a command-line option, with a documented default path.
- Validate that weights are numeric, non-negative, and sum to 100 (allow a small floating-point tolerance).
- Reject invalid configuration with a clear error message.
- Do not silently replace invalid or missing configuration with hard-coded weights.
- Keep the weights and scoring transformations configurable or clearly separated from the scoring engine.
- Include a sample configuration file in the project.
- Record the configuration version and actual weights in the output for auditability.

## 3. Parameters and default weights

| Parameter key | Parameter | Weight | Direction |
|---|---|---:|---|
| `return_3y` | 3-year annualised return (CAGR) | 25% | Higher is better |
| `return_5y` | 5-year annualised return (CAGR) | 15% | Higher is better |
| `rolling_consistency` | Consistency of rolling returns versus benchmark | 15% | Higher is better |
| `benchmark_excess_return` | Fund return minus benchmark return over a matched period | 10% | Higher is better |
| `risk_adjusted_return` | Risk-adjusted return, using Sharpe and/or Sortino | 10% | Higher is better |
| `maximum_drawdown` | Largest peak-to-trough portfolio decline | 10% | Smaller absolute loss is better |
| `expense_ratio` | Annual expense ratio (%) | 5% | Lower is better |
| `portfolio_quality` | Diversification, liquidity, concentration and portfolio-quality assessment | 10% | Higher is better |
| **Total** | | **100%** | |

The program must not assume that a higher raw number is always better. It must apply the appropriate direction when converting each metric to a comparable score.

## 4. Input data specification

The program should accept a CSV file, with one row per fund and an explicit as-of date. Prefer a separate data-ingestion module so that the scoring engine can be tested using local CSV files without internet access.

Suggested fields:

| Field | Meaning | Unit / format |
|---|---|---|
| `fund_name` | Scheme name | Text |
| `fund_category` | Comparable category, such as small-cap or mid-cap | Text |
| `plan_type` | Direct or regular | Text |
| `option` | Growth, IDCW, etc. | Text |
| `as_of_date` | Date to which the data applies | ISO date `YYYY-MM-DD` |
| `return_3y` | 3-year annualised fund return | Percent, e.g. `18.5` |
| `return_5y` | 5-year annualised fund return | Percent, e.g. `16.2` |
| `rolling_consistency` | Percentage of matched rolling periods the fund beat its benchmark | 0–100 |
| `benchmark_excess_return` | Fund return minus benchmark return for the selected matched period | Percentage points |
| `sharpe_ratio` | Annualised Sharpe ratio | Numeric |
| `sortino_ratio` | Annualised Sortino ratio | Numeric |
| `maximum_drawdown` | Maximum drawdown over the defined measurement window | Negative percentage, e.g. `-35.0` |
| `expense_ratio` | Annual expense ratio | Percent, e.g. `0.75` |
| `portfolio_quality` | Documented portfolio-quality score | 0–100 |
| `benchmark_name` | Benchmark index name | Text |
| `data_source` | Source of data | Text |
| `data_quality_notes` | Caveats, gaps or methodology notes | Text |

The implementation may accept additional fields, but it must document them. Define whether returns are based on NAV total returns and ensure fund and benchmark periods are aligned. Compare Direct Growth plans with Direct Growth plans for the main ranking unless the user explicitly requests otherwise.

### Metric definitions must be consistent

- **3-year and 5-year return:** CAGR calculated over matching as-of dates.
- **Rolling consistency:** percentage of matched rolling periods in which the fund outperformed its appropriate benchmark. Specify the rolling window, frequency (for example, monthly), total-return basis, and sample size.
- **Benchmark excess return:** fund return minus benchmark total return for the same dates and return convention. Avoid comparing a fund's total return with a price-only index.
- **Sharpe ratio:** annualised excess return over a documented risk-free rate divided by annualised standard deviation, with a documented return frequency.
- **Sortino ratio:** excess return over a documented minimum acceptable return divided by annualised downside deviation. Document the exact convention.
- **Maximum drawdown:** most negative peak-to-trough percentage change in the NAV/total-return series over a specified lookback period.
- **Expense ratio:** use the reported expense ratio applicable to the chosen plan and as-of date.
- **Portfolio quality:** a documented 0–100 score based on objective, disclosed subcriteria. Do not fabricate this value if holdings data are unavailable.

The chosen lookback periods and conventions must be recorded in the output. Do not mix different dates or methodologies silently.

## 5. Convert metrics to comparable scores

Different metrics use different units. Convert each metric into a score from 0 to 100 **within the relevant comparison group**, using a documented, reproducible method.

Recommended default: percentile ranking among eligible funds in the same category and as-of-date cohort.

- For metrics where higher is better, a higher percentile receives a higher score.
- For metrics where lower is better (`expense_ratio` and drawdown magnitude), reverse the percentile direction.
- For `maximum_drawdown`, use the absolute magnitude for ranking: for example, a 20% drawdown is preferable to a 40% drawdown, all else equal.
- Use a deterministic tie-handling method (for example, average ranks).
- Document how percentile scores are mapped to 0–100.
- Avoid min-max scaling without safeguards, because a single extreme observation can distort scores.
- Require a configurable minimum number of eligible funds in a comparison group; if there are too few funds, flag the ranking as low confidence.

For `risk_adjusted_return`, the default can be the average of the percentile scores for Sharpe and Sortino, provided both are available. If only one is available, apply the missing-data policy and flag the missing metric. Alternatively, make the Sharpe/Sortino blend configurable.

Percentile ranking is relative to the funds in the supplied dataset. It does not mean a fund is absolutely safe or likely to produce positive returns.

## 6. Calculate the weighted score

For each fund:

1. Validate and normalise the input values and dates.
2. Assign a 0–100 score for each metric.
3. Multiply each available metric score by its configured weight.
4. Apply the missing-data policy.
5. Produce a final score from 0 to 100, plus a ranking within the appropriate comparison group.

If all metrics are available:

`final_score = sum(metric_score * weight_percent) / 100`

If `missing_data_policy` is `renormalize_available`, calculate:

`final_score = sum(metric_score * weight_percent for available metrics) / sum(weight_percent for available metrics)`

This renormalisation is permitted only when the available metric weights meet `minimum_coverage_percent` of the full 100% weight. Otherwise, mark the fund as `INSUFFICIENT_DATA` and do not assign it a normal rank.

The program must report both:
- **Weight coverage:** sum of configured weights for metrics actually scored.
- **Final score:** the weighted average under the configured missing-data policy.

Do not treat an actual value of zero as missing. Distinguish missing, invalid, and zero values.

## 7. Risk and data-quality safeguards

- Rank funds within the same category by default; do not rank debt, large-cap, mid-cap, small-cap, sectoral and other equity categories together as though they had identical risk profiles.
- If an overall cross-category list is requested, label it exploratory and display category and risk information prominently.
- Exclude funds with insufficient history for a metric from that metric, not by silently substituting zero.
- Apply a configurable minimum coverage requirement before ranking a fund.
- Flag stale, missing, inconsistent, or non-comparable data.
- Do not infer missing Sharpe ratios, drawdowns, benchmark returns, holdings, or portfolio-quality scores.
- Use a suitable total-return benchmark for each fund category and record the mapping.
- Treat sectoral/thematic and small-cap funds as potentially concentrated/high-risk; the score is not a substitute for suitability analysis.
- Include a note that short investment horizons (such as 1–3 years) carry substantial equity risk and that high past returns do not guarantee future returns.
- The scoring model should be used for research and comparison, not as a guarantee or personalised financial advice.

## 8. Outputs

Produce at least:

1. `ranked_funds.csv` — one row per fund with final score, rank, category, each raw input, each metric score, weight coverage, data date, and data-quality flags.
2. `ranked_funds.md` — human-readable ranking tables by category, scoring methodology, configuration version, data sources, as-of dates, missing-data notes, and risk disclaimer.
3. A run log summarising input file, configuration file, eligible fund count, rejected rows, and warnings.

The Markdown report should make it easy to understand **why** each fund scored as it did. Include each metric's raw value, 0–100 score, configured weight, and weighted contribution.

Do not claim the data are current unless the data sources and as-of dates support that claim.

## 9. Suggested command-line interface

Example:

```bash
python rank_funds.py   --input funds.csv   --weights scoring_weights.json   --output-dir output   --as-of-date 2026-10-09
```

The program should:
- Validate the input schema and configuration.
- Allow the user to choose a category or rank all categories separately.
- Produce deterministic output for identical inputs and configuration.
- Exit with a non-zero status on fatal input/configuration errors.
- Print a concise summary and point to the generated output files.

## 10. Testing requirements

Include automated tests for at least:

- Valid configuration and weights summing to 100.
- Invalid, negative, non-numeric, and non-100% weights.
- Higher-is-better and lower-is-better percentile scoring.
- Maximum drawdown direction (a smaller loss should score higher).
- Correct Sharpe/Sortino combination.
- Missing-data handling and minimum coverage.
- Zero as a valid metric value.
- Duplicate fund names and duplicate rows.
- Mixed categories being ranked separately.
- Stale and inconsistent dates.
- Ties and deterministic ranking.
- CSV output schema and Markdown report generation.
- Reproducibility with the same input and configuration.

## 11. Important implementation note

This specification defines the **scoring engine**, not a guaranteed source of live financial data. Implement data ingestion separately from scoring. Any web/API/scraping integration must identify its source, respect access rules, preserve the as-of date, and handle unavailable data explicitly. Never fabricate values to complete a ranking.
