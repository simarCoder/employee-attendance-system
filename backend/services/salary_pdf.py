from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# ==============================================================================
# PDF SIZING & SPACING CONFIGURATION
# Adjust widths, paddings, fonts, or gaps here without touching ReportLab logic.
# ==============================================================================
PDF_CONFIG = {
    # Page Margins (in millimeters)
    "page_margins_mm": {
        "left": 7,
        "right": 7,
        "top": 10,
        "bottom": 10,
    },

    # Color Palette
    "colors": {
        "primary_ink": "#243447",     # Dark navy for headers and bold text
        "accent": "#526579",          # Subdued slate blue
        "pale_row": "#F2F4F6",        # Alternating row background
        "border_rule": "#D9DEE4",     # Grid lines
        "muted_text": "#687582",      # Secondary labels
    },

    # 1. Individual Salary Statement Table (Portrait A4)
    "statement": {
        # Earnings Table (colWidths in mm: [Description, Amount])
        "earnings_col_widths_mm": [98, 70],
        "earnings_cell_padding_y": 8,       # Top & bottom cell padding (points)
        "earnings_cell_padding_x": 6,       # Left & right cell padding (points)
        "earnings_font_size": 9,

        # Attendance Detail Grid (colWidths in mm for 4 columns)
        "attendance_col_widths_mm": [43, 36, 43, 46],
        "attendance_cell_padding_y": 6,     # Top & bottom cell padding (points)
        "attendance_cell_padding_x": 6,     # Left & right cell padding (points)
        "attendance_font_size": 8,

        # Vertical spacing between tables (mm)
        "gap_after_header_mm": 3,
        "gap_between_tables_mm": 5,
    },

    # 2. Payroll Register Table (Landscape A4: Total width = 277 mm)
    "register": {
        # Column widths in millimeters (Sum of all 14 columns = 277 mm)
        "col_widths_mm": {
            "sr_no": 8,                # Thin Sr No
            "employee_id": 9,          # Thin ID
            "name": 32,                # Employee Name
            "role": 23,                # Designation / Role
            "base_salary": 24,         # Assigned Base Salary
            "full_days": 13,           # Full Days count
            "half_days": 13,           # Half Days count
            "worked_days": 16,         # Total Worked Days
            "grace_holidays": 23,      # Grace Holidays
            "charged_leaves": 18,      # Charged Leaves
            "overtime": 15,            # Overtime hours
            "leave_deduction": 22,     # Leave Deduction
            "bonus": 22,               # Attendance Bonus
            "net_salary": 29,          # Final Net Salary
        },

        # Cell paddings (points)
        "cell_padding_y": 5,           # Top & bottom cell padding
        "cell_padding_x": 3,           # Left & right cell padding

        # Font sizes (points)
        "header_font_size": 7,
        "cell_font_size": 8,

        # Vertical spacing after table (mm)
        "gap_after_table_mm": 3,
    },
}

INK = colors.HexColor(PDF_CONFIG["colors"]["primary_ink"])
ACCENT = colors.HexColor(PDF_CONFIG["colors"]["accent"])
PALE = colors.HexColor(PDF_CONFIG["colors"]["pale_row"])
RULE = colors.HexColor(PDF_CONFIG["colors"]["border_rule"])
MUTED = colors.HexColor(PDF_CONFIG["colors"]["muted_text"])


def _money(value):
    return f"₹ {float(value or 0):,.2f}"


def _leave_units(value):
    value = float(value or 0)
    if value.is_integer():
        return str(int(value))
    return str(value)


def _full_days(record):
    if record.get("full_days") is not None:
        return int(record.get("full_days") or 0)
    worked = float(record.get("actual_worked_days") or 0)
    return int(worked)


def _half_days(record):
    if record.get("half_days") is not None:
        return int(record.get("half_days") or 0)
    worked = float(record.get("actual_worked_days") or 0)
    return 1 if not worked.is_integer() else 0


def _month_label(month):
    try:
        from datetime import datetime
        return datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except (TypeError, ValueError):
        return month or ""


