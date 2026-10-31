from backend.database import get_connection
from backend.services.settings import get_checkout_grace_minutes
from datetime import datetime, date, timedelta
import calendar
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------------------
# HALF-DAY & FULL-DAY ATTENDANCE THRESHOLDS
# ---------------------------------------------------------------------------
# FULL_DAY_MIN_RATIO:
#   Minimum fraction of daily_hours required for a Full Day (1.0 day).
#   Default 1.00 means full shift minus employee's late_grace_minutes
#   (e.g., for an 8h shift with 15m grace, 465 mins = Full Day).
#   Change to Decimal("0.90") if you want 90% of shift to count as Full Day
#   even when late_grace_minutes is 0.
FULL_DAY_MIN_RATIO = Decimal("1.00")

# HALF_DAY_MIN_RATIO:
#   Minimum fraction of daily_hours required for a Half Day (0.5 day).
#   Default 0.50 means at least 50% of daily_hours (e.g., 4h for an 8h shift).
#   Anything below HALF_DAY_MIN_RATIO counts as Absent (0.0 day).
HALF_DAY_MIN_RATIO = Decimal("0.50")

# ENFORCE_LATE_CHECKIN_HALF_DAY:
#   If True, punching in after (expected_check_in + late_grace_minutes)
#   caps a Full Day at a Half Day (0.5) even if total hours are met.
ENFORCE_LATE_CHECKIN_HALF_DAY = False


def _money(value):
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _day_units(value):
    """Return int for whole numbers (e.g. 24) and float for half-days (e.g. 24.5)."""
    quantized = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return int(quantized)
    return float(quantized)


