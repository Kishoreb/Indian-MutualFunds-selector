"""
report.py
---------
Formats the ranked shortlist as a polished Excel workbook: bold header,
frozen header row, auto-sized columns, percentage/number formatting, and
conditional color scale on the composite score so the best funds pop
visually. Falls back gracefully (prints a warning) if openpyxl isn't
installed rather than crashing the whole pipeline.
"""

import pandas as pd

PERCENT_COLS = {
    "cagr_1y", "cagr_3y", "cagr_5y", "volatility", "max_drawdown",
    "downside_deviation", "rolling_avg", "rolling_min", "rolling_std",
    "rolling_positive_pct", "sip_xirr",
    "benchmark_cagr", "benchmark_excess_return", "rolling_beat_benchmark_pct",
    "pq_coverage",
}
# portfolio_quality is on a 0-100 scale; the pq_* inputs are already in percent units.
RATIO_COLS = {"risk_return_ratio", "sortino_ratio", "composite_score", "portfolio_quality",
              "pq_top10_pct", "pq_top_sector_pct", "pq_largemid_pct", "pq_cash_pct"}


def export_to_excel(df: pd.DataFrame, path: str) -> bool:
    """Writes df to an .xlsx file with readable formatting. Returns True on
    success, False if openpyxl isn't available (caller should fall back to
    CSV-only in that case)."""
    try:
        import openpyxl  # noqa: F401
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.formatting.rule import ColorScaleRule
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("  (openpyxl not installed -- skipping Excel export. `pip install openpyxl` to enable it.)")
        return False

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Shortlist")
        ws = writer.sheets["Shortlist"]

        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        for col_idx, col_name in enumerate(df.columns, start=1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        ws.freeze_panes = "A2"

        for col_idx, col_name in enumerate(df.columns, start=1):
            letter = get_column_letter(col_idx)
            max_len = max(
                [len(str(col_name))] + [len(str(v)) for v in df[col_name].astype(str).tolist()]
            )
            ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 32)

            if col_name in PERCENT_COLS:
                for row_idx in range(2, len(df) + 2):
                    ws.cell(row=row_idx, column=col_idx).number_format = "0.00%"
            elif col_name in RATIO_COLS:
                for row_idx in range(2, len(df) + 2):
                    ws.cell(row=row_idx, column=col_idx).number_format = "0.00"

        if "composite_score" in df.columns:
            score_col_idx = list(df.columns).index("composite_score") + 1
            letter = get_column_letter(score_col_idx)
            rng = f"{letter}2:{letter}{len(df) + 1}"
            rule = ColorScaleRule(
                start_type="min", start_color="F8696B",
                mid_type="percentile", mid_value=50, mid_color="FFEB84",
                end_type="max", end_color="63BE7B",
            )
            ws.conditional_formatting.add(rng, rule)

    return True
