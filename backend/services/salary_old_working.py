from backend.database import get_connection
from datetime import datetime, date
import calendar


def get_working_days_for_month(cursor, year, month):
    """
    Count configured working days for a specific month.

    0 = Monday
    1 = Tuesday
    2 = Wednesday
    3 = Thursday
    4 = Friday
    5 = Saturday
    6 = Sunday
    """

    cursor.execute("""
        SELECT setting_value
        FROM system_settings
        WHERE setting_key = 'working_days'
    """)

    row = cursor.fetchone()

    if not row or not row[0]:
        working_weekdays = {0, 1, 2, 3, 4}
    else:
        try:
            working_weekdays = {
                int(day.strip())
                for day in row[0].split(",")
                if day.strip()
            }
        except ValueError:
            working_weekdays = {0, 1, 2, 3, 4}

    days_in_month = calendar.monthrange(year, month)[1]

    working_days = 0

    for day_number in range(1, days_in_month + 1):
        current_date = date(year, month, day_number)

        if current_date.weekday() in working_weekdays:
            working_days += 1

    return working_days

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
                salary_type
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
            salary_type
        ) = employee

        monthly_salary = float(monthly_salary or 0)
        daily_hours = float(daily_hours or 0)
        overtime_enabled = bool(overtime_enabled)
        overtime_rate = float(overtime_rate or 1.0)
        salary_type = salary_type or "monthly"

        try:
            year, month_num = map(int, month.split("-"))
        except ValueError:
            raise Exception("Month must be in YYYY-MM format")

        working_days = get_working_days_for_month(
            cursor,
            year,
            month_num
        )

        expected_monthly_minutes = (
            working_days * daily_hours * 60
        )

        cursor.execute("""
            SELECT
                COALESCE(SUM(worked_minutes), 0),
                COALESCE(SUM(overtime_minutes), 0)
            FROM attendance
            WHERE employee_id = ?
              AND date LIKE ?
        """, (
            employee_id,
            f"{month}-%"
        ))

        attendance = cursor.fetchone()
        actual_worked_minutes = int(attendance[0] or 0)
        overtime_minutes = int(attendance[1] or 0)

        if expected_monthly_minutes > 0:
            hourly_rate = monthly_salary / (working_days * daily_hours)
        else:
            hourly_rate = 0.0

        hourly_rate_snapshot = round(hourly_rate, 2)

        if expected_monthly_minutes > 0:
            base_salary = (
                monthly_salary
                * actual_worked_minutes
                / expected_monthly_minutes
            )
        else:
            base_salary = 0.0

        # Overtime is informational only. It never increases salary.
        overtime_pay = 0.0

        total_salary = round(
            base_salary + overtime_pay,
            2
        )

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
                    daily_hours = ?,
                    working_days = ?,
                    expected_monthly_minutes = ?,
                    actual_worked_minutes = ?,
                    total_hours = ?,
                    overtime_minutes = ?,
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
                daily_hours,
                working_days,
                expected_monthly_minutes,
                actual_worked_minutes,
                total_hours,
                overtime_minutes,
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
                    daily_hours,
                    working_days,
                    expected_monthly_minutes,
                    actual_worked_minutes,
                    total_hours,
                    overtime_minutes,
                    hourly_rate_snapshot,
                    base_salary,
                    overtime_pay,
                    total_salary,
                    locked,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                employee_id,
                month,
                employee_name,
                employee_role,
                salary_type,
                monthly_salary,
                daily_hours,
                working_days,
                expected_monthly_minutes,
                actual_worked_minutes,
                total_hours,
                overtime_minutes,
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
            "total_hours": total_hours,
            "overtime_minutes": overtime_minutes,
            "hourly_rate": hourly_rate_snapshot,
            "base_salary": round(base_salary, 2),
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
            daily_hours,
            working_days,
            expected_monthly_minutes,
            actual_worked_minutes,
            total_hours,
            overtime_minutes,
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
        "daily_hours",
        "working_days",
        "expected_monthly_minutes",
        "actual_worked_minutes",
        "total_hours",
        "overtime_minutes",
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
            daily_hours,
            working_days,
            expected_monthly_minutes,
            actual_worked_minutes,
            total_hours,
            overtime_minutes,
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
        "daily_hours",
        "working_days",
        "expected_monthly_minutes",
        "actual_worked_minutes",
        "total_hours",
        "overtime_minutes",
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