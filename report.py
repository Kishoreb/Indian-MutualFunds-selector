"""
report.py
---------
Formats the ranked shortlist as a polished Excel workbook: bold header,
frozen header row, auto-sized columns, percentage/number formatting, and
conditional color scale on the composite score so the best funds pop
visually. Optional extra sheets list the excluded funds (and why) and the
run settings (category, benchmark, window, ...). Falls back gracefully
(prints a warning) if openpyxl isn't installed rather than crashing the
whole pipeline.
"""

from __future__ import annotations

import pandas as pd

from logutil import get_logger

log = get_logger(__name__)

PERCENT_COLS = {
    "cagr_1y", "cagr_3y", "cagr_5y", "volatility", "max_drawdown",
    "downside_deviation", "rolling_avg", "rolling_min", "rolling_std",
    "rolling_positive_pct", "rolling_above_hurdle_pct", "sip_xirr",
    "alpha", "tracking_error", "excess_cagr", "rolling_beat_pct",
    "up_capture", "down_capture", "max_daily_move",
    "rolling_p10", "rolling_dispersion", "aum_growth_12m",
}
RATIO_COLS = {"risk_return_ratio", "sortino_ratio", "composite_score", "beta", "information_ratio",
              "sharpe_stability", "beta_drift", "down_capture_drift", "aum_vs_median", "aum_strain",
              "forward_tilt", "combined_score", "expense_ratio", "manager_tenure_years"}


def _style_header(ws, ncols, header_fill, header_font, Alignment):
    for col_idx in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"


def export_to_excel(df: pd.DataFrame, path: str, excluded: list | None = None,
                    notes: dict | None = None) -> bool:
    """Writes df to an .xlsx file with readable formatting. Returns True on
    success, False if openpyxl isn't available (caller should fall back to
    CSV-only in that case).

    excluded: optional list of {scheme_code, scheme_name, reasons} dicts for an
              "Excluded" sheet.
    notes:    optional {setting: value} dict for a "Run settings" sheet."""
    try:
        import openpyxl  # noqa: F401
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.formatting.rule import ColorScaleRule
        from openpyxl.utils import get_column_letter
    except ImportError:
        log.warning("  (openpyxl not installed -- skipping Excel export. `pip install openpyxl` to enable it.)")
        return False

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Shortlist")
        ws = writer.sheets["Shortlist"]
        _style_header(ws, len(df.columns), header_fill, header_font, Alignment)

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

        if excluded:
            ex_df = pd.DataFrame(excluded)
            ex_df.to_excel(writer, index=False, sheet_name="Excluded")
            ws2 = writer.sheets["Excluded"]
            _style_header(ws2, len(ex_df.columns), header_fill, header_font, Alignment)
            for col_idx, col_name in enumerate(ex_df.columns, start=1):
                max_len = max([len(str(col_name))] + [len(str(v)) for v in ex_df[col_name].astype(str)])
                ws2.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 2, 12), 90)

        if notes:
            nt = pd.DataFrame({"setting": list(notes.keys()), "value": [str(v) for v in notes.values()]})
            nt.to_excel(writer, index=False, sheet_name="Run settings")
            ws3 = writer.sheets["Run settings"]
            _style_header(ws3, 2, header_fill, header_font, Alignment)
            ws3.column_dimensions["A"].width = 36
            ws3.column_dimensions["B"].width = 70

    return True
