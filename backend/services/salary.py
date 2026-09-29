from backend.database import get_connection
from datetime import datetime, date, timedelta
import calendar
from decimal import Decimal, ROUND_HALF_UP


def _money(value):
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _parse_working_weekdays(value):
    try:
        weekdays = {
            int(item.strip())
            for item in str(value or "0,1,2,3,4,5").split(",")
            if item.strip()
        }
        weekdays = {day for day in weekdays if 0 <= day <= 6}
    except (TypeError, ValueError):
        weekdays = set()
    return weekdays or {0, 1, 2, 3, 4, 5}


def _scheduled_dates(start, end, weekdays):
    if end < start:
        return []
    return [
        date.fromordinal(ordinal)
        for ordinal in range(start.toordinal(), end.toordinal() + 1)
        if date.fromordinal(ordinal).weekday() in weekdays
    ]


# def get_working_days_for_month(cursor, year, month):
#     """
#     Count configured working days for a specific month.

#     0 = Monday
#     1 = Tuesday
#     2 = Wednesday
#     3 = Thursday
#     4 = Friday
#     5 = Saturday
#     6 = Sunday
#     """

#     cursor.execute("""
#         SELECT setting_value
#         FROM system_settings
#         WHERE setting_key = 'working_days'
#     """)

#     row = cursor.fetchone()

#     if not row or not row[0]:
#         working_weekdays = {0, 1, 2, 3, 4}
#     else:
#         try:
#             working_weekdays = {
#                 int(day.strip())
#                 for day in row[0].split(",")
#                 if day.strip()
#             }
#         except ValueError:
#             working_weekdays = {0, 1, 2, 3, 4}

#     days_in_month = calendar.monthrange(year, month)[1]

#     working_days = 0

#     for day_number in range(1, days_in_month + 1):
#         current_date = date(year, month, day_number)

#         if current_date.weekday() in working_weekdays:
#             working_days += 1

#     return working_days


# def get_working_weekdays(cursor):
#     """Return configured working weekdays as Python weekday integers."""
#     cursor.execute("""
#         SELECT setting_value
#         FROM system_settings
#         WHERE setting_key = 'working_days'
#     """)
#     row = cursor.fetchone()

#     if not row or not row[0]:
#         return {0, 1, 2, 3, 4}

#     try:
#         weekdays = {
#             int(day.strip())
#             for day in row[0].split(",")
#             if day.strip()
#         }
#         return weekdays or {0, 1, 2, 3, 4}
#     except (TypeError, ValueError):
#         return {0, 1, 2, 3, 4}


def calculate_holiday_deduction(
    expected_working_dates,
    attendance_by_date,
    daily_minutes,
    grace_holidays
):
    """Count a scheduled date as worked when it has any recorded work time.

    Short shifts still count as worked days. Only a scheduled date without
    recorded work is an absence; whole-day grace allowance is deducted from
    those absences before calculating charged leave.
    """
    expected_working_dates = list(expected_working_dates or [])
    attendance_by_date = attendance_by_date or {}
    daily_minutes = max(Decimal("0"), Decimal(str(daily_minutes or 0)))

    grace_holidays = max(Decimal("0"), Decimal(str(grace_holidays or 0)))
    if grace_holidays != grace_holidays.to_integral_value():
        raise ValueError("Grace holidays must use whole-day increments")

    worked_days = 0
    for scheduled_date in expected_working_dates:
        date_key = (
            scheduled_date.isoformat()
            if hasattr(scheduled_date, "isoformat")
            else str(scheduled_date)
        )
        worked_minutes = Decimal(str(attendance_by_date.get(date_key, 0) or 0))
        if worked_minutes > 0:
            worked_days += 1

    expected_working_days = len(expected_working_dates)
    absence_days = expected_working_days - worked_days
    grace_holidays_used = min(int(grace_holidays), absence_days)
    deducted_holidays = absence_days - grace_holidays_used
    paid_minutes = max(
        Decimal("0"),
        Decimal(expected_working_days - deducted_holidays) * daily_minutes,
    )

    return {
        "absence_days": absence_days,
        "actual_worked_days": worked_days,
        "grace_holidays_used": grace_holidays_used,
        "deducted_holidays": deducted_holidays,
        "paid_minutes": round(float(paid_minutes), 4),
    }

def calculate_overtime_pay(
    overtime_minutes,
    hourly_rate,
    overtime_rate
):
    if not overtime_minutes or overtime_minutes <= 0:
        return 0.0

    overtime_hours = overtime_minutes / 60

    return round(
        overtime_hours
        * float(hourly_rate or 0)
        * float(overtime_rate or 1.5),
        2
    )


