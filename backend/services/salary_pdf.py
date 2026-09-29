from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INK = colors.HexColor("#243447")
ACCENT = colors.HexColor("#526579")
PALE = colors.HexColor("#F2F4F6")
RULE = colors.HexColor("#D9DEE4")
MUTED = colors.HexColor("#687582")


def _money(value):
    return f"INR {float(value or 0):,.2f}"


def _leave_units(value):
    value = float(value or 0)
    if value.is_integer():
        return str(int(value))
    return str(value)


def _month_label(month):
    try:
        from datetime import datetime
        return datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except (TypeError, ValueError):
        return month or ""


def _styles():
    styles = getSampleStyleSheet()
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
        fontSize=8, leading=9.5, textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name="PayrollCell", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=8, leading=10, textColor=INK,
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
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4) if is_register else A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Salary {'Register' if is_register else 'Statement'} - {month}",
        author="Operon Solutions HR Management System",
    )
    story = _report_header("Payroll Register" if is_register else "Salary Statement", month, styles)

    if not is_register:
        record = records[0]
        story.append(Paragraph(
            f"<b>Employee:</b> {escape(str(record.get('employee_name') or '-'))} &nbsp;&nbsp; "
            f"<b>ID:</b> {record.get('employee_id', '')} &nbsp;&nbsp; "
            f"<b>Role:</b> {escape(str(record.get('employee_role') or '-'))} &nbsp;&nbsp; "
            f"<b>Status:</b> {'Finalized' if record.get('locked') else 'Draft'}",
            styles["Normal"],
        ))
        story.append(Spacer(1, 5 * mm))
        rows = [
            ["Earnings and adjustments", "Details"],
            ["Assigned hourly rate" if record.get("salary_type") == "hourly" else "Assigned base salary", _money(record.get("base_salary"))],
            ["Gross salary for period", _money(record.get("gross_salary"))],
            ["Leave deduction", f"- {_money(record.get('salary_deduction'))}"],
            ["Salary after holidays", _money(record.get("salary_after_holidays"))],
            ["Overtime", f"{float(record.get('overtime_minutes') or 0) / 60:.2f} hours (informational)"],
            ["Overtime pay", _money(record.get("overtime_pay"))],
            ["Net salary", _money(record.get("total_salary"))],
        ]
        table = Table(rows, colWidths=[98 * mm, 70 * mm], hAlign="LEFT")
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
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.extend([table, Spacer(1, 6 * mm)])
        detail_rows = [
            ["Attendance summary", "Value", "Leave summary", "Value"],
            ["Scheduled work days", str(record.get("working_days", "-")),
             "Grace used / allowance", f"{_leave_units(record.get('grace_holidays_used'))} / {_leave_units(record.get('grace_holidays'))} days"],
            ["Worked days", str(int(record.get("actual_worked_days") or 0)),
             "Charged leave", f"{_leave_units(record.get('deducted_holidays'))} days"],
            ["Worked hours", f"{float(record.get('actual_worked_minutes') or 0) / 60:.2f}",
             "Salary type", str(record.get("salary_type") or "-").title()],
            ["Overtime", f"{float(record.get('overtime_minutes') or 0) / 60:.2f} hours", "", ""],
        ]
        detail = Table(detail_rows, colWidths=[43 * mm, 36 * mm, 43 * mm, 46 * mm])
        detail.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, RULE),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(detail)
    else:
        headers = [
            "Sr No", "ID", "Name", "Role", "Base Salary", "Worked Days",
            "Grace Used / Allowance", "Charged Leaves", "Overtime",
            "Leave Deduction", "Net Salary",
        ]
        data = [[Paragraph(escape(label), styles["PayrollHeader"]) for label in headers]]
        for serial, record in enumerate(records, start=1):
            data.append([
                str(serial),
                str(record.get("employee_id", "")),
                Paragraph(escape(str(record.get("employee_name") or "-")), styles["PayrollCell"]),
                Paragraph(escape(str(record.get("employee_role") or "-")), styles["PayrollCell"]),
                _money(record.get("base_salary")),
                str(int(record.get("actual_worked_days") or 0)),
                f"{_leave_units(record.get('grace_holidays_used'))} / {_leave_units(record.get('grace_holidays'))}",
                _leave_units(record.get("deducted_holidays")),
                f"{float(record.get('overtime_minutes') or 0) / 60:.1f} h",
                _money(record.get("salary_deduction")),
                _money(record.get("total_salary")),
            ])
        total_net = sum(float(record.get("total_salary") or 0) for record in records)
        data.append(["", "", "TOTAL", "", "", "", "", "", "", "", _money(total_net)])

        # Landscape A4 provides enough width to keep every field distinct and readable.
        widths = [12, 14, 39, 25, 31, 20, 30, 23, 20, 31, 32]
        table = Table(data, colWidths=[width * mm for width in widths], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, RULE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, PALE]),
            ("BACKGROUND", (0, -1), (-1, -1), PALE),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, -1), (-1, -1), INK),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 1), (1, -1), "CENTER"),
            ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        story.append(table)
        story.append(Spacer(1, 4 * mm))
        # story.append(Paragraph(
        #     "Any recorded work time counts as a worked day. Each scheduled day without recorded work is one absence; grace days are deducted before charged leave is shown. "
        #     "Grace leave is shown as used / allowance. "
        #     "Overtime is informational and does not affect net salary under current payroll rules. "
        #     f"Employees included: {len(records)}.",
        #     styles["PayrollSubtitle"],
        # ))

    doc.build(story)
    output.seek(0)
    return output