def _styles():
    styles = getSampleStyleSheet()
    reg_cfg = PDF_CONFIG["register"]
    styles.add(ParagraphStyle(
        name="PayrollBrand", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8.5, leading=11, textColor=ACCENT, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="PayrollTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=INK, alignment=TA_CENTER,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="PayrollSubtitle", parent=styles["Normal"], fontSize=9,
        textColor=MUTED, alignment=TA_CENTER, leading=13,
    ))
    styles.add(ParagraphStyle(
        name="PayrollHeader", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=reg_cfg["header_font_size"], leading=reg_cfg["header_font_size"] + 2, textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name="PayrollCell", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=reg_cfg["cell_font_size"], leading=reg_cfg["cell_font_size"] + 2, textColor=INK,
    ))
    return styles


def _report_header(title, month, styles):
    return [
        Paragraph("OPERON SOLUTIONS  |  HR MANAGEMENT SYSTEM", styles["PayrollBrand"]),
        Spacer(1, 3 * mm),
        Paragraph(title, styles["PayrollTitle"]),
        Paragraph(_month_label(month), styles["PayrollSubtitle"]),
        Spacer(1, 8 * mm),
    ]


def build_salary_pdf(records, month, employee=None):
    """Build a printable individual salary statement or payroll register."""
    output = BytesIO()
    is_register = employee is None
    styles = _styles()
    margins = PDF_CONFIG["page_margins_mm"]
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4) if is_register else A4,
        rightMargin=margins["right"] * mm,
        leftMargin=margins["left"] * mm,
        topMargin=margins["top"] * mm,
        bottomMargin=margins["bottom"] * mm,
        title=f"Salary {'Register' if is_register else 'Statement'} - {month}",
        author="Operon Solutions HR Management System",
    )
    story = _report_header("Payroll Register" if is_register else "Salary Statement", month, styles)

    if not is_register:
        cfg = PDF_CONFIG["statement"]
        record = records[0]
        story.append(Paragraph(
            f"<b>Employee:</b> {escape(str(record.get('employee_name') or '-'))} &nbsp;&nbsp; "
            f"<b>ID:</b> {record.get('employee_id', '')} &nbsp;&nbsp; "
            f"<b>Role:</b> {escape(str(record.get('employee_role') or '-'))} &nbsp;&nbsp; "
            f"<b>Status:</b> {'Finalized' if record.get('locked') else 'Draft'}",
            styles["Normal"],
        ))
        story.append(Spacer(1, cfg["gap_after_header_mm"] * mm))
        rows = [
            ["Earnings and adjustments", "Details"],
            ["Assigned hourly rate" if record.get("salary_type") == "hourly" else "Assigned base salary", _money(record.get("base_salary"))],
            ["Gross salary for period", _money(record.get("gross_salary"))],
            ["Leave deduction", f"- {_money(record.get('salary_deduction'))}"],
            ["Salary after holidays", _money(record.get("salary_after_holidays"))],
            ["Overtime", f"{float(record.get('overtime_minutes') or 0) / 60:.2f} hours (informational)"],
            ["Overtime pay", _money(record.get("overtime_pay"))],
            ["Attendance bonus", f"+ {_money(record.get('bonus_amount') or 0)}"],
            ["Net salary", _money(record.get("total_salary"))],
        ]
        earnings_widths = [w * mm for w in cfg["earnings_col_widths_mm"]]
        table = Table(rows, colWidths=earnings_widths, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, RULE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, -1), (-1, -1), INK),
            ("TOPPADDING", (0, 0), (-1, -1), cfg["earnings_cell_padding_y"]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), cfg["earnings_cell_padding_y"]),
            ("LEFTPADDING", (0, 0), (-1, -1), cfg["earnings_cell_padding_x"]),
            ("RIGHTPADDING", (0, 0), (-1, -1), cfg["earnings_cell_padding_x"]),
        ]))
        story.extend([table, Spacer(1, cfg["gap_between_tables_mm"] * mm)])

        detail_rows = [
            ["Attendance summary", "Value", "Leave summary", "Value"],
            ["Scheduled work days", str(record.get("working_days", "-")),
             "Grace Holidays", f"{_leave_units(record.get('grace_holidays_used'))} / {_leave_units(record.get('grace_holidays'))} days"],
            ["Full days / Half days", f"{_full_days(record)} Full / {_half_days(record)} Half",
             "Absent days", f"{_leave_units(record.get('absence_days'))} days"],
            ["Total worked days", f"{_leave_units(record.get('actual_worked_days'))} days",
             "Charged leave", f"{_leave_units(record.get('deducted_holidays'))} days"],
            ["Worked hours", f"{float(record.get('actual_worked_minutes') or 0) / 60:.2f}",
             "Salary type", str(record.get("salary_type") or "-").title()],
            ["Overtime", f"{float(record.get('overtime_minutes') or 0) / 60:.2f} hours", "", ""],
        ]
        att_widths = [w * mm for w in cfg["attendance_col_widths_mm"]]
        detail = Table(detail_rows, colWidths=att_widths)
        detail.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, RULE),
            ("FONTSIZE", (0, 0), (-1, -1), cfg["attendance_font_size"]),
            ("TOPPADDING", (0, 0), (-1, -1), cfg["attendance_cell_padding_y"]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), cfg["attendance_cell_padding_y"]),
            ("LEFTPADDING", (0, 0), (-1, -1), cfg["attendance_cell_padding_x"]),
            ("RIGHTPADDING", (0, 0), (-1, -1), cfg["attendance_cell_padding_x"]),
        ]))
        story.append(detail)
    else:
        reg_cfg = PDF_CONFIG["register"]
        headers = [
            "Sr No", "ID", "Name", "Role", "Base Salary", "Full Days", "Half Days",
            "Worked Days", "Grace Holidays", "Charged Leaves", "Overtime",
            "Leave Deduction", "Bonus", "Net Salary",
        ]
        data = [[Paragraph(escape(label), styles["PayrollHeader"]) for label in headers]]
        for serial, record in enumerate(records, start=1):
            bonus_val = float(record.get("bonus_amount") or 0)
            data.append([
                str(serial),
                str(record.get("employee_id", "")),
                Paragraph(escape(str(record.get("employee_name") or "-")), styles["PayrollCell"]),
                Paragraph(escape(str(record.get("employee_role") or "-")), styles["PayrollCell"]),
                _money(record.get("base_salary")),
                str(_full_days(record)),
                str(_half_days(record)),
                _leave_units(record.get("actual_worked_days")),
                f"{_leave_units(record.get('grace_holidays_used'))} / {_leave_units(record.get('grace_holidays'))}",
                _leave_units(record.get("deducted_holidays")),
                f"{float(record.get('overtime_minutes') or 0) / 60:.1f} h",
                _money(record.get("salary_deduction")),
                f"+ {_money(bonus_val)}" if bonus_val > 0 else _money(0),
                _money(record.get("total_salary")),
            ])
        total_bonus = sum(float(record.get("bonus_amount") or 0) for record in records)
        total_net = sum(float(record.get("total_salary") or 0) for record in records)
        data.append(["", "", "TOTAL", "", "", "", "", "", "", "", "", "", _money(total_bonus), _money(total_net)])

        w_dict = reg_cfg["col_widths_mm"]
        widths = [
            w_dict.get("sr_no", 8),
            w_dict.get("employee_id", 9),
            w_dict.get("name", 32),
            w_dict.get("role", 20),
            w_dict.get("base_salary", 24),
            w_dict.get("full_days", 13),
            w_dict.get("half_days", 13),
            w_dict.get("worked_days", 16),
            w_dict.get("grace_holidays", 23),
            w_dict.get("charged_leaves", 18),
            w_dict.get("overtime", 15),
            w_dict.get("leave_deduction", 25),
            w_dict.get("bonus", 22),
            w_dict.get("net_salary", 29),
        ]
        table = Table(data, colWidths=[width * mm for width in widths], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, RULE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, PALE]),
            ("BACKGROUND", (0, -1), (-1, -1), PALE),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, -1), (-1, -1), INK),
            ("FONTSIZE", (0, 0), (-1, -1), reg_cfg["cell_font_size"]),
            ("ALIGN", (0, 1), (1, -1), "CENTER"),
            ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), reg_cfg["cell_padding_x"]),
            ("RIGHTPADDING", (0, 0), (-1, -1), reg_cfg["cell_padding_x"]),
            ("TOPPADDING", (0, 0), (-1, -1), reg_cfg["cell_padding_y"]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), reg_cfg["cell_padding_y"]),
        ]))
        story.append(table)
        story.append(Spacer(1, reg_cfg["gap_after_table_mm"] * mm))

    doc.build(story)
    output.seek(0)
    return output