def generate_salary(employee_id, month, role=None):
    """
    Generate or update the monthly salary record.

    The record stores a historical snapshot of the employee's
    configuration and attendance calculation for that month.

    Overtime is informational only and never increases salary.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT salary_id, locked, created_at
            FROM salary_cal
            WHERE employee_id = ?
              AND month = ?
        """, (employee_id, month))

        existing = cursor.fetchone()

        cursor.execute("""
            SELECT
                name,
                role,
                monthly_salary,
                daily_hours,
                overtime_enabled,
                overtime_rate,
                salary_type,
                COALESCE(grace_holidays, 0),
                working_weekdays
            FROM employees
            WHERE employee_id = ?
        """, (employee_id,))

        employee = cursor.fetchone()

        if not employee:
            raise Exception("Employee not found")

        (
            employee_name,
            employee_role,
            monthly_salary,
            daily_hours,
            overtime_enabled,
            overtime_rate,
            salary_type,
            grace_holidays,
            working_weekdays
        ) = employee

        monthly_salary = float(monthly_salary or 0)
        daily_hours = float(daily_hours or 0)
        overtime_enabled = bool(overtime_enabled)
        overtime_rate = float(overtime_rate or 1.0)
        salary_type = salary_type or "monthly"
        grace_holidays = max(0.0, float(grace_holidays or 0))
        
        try:
            year, month_num = map(int, month.split("-"))
            if month_num < 1 or month_num > 12:
                raise ValueError
        except ValueError:
            raise Exception("Month must be in YYYY-MM format")

        weekdays = _parse_working_weekdays(working_weekdays)
        days_in_month = calendar.monthrange(year, month_num)[1]
        month_start = date(year, month_num, 1)
        month_end = date(year, month_num, days_in_month)
        full_month_working_dates = _scheduled_dates(
            month_start, month_end, weekdays
        )
        working_days = len(full_month_working_dates)
        if working_days == 0:
            raise Exception("Employee has no scheduled working dates in this month")

        expected_monthly_minutes = working_days * daily_hours * 60.0

        cursor.execute("""
            SELECT
                date,
                COALESCE(worked_minutes, 0),
                COALESCE(overtime_minutes, 0),
                check_out
            FROM attendance
            WHERE employee_id = ?
              AND date LIKE ?
            ORDER BY date ASC
        """, (
            employee_id,
            f"{month}-%"
        ))

        attendance_rows = cursor.fetchall()
        actual_worked_minutes = int(
            sum(int(row[1] or 0) for row in attendance_rows)
        )
        overtime_minutes = int(
            sum(int(row[2] or 0) for row in attendance_rows)
        )

        today = date.today()
        attendance_by_date = {}
        for attendance_date, worked_minutes, overtime_for_date, check_out in attendance_rows:
            attendance_by_date[attendance_date] = int(worked_minutes or 0)

        if month_start > today:
            period_end = month_start - timedelta(days=1)
        elif month_end <= today:
            period_end = month_end
        else:
            # Do not assess today's shift until it has been checked out.
            today_row = next(
                (row for row in attendance_rows if row[0] == today.isoformat()),
                None,
            )
            period_end = today if today_row and today_row[3] else today - timedelta(days=1)

        period_working_dates = _scheduled_dates(
            month_start, min(period_end, month_end), weekdays
        )
        expected_working_days_for_period = len(period_working_dates)

        holiday_metrics = calculate_holiday_deduction(
            expected_working_dates=period_working_dates,
            attendance_by_date=attendance_by_date,
            daily_minutes=daily_hours * 60.0,
            grace_holidays=grace_holidays,
        )

        absence_days = holiday_metrics["absence_days"]
        actual_worked_days = holiday_metrics["actual_worked_days"]
        grace_holidays_used = holiday_metrics["grace_holidays_used"]
        deducted_holidays = holiday_metrics["deducted_holidays"]
        paid_minutes = holiday_metrics["paid_minutes"]

        if salary_type == "hourly":
            hourly_rate = monthly_salary
            gross_amount = (
                Decimal(str(hourly_rate))
                * Decimal(str(daily_hours))
                * expected_working_days_for_period
            )
            deduction_amount = (
                Decimal(str(hourly_rate))
                * Decimal(str(daily_hours))
                * Decimal(str(deducted_holidays))
            )
        else:
            hourly_rate = (
                monthly_salary / (working_days * daily_hours)
                if daily_hours > 0 else 0.0
            )
            # A fixed monthly salary is paid in full. Attendance affects it
            # only through chargeable full-day absences below.
            gross_amount = Decimal(str(monthly_salary))
            deduction_amount = (
                Decimal(str(monthly_salary))
                * Decimal(str(deducted_holidays))
                / working_days
            )

        hourly_rate_snapshot = _money(hourly_rate)
        gross_salary = _money(gross_amount)
        salary_deduction = _money(deduction_amount)
        salary_after_holidays = _money(
            Decimal(str(gross_salary)) - Decimal(str(salary_deduction))
        )

        # Keep the assigned salary or hourly rate as the base amount. Pay after
        # attendance deductions is reported independently above.
        base_salary = monthly_salary

        # Overtime is informational only. It never increases salary.
        overtime_pay = 0.0

        total_salary = _money(Decimal(str(salary_after_holidays)) + Decimal(str(overtime_pay)))

        last_day = calendar.monthrange(year, month_num)[1]
        last_date = datetime(
            year,
            month_num,
            last_day,
            23,
            59,
            59
        )

        lock_value = int(datetime.now() > last_date)

        total_hours = round(
            actual_worked_minutes / 60,
            4
        )

        now = datetime.now().isoformat(timespec="seconds")
        created_at = existing[2] if existing and existing[2] else now

        if existing:
            salary_id, current_locked_status, _ = existing

            if (
                current_locked_status == 1
                and lock_value == 1
                and role != "head"
            ):
                raise Exception(
                    "Salary already locked for this month. "
                    "Only Head Developer can regenerate."
                )

            cursor.execute("""
                UPDATE salary_cal
                SET
                    employee_name = ?,
                    employee_role = ?,
                    salary_type = ?,
                    monthly_salary_snapshot = ?,
                    gross_salary = ?,
                    salary_deduction = ?,
                    salary_after_holidays = ?,
                    daily_hours = ?,
                    working_days = ?,
                    expected_monthly_minutes = ?,
                    actual_worked_minutes = ?,
                    actual_worked_days = ?,
                    total_hours = ?,
                    overtime_minutes = ?,
                    grace_holidays_snapshot = ?,
                    absence_days = ?,
                    grace_holidays_used = ?,
                    deducted_holidays = ?,
                    paid_minutes = ?,
                    hourly_rate_snapshot = ?,
                    base_salary = ?,
                    overtime_pay = ?,
                    total_salary = ?,
                    locked = ?,
                    created_at = ?,
                    updated_at = ?
                WHERE salary_id = ?
            """, (
                employee_name,
                employee_role,
                salary_type,
                monthly_salary,
                round(gross_salary, 2),
                round(salary_deduction, 2),
                round(salary_after_holidays, 2),
                daily_hours,
                working_days,
                expected_monthly_minutes,
                actual_worked_minutes,
                actual_worked_days,
                total_hours,
                overtime_minutes,
                grace_holidays,
                absence_days,
                grace_holidays_used,
                deducted_holidays,
                paid_minutes,
                hourly_rate_snapshot,
                round(base_salary, 2),
                overtime_pay,
                total_salary,
                lock_value,
                created_at,
                now,
                salary_id
            ))

        else:
            cursor.execute("""
                INSERT INTO salary_cal (
                    employee_id,
                    month,
                    employee_name,
                    employee_role,
                    salary_type,
                    monthly_salary_snapshot,
                    gross_salary,
                    salary_deduction,
                    salary_after_holidays,
                    daily_hours,
                    working_days,
                    expected_monthly_minutes,
                    actual_worked_minutes,
                    actual_worked_days,
                    total_hours,
                    overtime_minutes,
                    grace_holidays_snapshot,
                    absence_days,
                    grace_holidays_used,
                    deducted_holidays,
                    paid_minutes,
                    hourly_rate_snapshot,
                    base_salary,
                    overtime_pay,
                    total_salary,
                    locked,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                employee_id,
                month,
                employee_name,
                employee_role,
                salary_type,
                monthly_salary,
                round(gross_salary, 2),
                round(salary_deduction, 2),
                round(salary_after_holidays, 2),
                daily_hours,
                working_days,
                expected_monthly_minutes,
                actual_worked_minutes,
                actual_worked_days,
                total_hours,
                overtime_minutes,
                grace_holidays,
                absence_days,
                grace_holidays_used,
                deducted_holidays,
                paid_minutes,
                hourly_rate_snapshot,
                round(base_salary, 2),
                overtime_pay,
                total_salary,
                lock_value,
                now,
                now
            ))

        conn.commit()

        return {
            "employee_id": employee_id,
            "employee_name": employee_name,
            "employee_role": employee_role,
            "month": month,
            "salary_type": salary_type,
            "monthly_salary": monthly_salary,
            "daily_hours": daily_hours,
            "working_days": working_days,
            "expected_monthly_minutes": expected_monthly_minutes,
            "actual_worked_minutes": actual_worked_minutes,
            "actual_worked_days": actual_worked_days,
            "total_hours": total_hours,
            "overtime_minutes": overtime_minutes,
            "grace_holidays": grace_holidays,
            "absence_days": absence_days,
            "grace_holidays_used": grace_holidays_used,
            "deducted_holidays": deducted_holidays,
            "paid_minutes": paid_minutes,
            "hourly_rate": hourly_rate_snapshot,
            "base_salary": round(base_salary, 2),
            "gross_salary": round(gross_salary, 2),
            "salary_deduction": round(salary_deduction, 2),
            "salary_after_holidays": round(salary_after_holidays, 2),
            "overtime_pay": round(overtime_pay, 2),
            "total_salary": total_salary,
            "locked": lock_value
        }

    finally:
        cursor.close()
        conn.close()


def get_salary(employee_id, month):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            salary_id,
            employee_id,
            month,
            employee_name,
            employee_role,
            salary_type,
            monthly_salary_snapshot,
            gross_salary,
            salary_deduction,
            salary_after_holidays,
            daily_hours,
            working_days,
            expected_monthly_minutes,
            actual_worked_minutes,
            actual_worked_days,
            total_hours,
            overtime_minutes,
            grace_holidays_snapshot,
            absence_days,
            grace_holidays_used,
            deducted_holidays,
            paid_minutes,
            hourly_rate_snapshot,
            base_salary,
            overtime_pay,
            total_salary,
            locked,
            created_at,
            updated_at
        FROM salary_cal
        WHERE employee_id = ? AND month = ?
    """, (employee_id, month))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return None

    columns = [
        "salary_id",
        "employee_id",
        "month",
        "employee_name",
        "employee_role",
        "salary_type",
        "monthly_salary",
        "gross_salary",
        "salary_deduction",
        "salary_after_holidays",
        "daily_hours",
        "working_days",
        "expected_monthly_minutes",
        "actual_worked_minutes",
        "actual_worked_days",
        "total_hours",
        "overtime_minutes",
        "grace_holidays",
        "absence_days",
        "grace_holidays_used",
        "deducted_holidays",
        "paid_minutes",
        "hourly_rate",
        "base_salary",
        "overtime_pay",
        "total_salary",
        "locked",
        "created_at",
        "updated_at",
    ]

    return dict(zip(columns, row))