def _ensure_salary_cal_columns(conn, cursor):
    """Ensure full_days and half_days columns exist on salary_cal without breaking existing DBs."""
    try:
        cursor.execute("PRAGMA table_info(salary_cal)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        altered = False
        if "full_days" not in existing_cols:
            cursor.execute("ALTER TABLE salary_cal ADD COLUMN full_days INTEGER DEFAULT 0")
            altered = True
        if "half_days" not in existing_cols:
            cursor.execute("ALTER TABLE salary_cal ADD COLUMN half_days INTEGER DEFAULT 0")
            altered = True
        if "bonus_amount" not in existing_cols:
            cursor.execute("ALTER TABLE salary_cal ADD COLUMN bonus_amount REAL DEFAULT 0")
            altered = True
        if altered:
            conn.commit()
    except Exception:
        pass


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


def _parse_time_to_minutes(time_str):
    """Convert 'HH:MM' or 'HH:MM:SS' into minutes from midnight."""
    if not time_str:
        return None
    parts = str(time_str).strip().split(":")
    if len(parts) < 2:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        return hours * 60 + minutes
    except (TypeError, ValueError):
        return None


def _resolve_worked_minutes(worked_minutes, check_in=None, check_out=None):
    """Use stored worked_minutes, or compute from check_in and check_out if needed."""
    if worked_minutes is not None and Decimal(str(worked_minutes or 0)) > 0:
        return Decimal(str(worked_minutes))

    in_mins = _parse_time_to_minutes(check_in)
    out_mins = _parse_time_to_minutes(check_out)
    if in_mins is None or out_mins is None:
        return Decimal("0")

    duration = out_mins - in_mins
    if duration < 0:
        duration += 24 * 60
    return Decimal(str(max(0, duration)))


def evaluate_day_attendance(
    worked_minutes,
    daily_minutes,
    check_in=None,
    check_out=None,
    expected_check_in=None,
    expected_check_out=None,
    late_grace_minutes=0,
    checkout_grace_minutes=0,
):
    """
    Evaluate a single day's attendance and return:
      - day_credit: Decimal('1.0') for Full Day, Decimal('0.5') for Half Day, Decimal('0.0') for Absent
      - status: 'Full Day' | 'Half Day' | 'Incomplete' | 'Absent'
    """
    daily_minutes = max(Decimal("0"), Decimal(str(daily_minutes or 0)))
    late_grace = max(Decimal("0"), Decimal(str(late_grace_minutes or 0)))
    checkout_grace = max(Decimal("0"), Decimal(str(checkout_grace_minutes or 0)))

    # If one punch is present without the other, treat as Incomplete (0.0 credit)
    if (check_in and not check_out) or (check_out and not check_in):
        return Decimal("0.0"), "Incomplete"

    effective_worked = _resolve_worked_minutes(worked_minutes, check_in, check_out)
    if effective_worked <= 0 or daily_minutes <= 0:
        return Decimal("0.0"), "Absent"

    full_day_threshold = max(
        daily_minutes * HALF_DAY_MIN_RATIO,
        (daily_minutes * FULL_DAY_MIN_RATIO) - late_grace - checkout_grace,
    )
    half_day_threshold = daily_minutes * HALF_DAY_MIN_RATIO

    completed_shift = False
    if expected_check_in and expected_check_out and check_in and check_out:
        exp_in_mins = _parse_time_to_minutes(expected_check_in)
        exp_out_mins = _parse_time_to_minutes(expected_check_out)
        act_in_mins = _parse_time_to_minutes(check_in)
        act_out_mins = _parse_time_to_minutes(check_out)
        if exp_in_mins is not None and exp_out_mins is not None and act_in_mins is not None and act_out_mins is not None:
            if act_in_mins <= (exp_in_mins + int(late_grace)) and act_out_mins >= (exp_out_mins - int(checkout_grace)):
                completed_shift = True

    if completed_shift or effective_worked >= full_day_threshold:
        day_credit = Decimal("1.0")
        status = "Full Day"
    elif effective_worked >= half_day_threshold:
        day_credit = Decimal("0.5")
        status = "Half Day"
    else:
        return Decimal("0.0"), "Absent"

    # Optional: downgrade Full Day to Half Day if employee punched in after grace window
    if ENFORCE_LATE_CHECKIN_HALF_DAY and day_credit == Decimal("1.0") and expected_check_in and check_in:
        expected_in_mins = _parse_time_to_minutes(expected_check_in)
        actual_in_mins = _parse_time_to_minutes(check_in)
        if expected_in_mins is not None and actual_in_mins is not None:
            if actual_in_mins > (expected_in_mins + int(late_grace)):
                day_credit = Decimal("0.5")
                status = "Half Day"

    # Downgrade Full Day to Half Day if employee punched out before checkout grace window
    if day_credit == Decimal("1.0") and expected_check_out and check_out and checkout_grace >= 0:
        expected_out_mins = _parse_time_to_minutes(expected_check_out)
        actual_out_mins = _parse_time_to_minutes(check_out)
        if expected_out_mins is not None and actual_out_mins is not None:
            if actual_out_mins < (expected_out_mins - int(checkout_grace)):
                day_credit = Decimal("0.5")
                status = "Half Day"

    return day_credit, status


def calculate_holiday_deduction(
    expected_working_dates,
    attendance_by_date,
    daily_minutes,
    grace_holidays,
    expected_check_in=None,
    expected_check_out=None,
    late_grace_minutes=0,
    checkout_grace_minutes=0,
):
    """
    Score each scheduled date as:
      - Full Day (1.0 worked day, 0.0 absence)
      - Half Day (0.5 worked day, 0.5 absence)
      - Absent / Incomplete (0.0 worked day, 1.0 absence)

    Grace holidays are applied against total absence_days (supporting 0.5 increments).
    """
    expected_working_dates = list(expected_working_dates or [])
    attendance_by_date = attendance_by_date or {}
    daily_minutes = max(Decimal("0"), Decimal(str(daily_minutes or 0)))

    grace_holidays = max(Decimal("0"), Decimal(str(grace_holidays or 0)))
    if (grace_holidays * 2) != (grace_holidays * 2).to_integral_value():
        raise ValueError("Grace holidays must use 0.5 or whole-day increments")

    worked_days = Decimal("0.0")
    full_days_count = 0
    half_days_count = 0

    for scheduled_date in expected_working_dates:
        date_key = (
            scheduled_date.isoformat()
            if hasattr(scheduled_date, "isoformat")
            else str(scheduled_date)
        )
        entry = attendance_by_date.get(date_key)

        if isinstance(entry, dict):
            raw_worked = entry.get("worked_minutes", 0)
            check_in = entry.get("check_in")
            check_out = entry.get("check_out")
        else:
            raw_worked = entry or 0
            check_in = None
            check_out = None

        day_credit, _ = evaluate_day_attendance(
            worked_minutes=raw_worked,
            daily_minutes=daily_minutes,
            check_in=check_in,
            check_out=check_out,
            expected_check_in=expected_check_in,
            expected_check_out=expected_check_out,
            late_grace_minutes=late_grace_minutes,
            checkout_grace_minutes=checkout_grace_minutes,
        )

        worked_days += day_credit
        if day_credit == Decimal("1.0"):
            full_days_count += 1
        elif day_credit == Decimal("0.5"):
            half_days_count += 1

    expected_working_days = Decimal(str(len(expected_working_dates)))
    absence_days = max(Decimal("0.0"), expected_working_days - worked_days)
    grace_holidays_used = min(grace_holidays, absence_days)
    deducted_holidays = max(Decimal("0.0"), absence_days - grace_holidays_used)
    paid_minutes = max(
        Decimal("0"),
        (expected_working_days - deducted_holidays) * daily_minutes,
    )

    return {
        "full_days": full_days_count,
        "half_days": half_days_count,
        "absence_days": _day_units(absence_days),
        "actual_worked_days": _day_units(worked_days),
        "grace_holidays_used": _day_units(grace_holidays_used),
        "deducted_holidays": _day_units(deducted_holidays),
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


def is_eligible_for_attendance_bonus(
    expected_working_dates,
    attendance_by_date,
    daily_hours,
    expected_check_in=None,
    expected_check_out=None,
    late_grace_minutes=0,
    checkout_grace_minutes=0,
    absence_days=0,
    grace_holidays_used=0,
    half_days=0,
):
    """
    Check if employee qualifies for attendance bonus.

    Criteria:
      1. No holiday taken, not even grace:
         - At least one scheduled working day exists in period
         - absence_days == 0
         - grace_holidays_used == 0
         - half_days == 0 (no partial worked days)
      2. Proper arrival and departure on every scheduled working day:
         - Both check_in and check_out punches must be recorded
         - check_in <= expected_check_in + late_grace_minutes (no late coming beyond grace)
         - check_out >= expected_check_out (no early exit)
         - worked duration >= daily_hours * 60 (shift hours fulfilled or overtimed)
    """
    if not expected_working_dates:
        return False

    if float(absence_days or 0) > 0:
        return False

    if float(grace_holidays_used or 0) > 0:
        return False

    if int(half_days or 0) > 0:
        return False

    req_minutes = int(round(float(daily_hours or 0) * 60))
    grace_mins = int(late_grace_minutes or 0)

    for scheduled_date in expected_working_dates:
        date_key = (
            scheduled_date.isoformat()
            if hasattr(scheduled_date, "isoformat")
            else str(scheduled_date)
        )
        record = attendance_by_date.get(date_key)
        if not record or not isinstance(record, dict):
            return False

        check_in = record.get("check_in")
        check_out = record.get("check_out")
        if not check_in or not check_out:
            return False

        # Grace-assisted arrival check (no late coming beyond grace)
        if expected_check_in:
            in_mins = _parse_time_to_minutes(check_in)
            exp_in_mins = _parse_time_to_minutes(expected_check_in)
            if in_mins is not None and exp_in_mins is not None:
                if in_mins > (exp_in_mins + grace_mins):
                    return False

        checkout_grace = int(checkout_grace_minutes or 0)
        # Early exit check (no early exiting beyond checkout grace)
        if expected_check_out:
            out_mins = _parse_time_to_minutes(check_out)
            exp_out_mins = _parse_time_to_minutes(expected_check_out)
            if out_mins is not None and exp_out_mins is not None:
                if out_mins < (exp_out_mins - checkout_grace):
                    return False

        # Shift duration check (proper or overtimed, allowing grace)
        if req_minutes > 0:
            eff_worked = int(_resolve_worked_minutes(record.get("worked_minutes"), check_in, check_out))
            min_allowed = max(0, req_minutes - grace_mins - checkout_grace)
            shift_fulfilled = (
                expected_check_in and expected_check_out and
                _parse_time_to_minutes(check_in) is not None and _parse_time_to_minutes(expected_check_in) is not None and
                _parse_time_to_minutes(check_out) is not None and _parse_time_to_minutes(expected_check_out) is not None and
                _parse_time_to_minutes(check_in) <= (_parse_time_to_minutes(expected_check_in) + grace_mins) and
                _parse_time_to_minutes(check_out) >= (_parse_time_to_minutes(expected_check_out) - checkout_grace)
            )
            if not shift_fulfilled and eff_worked < min_allowed:
                return False

    return True


def generate_salary(employee_id, month, role=None):
    """
    Generate or update the monthly salary record.

    The record stores a historical snapshot of the employee's
    configuration and attendance calculation (including Full Days
    and Half Days) for that month.

    Overtime is informational only and never increases salary.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        _ensure_salary_cal_columns(conn, cursor)

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
                working_weekdays,
                expected_check_in,
                COALESCE(late_grace_minutes, 0),
                expected_check_out
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
            working_weekdays,
            expected_check_in,
            late_grace_minutes,
            expected_check_out,
        ) = employee

        monthly_salary = float(monthly_salary or 0)
        daily_hours = float(daily_hours or 0)
        overtime_enabled = bool(overtime_enabled)
        overtime_rate = float(overtime_rate or 1.0)
        salary_type = salary_type or "monthly"
        grace_holidays = max(0.0, float(grace_holidays or 0))
        late_grace_minutes = int(late_grace_minutes or 0)

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
                check_out,
                check_in
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
        for attendance_date, worked_minutes, overtime_for_date, check_out, check_in in attendance_rows:
            attendance_by_date[attendance_date] = {
                "worked_minutes": int(worked_minutes or 0),
                "check_in": check_in,
                "check_out": check_out,
            }

        max_att_date = max(
            (date.fromisoformat(row[0]) for row in attendance_rows if row[0]),
            default=None,
        )

        if month_start > today:
            period_end = min(month_end, max_att_date) if max_att_date else month_start - timedelta(days=1)
        elif month_end <= today:
            period_end = month_end
        else:
            today_row = next(
                (row for row in attendance_rows if row[0] == today.isoformat()),
                None,
            )
            effective_today = today if today_row and today_row[3] else today - timedelta(days=1)
            # If attendance records exist beyond today (e.g. populated/punched through month-end),
            # include all recorded attendance dates so half days/absences are not missed.
            if max_att_date and max_att_date > effective_today:
                period_end = min(month_end, max_att_date)
            else:
                period_end = effective_today

        period_working_dates = _scheduled_dates(
            month_start, min(period_end, month_end), weekdays
        )
        expected_working_days_for_period = len(period_working_dates)

        checkout_grace_minutes = get_checkout_grace_minutes()
        holiday_metrics = calculate_holiday_deduction(
            expected_working_dates=period_working_dates,
            attendance_by_date=attendance_by_date,
            daily_minutes=daily_hours * 60.0,
            grace_holidays=grace_holidays,
            expected_check_in=expected_check_in,
            expected_check_out=expected_check_out,
            late_grace_minutes=late_grace_minutes,
            checkout_grace_minutes=checkout_grace_minutes,
        )

        full_days = holiday_metrics["full_days"]
        half_days = holiday_metrics["half_days"]
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
            monthly_amount = Decimal(str(monthly_salary))
            daily_rate = monthly_amount / Decimal(days_in_month)
            hourly_rate = (
                float(daily_rate / Decimal(str(daily_hours)))
                if daily_hours > 0 else 0.0
            )
            gross_amount = monthly_amount
            deduction_amount = daily_rate * Decimal(str(deducted_holidays))

        hourly_rate_snapshot = _money(hourly_rate)
        gross_salary = _money(gross_amount)
        salary_deduction = _money(deduction_amount)
        salary_after_holidays = _money(
            Decimal(str(gross_salary)) - Decimal(str(salary_deduction))
        )

        # Attendance bonus evaluation
        cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'attendance_bonus_amount'")
        bonus_setting_row = cursor.fetchone()
        system_bonus_val = (
            float(bonus_setting_row[0])
            if bonus_setting_row and bonus_setting_row[0]
            else 1000.0
        )

        bonus_eligible = is_eligible_for_attendance_bonus(
            expected_working_dates=period_working_dates,
            attendance_by_date=attendance_by_date,
            daily_hours=daily_hours,
            expected_check_in=expected_check_in,
            expected_check_out=expected_check_out,
            late_grace_minutes=late_grace_minutes,
            checkout_grace_minutes=checkout_grace_minutes,
            absence_days=absence_days,
            grace_holidays_used=grace_holidays_used,
            half_days=half_days,
        )
        bonus_amount = _money(system_bonus_val) if bonus_eligible else 0.0

        base_salary = monthly_salary
        overtime_pay = 0.0
        total_salary = _money(
            Decimal(str(salary_after_holidays))
            + Decimal(str(overtime_pay))
            + Decimal(str(bonus_amount))
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

            user_role = str(role).lower() if role else ""
            if (
                current_locked_status == 1
                and lock_value == 1
                and user_role not in ("head", "developer")
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
                    full_days = ?,
                    half_days = ?,
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
                    bonus_amount = ?,
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
                full_days,
                half_days,
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
                bonus_amount,
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
                    full_days,
                    half_days,
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
                    bonus_amount,
                    total_salary,
                    locked,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                full_days,
                half_days,
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
                bonus_amount,
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
            "full_days": full_days,
            "half_days": half_days,
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
            "bonus_amount": bonus_amount,
            "total_salary": total_salary,
            "locked": lock_value
        }

    finally:
        cursor.close()
        conn.close()


def _normalize_day_counts(record_dict):
    """Ensure full_days and half_days are always populated integers even for legacy rows."""
    worked = Decimal(str(record_dict.get("actual_worked_days") or 0))
    full_days = record_dict.get("full_days")
    half_days = record_dict.get("half_days")

    if full_days is None and half_days is None:
        # Derive sensible default from actual_worked_days if legacy record had NULLs
        if worked != worked.to_integral_value():
            half_days = 1
            full_days = max(0, int(worked - Decimal("0.5")))
        else:
            half_days = 0
            full_days = max(0, int(worked))
    else:
        full_days = int(full_days or 0)
        half_days = int(half_days or 0)
        # If both were 0 on a legacy row that had actual_worked_days > 0, infer from worked
        if full_days == 0 and half_days == 0 and worked > 0:
            if worked != worked.to_integral_value():
                half_days = 1
                full_days = max(0, int(worked - Decimal("0.5")))
            else:
                full_days = int(worked)

    record_dict["full_days"] = full_days
    record_dict["half_days"] = half_days
    record_dict["actual_worked_days"] = _day_units(worked)
    record_dict["absence_days"] = _day_units(record_dict.get("absence_days") or 0)
    record_dict["grace_holidays"] = _day_units(record_dict.get("grace_holidays") or 0)
    record_dict["grace_holidays_used"] = _day_units(record_dict.get("grace_holidays_used") or 0)
    record_dict["deducted_holidays"] = _day_units(record_dict.get("deducted_holidays") or 0)
    record_dict["bonus_amount"] = _money(record_dict.get("bonus_amount") or 0)
    return record_dict


def get_salary(employee_id, month):
    conn = get_connection()
    cursor = conn.cursor()

    _ensure_salary_cal_columns(conn, cursor)

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
            full_days,
            half_days,
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
            bonus_amount,
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
        "full_days",
        "half_days",
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
        "bonus_amount",
        "total_salary",
        "locked",
        "created_at",
        "updated_at",
    ]

    return _normalize_day_counts(dict(zip(columns, row)))


def get_salary_records(employee_id=None, month=None):
    """Return monthly salary history with optional filters."""

    conn = get_connection()
    cursor = conn.cursor()

    _ensure_salary_cal_columns(conn, cursor)

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
            full_days,
            half_days,
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
            bonus_amount,
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
        "full_days",
        "half_days",
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
        "bonus_amount",
        "total_salary",
        "locked",
        "created_at",
        "updated_at",
    ]

    return [_normalize_day_counts(dict(zip(columns, row))) for row in rows]


def update_salary_details(employee_id, month, new_salary, role):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT locked FROM salary_cal WHERE employee_id = ? AND month = ?", (employee_id, month))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        raise Exception("Salary record not found")

    is_locked = row[0]

    user_role = str(role).lower() if role else ""
    if is_locked == 1 and user_role not in ('head', 'developer'):
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