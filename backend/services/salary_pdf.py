from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#2674B8")
PALE_BLUE = colors.HexColor("#EAF2F9")
MUTED = colors.HexColor("#66788A")


def _money(value):
    return f"INR {float(value or 0):,.2f}"


def _month_label(month):
    try:
        from datetime import datetime
        return datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except (TypeError, ValueError):
        return month or ""


def build_salary_pdf(records, month, employee=None):
    """Build a printable individual salary statement or payroll register."""
    output = BytesIO()
    is_register = employee is None
    pagesize = landscape(A4) if is_register else A4
    doc = SimpleDocTemplate(
        output,
        pagesize=pagesize,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=13 * mm,
        bottomMargin=13 * mm,
        title=f"Salary {'Register' if is_register else 'Statement'} - {month}",
        author="Operon Solutions HR Management System",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="Brand", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=BLUE, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=19, leading=23, textColor=NAVY, alignment=TA_CENTER,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Subtitle", parent=styles["Normal"], fontSize=9,
        textColor=MUTED, alignment=TA_CENTER, leading=13,
    ))
    styles.add(ParagraphStyle(
        name="RegisterHeader", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=6.5, leading=7.5, textColor=colors.white,
    ))

    story = [
        Paragraph("OPERON SOLUTIONS  |  HR MANAGEMENT SYSTEM", styles["Brand"]),
        Spacer(1, 3 * mm),
        Paragraph("Payroll Register" if is_register else "Salary Statement", styles["ReportTitle"]),
        Paragraph(_month_label(month), styles["Subtitle"]),
        Spacer(1, 8 * mm),
    ]

    if not is_register:
        record = records[0]
        employee_name = escape(str(record.get("employee_name") or ""))
        story.append(Paragraph(
            f"<b>Employee:</b> {employee_name} &nbsp;&nbsp; "
            f"<b>ID:</b> #{record.get('employee_id', '')} &nbsp;&nbsp; "
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
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6E0E9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_BLUE]),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, -1), (-1, -1), NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.extend([table, Spacer(1, 6 * mm)])
        detail_rows = [
            ["Attendance summary", "Value", "Leave summary", "Value"],
            ["Scheduled work days", str(record.get("working_days", "-")),
             "Grace leave allowance", f"{float(record.get('grace_holidays') or 0):.2f} days"],
            ["Worked days (equivalent)", f"{float(record.get('actual_worked_minutes') or 0) / max(1, float(record.get('daily_hours') or 8) * 60):.2f}",
             "Grace leave used", f"{float(record.get('grace_holidays_used') or 0):.2f} days"],
            ["Worked hours", f"{float(record.get('actual_worked_minutes') or 0) / 60:.2f}",
             "Chargeable leave", f"{float(record.get('deducted_holidays') or 0):.2f} days"],
            ["Overtime", f"{float(record.get('overtime_minutes') or 0) / 60:.2f} hours",
             "Salary type", str(record.get("salary_type") or "-").title()],
        ]
        detail = Table(detail_rows, colWidths=[43 * mm, 36 * mm, 43 * mm, 46 * mm])
        detail.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6E0E9")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(detail)
    else:
        headers = ["ID", "Employee", "Role", "Assigned salary / rate", "Worked days*", "Worked hours", "Grace allowance / used", "Charged leave", "OT hours", "OT pay", "Gross for period", "Leave deduction", "After holidays", "Net salary"]
        data = [[Paragraph(escape(header), styles["RegisterHeader"]) for header in headers]]
        for row in records:
            daily_minutes = max(1.0, float(row.get("daily_hours") or 8) * 60)
            data.append([
                f"#{row.get('employee_id', '')}",
                Paragraph(escape(str(row.get("employee_name") or "-")), styles["BodyText"]),
                escape(str(row.get("employee_role") or "-")),
                _money(row.get("base_salary")),
                f"{float(row.get('actual_worked_minutes') or 0) / daily_minutes:.1f}",
                f"{float(row.get('actual_worked_minutes') or 0) / 60:.1f} h",
                f"{float(row.get('grace_holidays') or 0):.1f} / {float(row.get('grace_holidays_used') or 0):.1f}",
                f"{float(row.get('deducted_holidays') or 0):.1f}",
                f"{float(row.get('overtime_minutes') or 0) / 60:.1f} h",
                _money(row.get("overtime_pay")),
                _money(row.get("gross_salary")),
                _money(row.get("salary_deduction")),
                _money(row.get("salary_after_holidays")),
                _money(row.get("total_salary")),
            ])
        total_net = sum(float(row.get("total_salary") or 0) for row in records)
        data.append(["", "TOTAL", "", "", "", "", "", "", "", "", "", "", "", _money(total_net)])
        widths = [10, 34, 16, 21, 14, 15, 21, 15, 16, 19, 21, 20, 21, 22]
        table = Table(data, colWidths=[w * mm for w in widths], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("LEADING", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6E0E9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, PALE_BLUE]),
            ("BACKGROUND", (0, -1), (-1, -1), PALE_BLUE),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, -1), (-1, -1), NAVY),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            "* Worked days are equivalent full days calculated from recorded work time. "
            "Overtime is informational and does not affect net salary under current payroll rules. "
            f"Employees included: {len(records)}.",
            styles["Subtitle"],
        ))

    doc.build(story)
    output.seek(0)
    return output