def get_salary_records(employee_id=None, month=None):
    """Return monthly salary history with optional filters."""

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            salary_id,
            employee_id,
            month,
            employee_name,
            employee_role,
            salary_type,
            monthly_salary_snapshot,
            gross_salary,
            salary_deduction,
            salary_after_holidays,
            daily_hours,
            working_days,
            expected_monthly_minutes,
            actual_worked_minutes,
            actual_worked_days,
            total_hours,
            overtime_minutes,
            grace_holidays_snapshot,
            absence_days,
            grace_holidays_used,
            deducted_holidays,
            paid_minutes,
            hourly_rate_snapshot,
            base_salary,
            overtime_pay,
            total_salary,
            locked,
            created_at,
            updated_at
        FROM salary_cal
        WHERE 1 = 1
    """

    params = []

    if employee_id is not None:
        query += " AND employee_id = ?"
        params.append(employee_id)

    if month:
        query += " AND month = ?"
        params.append(month)

    query += " ORDER BY month DESC, employee_name COLLATE NOCASE ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    columns = [
        "salary_id",
        "employee_id",
        "month",
        "employee_name",
        "employee_role",
        "salary_type",
        "monthly_salary",
        "gross_salary",
        "salary_deduction",
        "salary_after_holidays",
        "daily_hours",
        "working_days",
        "expected_monthly_minutes",
        "actual_worked_minutes",
        "actual_worked_days",
        "total_hours",
        "overtime_minutes",
        "grace_holidays",
        "absence_days",
        "grace_holidays_used",
        "deducted_holidays",
        "paid_minutes",
        "hourly_rate",
        "base_salary",
        "overtime_pay",
        "total_salary",
        "locked",
        "created_at",
        "updated_at",
    ]

    return [dict(zip(columns, row)) for row in rows]


def update_salary_details(employee_id, month, new_salary, role):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check current lock status
    cursor.execute("SELECT locked FROM salary_cal WHERE employee_id = ? AND month = ?", (employee_id, month))
    row = cursor.fetchone()
    
    if not row:
        cursor.close()
        conn.close()
        raise Exception("Salary record not found")
        
    is_locked = row[0]
    
    # GOD MODE LOGIC: If role is 'head', allow update even if locked.
    if is_locked == 1 and role != 'head':
        cursor.close()
        conn.close()
        raise Exception("Salary is locked. Only Head Developer can edit.")

    cursor.execute("""
        UPDATE salary_cal
        SET
            total_salary = ?,
            updated_at = ?
        WHERE employee_id = ? AND month = ?
    """, (
        new_salary,
        datetime.now().isoformat(timespec="seconds"),
        employee_id,
        month
    ))
    
    conn.commit()
    cursor.close()
    conn.close()
