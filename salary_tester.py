"""
Standalone salary + attendance edge-case test runner.

Run from the HR project root:

    python salary_tester.py

IMPORTANT:
- This file does NOT modify production service code.
- Test employees are created with a reserved name prefix and removed in cleanup.
- Test attendance and salary rows are also removed in cleanup.
- Overtime pay is intentionally expected to remain 0.00.
- Attendance tests model the application's stored attendance records.
- Manual check-in/check-out API behavior is NOT tested here because the
  production workflow receives punches from the Secureye device.

Business model tested here:

    First machine punch of the day = check-in
    Last machine punch of the day  = check-out
    No lunch/break deduction
    Full day  = 100% of daily_hours worked
    Half day  = 50% of daily_hours worked
    Absent    = < 50% of daily_hours worked (or Incomplete)
    Overtime  = informational only
    Overtime pay = 0
    Salary deduction = (monthly_salary / days_in_calendar_month) * deducted_absence_days
    Grace holidays reduce deductible absence
    Salary cannot exceed the configured monthly salary
    Completed-month salary becomes locked
    Only Head can regenerate a locked completed salary
    Working days are determined by each employee's working_weekdays schedule
"""

import os
import sys
import traceback
import calendar as cal_mod
from datetime import date

# =========================================================
# PROJECT PATH
# =========================================================

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# =========================================================
# APPLICATION IMPORTS
# =========================================================

from backend.database import employee_db, get_connection
from backend.services.employee import add_employee
from backend.services.attendance import calculate_attendance_metrics
from backend.services.salary import generate_salary, get_salary


# =========================================================
# TEST CONFIGURATION
# =========================================================

TEST_PREFIX = "__SALARY_TEST__"

# July 2026 is a completed month — makes salary locking deterministic.
TEST_MONTH = "2026-07"

# Default schedule: Mon-Sat (0-5) = 27 working days in July 2026.
# All expected salary values in these tests are calculated against 27 working
# days and 31 calendar days (days_in_month).
#
#   daily_rate     = monthly_salary / 31   (calendar days, as per engine)
#   deduction      = daily_rate * deducted_absence_days
#   total_salary   = monthly_salary - deduction
#
# July 2026 Mon-Sat dates (27 total):
#   1,2,3,4 | 6,7,8,9,10,11 | 13,14,15,16,17,18 |
#   20,21,22,23,24,25 | 27,28,29,30,31
DEFAULT_WORKING_WEEKDAYS = "0,1,2,3,4,5"   # Mon-Sat
DAYS_IN_TEST_MONTH       = 31              # July 2026 calendar days
WORKING_DAYS_IN_MONTH    = 27              # Mon-Sat count in July 2026


def _expected_salary(monthly_salary, absence_days, grace=0):
    """
    Compute the expected total_salary using the engine's calendar-day formula.

        daily_rate  = monthly_salary / DAYS_IN_TEST_MONTH
        deducted    = max(0, absence_days - grace)
        total       = monthly_salary - daily_rate * deducted
    """
    daily_rate  = monthly_salary / DAYS_IN_TEST_MONTH
    deducted    = max(0.0, absence_days - grace)
    return round(monthly_salary - daily_rate * deducted, 2)


# =========================================================
# TEST COUNTERS
# =========================================================

passed = 0
failed = 0

created_employee_ids = []


# =========================================================
# REPORTING HELPERS
# =========================================================

def report_pass(name):
    global passed
    passed += 1
    print(f"PASS  {name}")


def report_fail(name, details):
    global failed
    failed += 1
    print(f"FAIL  {name}")
    print(f"      {details}")


def assert_equal(name, actual, expected):
    if actual == expected:
        report_pass(name)
        return True
    report_fail(name, f"expected {expected!r}, got {actual!r}")
    return False


def assert_close(name, actual, expected, tolerance=0.02):
    try:
        ok = abs(float(actual) - float(expected)) <= tolerance
    except (TypeError, ValueError):
        ok = False
    if ok:
        report_pass(name)
        return True
    report_fail(name, f"expected {expected}, got {actual}")
    return False


def assert_raises(name, func, expected_message=None):
    try:
        func()
    except Exception as exc:
        if expected_message is None or expected_message in str(exc):
            report_pass(name)
            return True
        report_fail(
            name,
            f"raised {type(exc).__name__}: {exc!s}, "
            f"expected message containing {expected_message!r}",
        )
        return False
    report_fail(name, "expected an exception, but no exception was raised")
    return False


# =========================================================
# SCHEDULE HELPERS
# =========================================================

def get_scheduled_dates(month=TEST_MONTH, working_weekdays=DEFAULT_WORKING_WEEKDAYS):
    """
    Return all scheduled working dates for the given month as date objects,
    in ascending order, based on the working_weekdays string.
    """
    year, month_num = map(int, month.split("-"))
    days_in_month   = cal_mod.monthrange(year, month_num)[1]
    weekday_set     = {int(d.strip()) for d in working_weekdays.split(",") if d.strip()}
    return [
        date(year, month_num, d)
        for d in range(1, days_in_month + 1)
        if date(year, month_num, d).weekday() in weekday_set
    ]


# =========================================================
# DATABASE / TEST DATA HELPERS
# =========================================================

def create_test_employee(
    suffix,
    monthly_salary=10000,
    grace_holidays=0,
    daily_hours=8,
    overtime_enabled=0,
    overtime_rate=1.5,
    salary_type="monthly",
    working_weekdays=DEFAULT_WORKING_WEEKDAYS,
):
    """
    Create an isolated test employee.

    working_weekdays controls how many scheduled days the salary engine sees.
    Default is Mon-Sat = 27 days in July 2026.
    """
    name = f"{TEST_PREFIX}{suffix}"

    add_employee(
        name=name,
        role="salary-test",
        phone="0000000000",
        address="TEST ONLY",
        monthly_salary=monthly_salary,
        salary_type=salary_type,
        daily_hours=daily_hours,
        expected_check_in="08:00:00",
        expected_check_out="16:00:00",
        late_grace_minutes=0,
        overtime_enabled=overtime_enabled,
        overtime_rate=overtime_rate,
        working_days=26,          # legacy field, not used by salary engine
        grace_holidays=grace_holidays,
        working_weekdays=working_weekdays,
    )

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT employee_id FROM employees
            WHERE name = ?
            ORDER BY employee_id DESC LIMIT 1
            """,
            (name,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise RuntimeError(f"Could not locate newly created test employee: {name}")

    employee_id = row[0]
    created_employee_ids.append(employee_id)
    return employee_id


def insert_attendance(
    employee_id,
    target_date,
    worked_minutes,
    overtime_minutes=0,
    check_in_time="08:00:00",
    check_out_time="16:00:00",
):
    """
    Insert a processed attendance record for a specific date.
    No schedule check — caller decides which dates are valid.
    """
    worked_hours = round(worked_minutes / 60.0, 4)

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO attendance (
                employee_id, date,
                check_in, check_out,
                check_in_source, check_out_source,
                worked_hours, worked_minutes,
                late_minutes, overtime_minutes, locked
            ) VALUES (?, ?, ?, ?, 'test', 'test', ?, ?, 0, ?, 0)
            """,
            (
                employee_id, target_date,
                check_in_time, check_out_time,
                worked_hours, int(worked_minutes),
                int(overtime_minutes),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_full_days(
    employee_id,
    count,
    month=TEST_MONTH,
    working_weekdays=DEFAULT_WORKING_WEEKDAYS,
    check_in_time="08:00:00",
    check_out_time="16:00:00",
):
    """
    Insert `count` full-day (480 min) records on the FIRST `count` SCHEDULED
    working dates of the month.  Skips Sundays / off-days automatically.
    """
    scheduled = get_scheduled_dates(month, working_weekdays)
    for target_date in scheduled[:count]:
        insert_attendance(
            employee_id,
            target_date.isoformat(),
            480,
            check_in_time=check_in_time,
            check_out_time=check_out_time,
        )


def insert_half_days(
    employee_id,
    count,
    month=TEST_MONTH,
    working_weekdays=DEFAULT_WORKING_WEEKDAYS,
):
    """
    Insert `count` half-day (240 min) records on the FIRST `count` SCHEDULED
    working dates of the month.
    """
    scheduled = get_scheduled_dates(month, working_weekdays)
    for target_date in scheduled[:count]:
        insert_attendance(
            employee_id,
            target_date.isoformat(),
            240,
            check_in_time="08:00:00",
            check_out_time="12:00:00",
        )


def salary_for(employee_id, month=TEST_MONTH, role=None):
    """Generate and immediately retrieve a salary record."""
    generate_salary(employee_id, month, role=role)
    result = get_salary(employee_id, month)
    if result is None:
        raise AssertionError(
            "Salary generation succeeded but no salary record was returned"
        )
    return result


# =========================================================
# CLEANUP
# =========================================================

def cleanup():
    """Remove only records created by this test runner."""
    conn = get_connection()
    try:
        if created_employee_ids:
            placeholders = ",".join("?" for _ in created_employee_ids)
            params = tuple(created_employee_ids)
            for table in ("attendance", "salary_cal", "employee_docs", "employees"):
                conn.execute(
                    f"DELETE FROM {table} WHERE employee_id IN ({placeholders})",
                    params,
                )

        # Defensive cleanup for interrupted / previous runs.
        for table in ("attendance", "salary_cal", "employee_docs"):
            conn.execute(
                f"""
                DELETE FROM {table}
                WHERE employee_id IN (
                    SELECT employee_id FROM employees WHERE name LIKE ?
                )
                """,
                (f"{TEST_PREFIX}%",),
            )
        conn.execute(
            "DELETE FROM employees WHERE name LIKE ?",
            (f"{TEST_PREFIX}%",),
        )
        conn.commit()
    finally:
        conn.close()


# =========================================================
# ATTENDANCE METRIC TESTS
# =========================================================

def test_attendance_metrics():

    print("\n=========================================================")
    print("ATTENDANCE METRIC EDGE CASES")
    print("=========================================================")

    cases = [
        ("8h same-day",    "08:00:00", "16:00:00", 480),
        ("4h same-day",    "08:00:00", "12:00:00", 240),
        ("30m same-day",   "08:00:00", "08:30:00",  30),
        ("zero duration",  "08:00:00", "08:00:00",   0),
        ("2h overnight",   "23:00:00", "01:00:00", 120),
    ]

    for label, ci, co, expected_minutes in cases:
        metrics = calculate_attendance_metrics(
            ci, co,
            expected_check_in="08:00:00",
            expected_check_out="16:00:00",
            late_grace_minutes=0,
            overtime_enabled=False,
        )
        assert_equal(
            f"attendance {label} -> worked minutes",
            metrics["worked_minutes"],
            expected_minutes,
        )

    # Late calculation
    metrics = calculate_attendance_metrics(
        "08:15:00", "16:00:00",
        expected_check_in="08:00:00",
        expected_check_out="16:00:00",
        late_grace_minutes=10,
        overtime_enabled=False,
    )
    assert_equal("15m late with 10m grace -> 5m late", metrics["late_minutes"], 5)

    # Overtime detection
    metrics = calculate_attendance_metrics(
        "08:00:00", "18:00:00",
        expected_check_in="08:00:00",
        expected_check_out="16:00:00",
        late_grace_minutes=0,
        overtime_enabled=True,
    )
    assert_equal(
        "10h worked on 8h shift -> 120m overtime",
        metrics["overtime_minutes"],
        120,
    )


# =========================================================
# HALF-DAY / FULL-DAY UNIT TESTS (no DB needed)
# =========================================================

def test_half_full_day_unit():
    """
    Unit-test evaluate_day_attendance directly — no employee/DB required.
    Verifies the core half-day / full-day classification logic.
    """

    print("\n=========================================================")
    print("HALF-DAY / FULL-DAY UNIT TESTS")
    print("=========================================================")

    from backend.services.salary import evaluate_day_attendance

    daily_mins = 480  # 8h shift

    cases = [
        # (label, worked_mins, check_in, check_out, exp_in, grace, expected_credit, expected_status)
        ("8h worked",                  480, "08:00:00", "16:00:00", "08:00:00",  0, "1.0", "Full Day"),
        ("4h worked",                  240, "08:00:00", "12:00:00", "08:00:00",  0, "0.5", "Half Day"),
        ("3h59m (< 50%) -> Absent",    239, "08:00:00", "11:59:00", "08:00:00",  0, "0.0", "Absent"),
        ("7h45m + 15m grace -> Full",  465, "08:15:00", "16:00:00", "08:00:00", 15, "1.0", "Full Day"),
        ("7h44m + 15m grace -> Half",  464, "08:16:00", "16:00:00", "08:00:00", 15, "0.5", "Half Day"),
        ("10h OT -> Full Day",         600, "08:00:00", "18:00:00", "08:00:00",  0, "1.0", "Full Day"),
        ("Only check_in -> Incomplete",None, "08:00:00", None,       "08:00:00",  0, "0.0", "Incomplete"),
        ("Only check_out -> Incomplete",None, None,     "16:00:00", "08:00:00",  0, "0.0", "Incomplete"),
    ]

    for label, wm, ci, co, exp_ci, grace, exp_credit, exp_status in cases:
        credit, status = evaluate_day_attendance(
            worked_minutes=wm,
            daily_minutes=daily_mins,
            check_in=ci,
            check_out=co,
            expected_check_in=exp_ci,
            late_grace_minutes=grace,
        )
        assert_equal(f"[credit] {label}", str(credit), exp_credit)
        assert_equal(f"[status] {label}", status,      exp_status)


# =========================================================
# SALARY BASIC TESTS
# =========================================================

def test_salary_basics():
    """
    July 2026 = 31 calendar days, 27 Mon-Sat working days.
    Salary formula (monthly type):
        daily_rate = monthly_salary / 31
        deduction  = daily_rate * deducted_absence_days
        total      = monthly_salary - deduction
    """

    print("\n=========================================================")
    print("SALARY BASIC EDGE CASES")
    print("=========================================================")

    ms = 10000  # monthly salary for most tests

    # ------------------------------------------------------------------
    # Zero attendance — 27 absences, 0 grace
    # ------------------------------------------------------------------
    employee_id = create_test_employee("ZERO_ATTENDANCE")
    result = salary_for(employee_id)

    expected = _expected_salary(ms, WORKING_DAYS_IN_MONTH, 0)
    assert_close(
        "zero attendance -> salary (all 27 days absent)",
        result["total_salary"],
        expected,
    )
    assert_equal("zero attendance -> paid minutes 0", result["paid_minutes"], 0.0)

    # ------------------------------------------------------------------
    # One full day — 26 absences
    # ------------------------------------------------------------------
    employee_id = create_test_employee("ONE_FULL_DAY")
    insert_full_days(employee_id, 1)
    result = salary_for(employee_id)

    assert_equal("1 full day -> worked 480m", result["actual_worked_minutes"], 480)
    assert_equal("1 full day -> paid 480m",   result["paid_minutes"],          480.0)
    assert_equal("1 full day -> full_days=1", result["full_days"],             1)
    assert_equal("1 full day -> half_days=0", result["half_days"],             0)
    expected = _expected_salary(ms, 26, 0)
    assert_close("1 full day -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # Five full days — 22 absences
    # ------------------------------------------------------------------
    employee_id = create_test_employee("FIVE_FULL_DAYS")
    insert_full_days(employee_id, 5)
    result = salary_for(employee_id)

    assert_equal("5 full days -> worked 2400m", result["actual_worked_minutes"], 2400)
    assert_equal("5 full days -> full_days=5",  result["full_days"],             5)
    expected = _expected_salary(ms, 22, 0)
    assert_close("5 full days -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # Full attendance — 27 days, 0 absences -> full salary
    # ------------------------------------------------------------------
    employee_id = create_test_employee("FULL_ATTENDANCE")
    insert_full_days(employee_id, 27)
    result = salary_for(employee_id)

    assert_equal("27 full days -> worked 12960m", result["actual_worked_minutes"], 27 * 480)
    assert_equal("27 full days -> full_days=27",  result["full_days"],             27)
    assert_equal("27 full days -> half_days=0",   result["half_days"],             0)
    assert_equal("27 full days -> bonus awarded", result["bonus_amount"],          1000.0)
    assert_close("27 full days -> salary = 10000 + 1000 bonus", result["total_salary"], ms + 1000.0)

    # hourly_rate = monthly_salary / (days_in_month * daily_hours)
    # = 10000 / (31 * 8) = 40.32
    expected_hr = round(ms / (DAYS_IN_TEST_MONTH * 8), 2)
    assert_close("full attendance -> hourly rate", result["hourly_rate"], expected_hr)


# =========================================================
# WORKING-WEEKDAY SCHEDULE BOUNDARY TESTS
# =========================================================

def test_working_schedule_boundaries():
    """
    Verify salary engine handles different working_weekdays configurations:
      - Sparse   : only Fridays (5 days in July 2026)
      - Standard : Mon-Sat    (27 days in July 2026)
      - Full week: Mon-Sun    (31 days in July 2026)
    """

    print("\n=========================================================")
    print("WORKING-WEEKDAY SCHEDULE BOUNDARY TESTS")
    print("=========================================================")

    # ------------------------------------------------------------------
    # Sparse: only Fridays (weekday 4)
    # July 2026 Fridays: 3, 10, 17, 24, 31  -> 5 days
    # ------------------------------------------------------------------
    FRIDAYS_ONLY = "4"
    FRI_DAYS     = 5

    employee_id = create_test_employee(
        "SCHEDULE_FRI_ONLY",
        monthly_salary=5000,
        working_weekdays=FRIDAYS_ONLY,
    )
    insert_full_days(employee_id, FRI_DAYS, working_weekdays=FRIDAYS_ONLY)
    result = salary_for(employee_id)

    assert_equal(
        "Fri-only: expected_monthly_minutes = 2400",
        result["expected_monthly_minutes"],
        FRI_DAYS * 8 * 60,
    )
    assert_equal(
        "Fri-only: actual_worked_minutes = 2400",
        result["actual_worked_minutes"],
        FRI_DAYS * 8 * 60,
    )
    assert_close(
        "Fri-only: full attendance -> salary 5000 + 1000 bonus",
        result["total_salary"],
        5000.0 + 1000.0,
    )

    # ------------------------------------------------------------------
    # Standard: Mon-Sat (default) — 27 days
    # ------------------------------------------------------------------
    employee_id = create_test_employee(
        "SCHEDULE_MON_SAT",
        monthly_salary=27000,
    )
    insert_full_days(employee_id, 27)
    result = salary_for(employee_id)

    assert_equal(
        "Mon-Sat: expected_monthly_minutes = 12960",
        result["expected_monthly_minutes"],
        27 * 8 * 60,
    )
    assert_close("Mon-Sat: full attendance -> salary 27000 + 1000 bonus", result["total_salary"], 27000.0 + 1000.0)

    # ------------------------------------------------------------------
    # Full week: Mon-Sun — 31 days in July 2026
    # ------------------------------------------------------------------
    ALL_DAYS    = "0,1,2,3,4,5,6"
    FULL_DAYS   = 31

    employee_id = create_test_employee(
        "SCHEDULE_MON_SUN",
        monthly_salary=31000,
        working_weekdays=ALL_DAYS,
    )
    insert_full_days(employee_id, FULL_DAYS, working_weekdays=ALL_DAYS)
    result = salary_for(employee_id)

    assert_equal(
        "Mon-Sun: expected_monthly_minutes = 14880",
        result["expected_monthly_minutes"],
        FULL_DAYS * 8 * 60,
    )
    assert_close("Mon-Sun: full attendance -> salary 31000 + 1000 bonus", result["total_salary"], 31000.0 + 1000.0)
    expected_hr = round(31000 / (FULL_DAYS * 8), 2)
    assert_close("Mon-Sun: hourly rate", result["hourly_rate"], expected_hr)


# =========================================================
# HALF-DAY + GRACE HOLIDAY SALARY TESTS
# =========================================================

def test_half_days_and_grace():
    """
    Half-day = 240 min worked (50 % of 8h).
    Each half-day contributes 0.5 day credit.
    Absence = scheduled_days - worked_day_credits.
    Grace holidays reduce deductible absences.
    """

    print("\n=========================================================")
    print("HALF-DAY + GRACE HOLIDAY EDGE CASES")
    print("=========================================================")

    ms = 10000  # monthly salary
    WD = WORKING_DAYS_IN_MONTH  # 27

    # ------------------------------------------------------------------
    # One half-day: 26.5 absences
    # ------------------------------------------------------------------
    employee_id = create_test_employee("ONE_HALF_DAY")
    insert_half_days(employee_id, 1)
    result = salary_for(employee_id)

    assert_equal("1 half-day -> worked 240m",   result["actual_worked_minutes"], 240)
    assert_equal("1 half-day -> half_days=1",   result["half_days"],             1)
    assert_equal("1 half-day -> full_days=0",   result["full_days"],             0)
    assert_close("1 half-day -> absence=26.5",  result["absence_days"],          26.5)
    expected = _expected_salary(ms, 26.5, 0)
    assert_close("1 half-day -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # Two half-days = 1 day credit: 26 absences
    # ------------------------------------------------------------------
    employee_id = create_test_employee("TWO_HALF_DAYS")
    insert_half_days(employee_id, 2)
    result = salary_for(employee_id)

    assert_equal("2 half-days -> worked 480m",  result["actual_worked_minutes"], 480)
    assert_equal("2 half-days -> half_days=2",  result["half_days"],             2)
    assert_close("2 half-days -> absence=26.0", result["absence_days"],          26.0)
    expected = _expected_salary(ms, 26.0, 0)
    assert_close("2 half-days -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # Three half-days = 1.5 day credit: 25.5 absences
    # ------------------------------------------------------------------
    employee_id = create_test_employee("THREE_HALF_DAYS")
    insert_half_days(employee_id, 3)
    result = salary_for(employee_id)

    assert_equal("3 half-days -> worked 720m",  result["actual_worked_minutes"], 720)
    assert_close("3 half-days -> absence=25.5", result["absence_days"],          25.5)
    expected = _expected_salary(ms, 25.5, 0)
    assert_close("3 half-days -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # 1 full + 1 half = 1.5 day credit: 25.5 absences
    # ------------------------------------------------------------------
    employee_id = create_test_employee("FULL_PLUS_HALF")
    insert_full_days(employee_id, 1)
    scheduled = get_scheduled_dates()
    insert_attendance(employee_id, scheduled[1].isoformat(), 240,
                      check_in_time="08:00:00", check_out_time="12:00:00")
    result = salary_for(employee_id)

    assert_equal("1 full + 1 half -> worked 720m",  result["actual_worked_minutes"], 720)
    assert_equal("1 full + 1 half -> full_days=1",  result["full_days"],             1)
    assert_equal("1 full + 1 half -> half_days=1",  result["half_days"],             1)
    assert_close("1 full + 1 half -> absence=25.5", result["absence_days"],          25.5)
    expected = _expected_salary(ms, 25.5, 0)
    assert_close("1 full + 1 half -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # 26 full days + 1 half = 26.5 day credit -> absence = 0.5
    # ------------------------------------------------------------------
    employee_id = create_test_employee("TWENTY_SIX_AND_HALF")
    insert_full_days(employee_id, 26)
    # Insert half-day on the 27th scheduled date
    scheduled = get_scheduled_dates()
    insert_attendance(employee_id, scheduled[26].isoformat(), 240,
                      check_in_time="08:00:00", check_out_time="12:00:00")
    result = salary_for(employee_id)

    assert_equal("26 full + 1 half -> worked 12720m", result["actual_worked_minutes"], 26*480 + 240)
    assert_equal("26 full + 1 half -> full_days=26",  result["full_days"],             26)
    assert_equal("26 full + 1 half -> half_days=1",   result["half_days"],             1)
    assert_close("26 full + 1 half -> absence=0.5",   result["absence_days"],          0.5)
    expected = _expected_salary(ms, 0.5, 0)
    assert_close("26 full + 1 half -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # Grace holidays = 0: 25 worked + 2 absent -> deducted 2
    # ------------------------------------------------------------------
    employee_id = create_test_employee("GRACE_ZERO", grace_holidays=0)
    insert_full_days(employee_id, 25)
    result = salary_for(employee_id)

    assert_close("25 worked + 2 absent + 0 grace -> deducted 2", result["deducted_holidays"], 2.0)
    expected = _expected_salary(ms, 2.0, 0)
    assert_close("25 worked + 2 absent + 0 grace -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # Two grace holidays, zero attendance
    # ------------------------------------------------------------------
    employee_id = create_test_employee("GRACE_ZERO_ATTENDANCE", grace_holidays=2)
    result = salary_for(employee_id)

    assert_close("2 grace + 0 attendance -> grace_used=2",   result["grace_holidays_used"], 2.0)
    assert_close("2 grace + 0 attendance -> deducted=25",    result["deducted_holidays"],   25.0)
    expected = _expected_salary(ms, 27, 2)
    assert_close("2 grace + 0 attendance -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # 25 worked + 2 absent + 2 grace -> no deduction
    # ------------------------------------------------------------------
    employee_id = create_test_employee("GRACE_TWO_ABSENCES", grace_holidays=2)
    insert_full_days(employee_id, 25)
    result = salary_for(employee_id)

    assert_close("25 worked + 2 absent + 2 grace -> grace_used=2", result["grace_holidays_used"], 2.0)
    assert_close("25 worked + 2 absent + 2 grace -> deducted=0",   result["deducted_holidays"],   0.0)
    assert_close("25 worked + 2 absent + 2 grace -> full salary",  result["total_salary"],        ms)

    # ------------------------------------------------------------------
    # 24 worked + 3 absent + 2 grace -> deducted 1
    # ------------------------------------------------------------------
    employee_id = create_test_employee("GRACE_THREE_ABSENCES", grace_holidays=2)
    insert_full_days(employee_id, 24)
    result = salary_for(employee_id)

    assert_close("24 worked + 3 absent + 2 grace -> grace_used=2", result["grace_holidays_used"], 2.0)
    assert_close("24 worked + 3 absent + 2 grace -> deducted=1",   result["deducted_holidays"],   1.0)
    expected = _expected_salary(ms, 1.0, 0)
    assert_close("24 worked + 3 absent + 2 grace -> salary", result["total_salary"], expected)

    # ------------------------------------------------------------------
    # Grace > absence: 25 worked + 2 absent + 5 grace -> grace used only 2
    # ------------------------------------------------------------------
    employee_id = create_test_employee("GRACE_GREATER_THAN_ABSENCE", grace_holidays=5)
    insert_full_days(employee_id, 25)
    result = salary_for(employee_id)

    assert_close("grace 5 with 2 absences -> grace used only 2", result["grace_holidays_used"], 2.0)
    assert_close("grace 5 with 2 absences -> deducted 0",        result["deducted_holidays"],   0.0)
    assert_close("grace 5 with 2 absences -> full salary",       result["total_salary"],        ms)

    # ------------------------------------------------------------------
    # Half-day absence covered by grace
    # 26 full + 1 half -> absence 0.5, grace 1 -> grace used 0.5, deducted 0
    # ------------------------------------------------------------------
    employee_id = create_test_employee("HALF_DAY_WITH_GRACE", grace_holidays=1)
    insert_full_days(employee_id, 26)
    scheduled = get_scheduled_dates()
    insert_attendance(employee_id, scheduled[26].isoformat(), 240,
                      check_in_time="08:00:00", check_out_time="12:00:00")
    result = salary_for(employee_id)

    assert_close("0.5 absence with 1 grace -> absence=0.5",   result["absence_days"],          0.5)
    assert_close("0.5 absence with 1 grace -> grace_used=0.5",result["grace_holidays_used"],   0.5)
    assert_close("0.5 absence with 1 grace -> deducted=0",    result["deducted_holidays"],     0.0)
    assert_close("0.5 absence with 1 grace -> full salary",   result["total_salary"],          ms)

    # ------------------------------------------------------------------
    # Equivalence: 26 full + 1 half  ==  (53 half-days across 27 scheduled days)
    # Both produce 26.5 day credit from 27 scheduled days -> same salary
    # ------------------------------------------------------------------
    employee_a = create_test_employee("EQUIVALENCE_A", monthly_salary=ms)
    insert_full_days(employee_a, 26)
    scheduled = get_scheduled_dates()
    insert_attendance(employee_a, scheduled[26].isoformat(), 240,
                      check_in_time="08:00:00", check_out_time="12:00:00")
    result_a = salary_for(employee_a)

    employee_b = create_test_employee("EQUIVALENCE_B", monthly_salary=ms)
    # 53 half-days on 27 scheduled days (first 27 = whole month, each gets 240 min)
    # But there are only 27 scheduled days, so we insert 27 half-days = 13.5 day credit
    # For true equivalence: insert 53 half-days needs more scheduled days.
    # Instead: insert 27 half-days = 13.5 day credit (different from A's 26.5)
    # Correct equivalence: insert same credit via different means.
    # A has 26.5 credit. For B: 26 full + 1 half is same as A.
    # Real test: N full-days vs 2N half-days -> same credit, same salary.
    # Use: 13 full days vs 26 half-days -> 13.0 day credit each.
    employee_b2 = create_test_employee("EQUIVALENCE_B2", monthly_salary=ms)
    insert_full_days(employee_b2, 13)
    result_b2_full = salary_for(employee_b2)

    employee_b3 = create_test_employee("EQUIVALENCE_B3", monthly_salary=ms)
    insert_half_days(employee_b3, 26)   # 26 * 0.5 = 13 day credit
    result_b3_half = salary_for(employee_b3)

    assert_equal(
        "13 full-days vs 26 half-days -> same worked minutes",
        result_b2_full["actual_worked_minutes"],
        result_b3_half["actual_worked_minutes"],
    )
    assert_close(
        "13 full-days vs 26 half-days -> same salary",
        result_b2_full["total_salary"],
        result_b3_half["total_salary"],
    )


# =========================================================
# OVERTIME TESTS
# =========================================================

def test_overtime():

    print("\n=========================================================")
    print("OVERTIME TESTS (INFORMATIONAL ONLY)")
    print("=========================================================")

    employee_id = create_test_employee("OVERTIME", overtime_enabled=1, overtime_rate=2.0)

    scheduled = get_scheduled_dates()
    insert_attendance(
        employee_id,
        scheduled[0].isoformat(),
        worked_minutes=480,
        overtime_minutes=120,
        check_in_time="08:00:00",
        check_out_time="16:00:00",
    )

    result = salary_for(employee_id)

    assert_equal("overtime -> 120 informational overtime minutes", result["overtime_minutes"], 120)
    assert_close("overtime pay remains 0",                          result["overtime_pay"],      0.0)

    # 26 absences, 0 grace
    expected = _expected_salary(10000, 26, 0)
    assert_close("overtime: salary based on 1 attended day", result["total_salary"], expected)


# =========================================================
# OVER-ATTENDANCE TESTS
# =========================================================

def test_over_attendance():
    """
    Attending more days than scheduled still caps salary at monthly_salary.
    Extra attendance on unscheduled days (Sundays) increments actual_worked_minutes
    but does not reduce absence_days.
    """

    print("\n=========================================================")
    print("OVER-ATTENDANCE TEST")
    print("=========================================================")

    employee_id = create_test_employee("OVER_ATTENDANCE")

    # Insert all 27 scheduled Mon-Sat days
    insert_full_days(employee_id, 27)

    # Also insert 2 extra days on Sundays (unscheduled)
    # July 2026 Sundays: 5, 12
    insert_attendance(employee_id, "2026-07-05", 480)   # Sunday — off day
    insert_attendance(employee_id, "2026-07-12", 480)   # Sunday — off day

    result = salary_for(employee_id)

    assert_equal(
        "29 total records -> actual_worked_minutes = 29*480",
        result["actual_worked_minutes"],
        29 * 480,
    )
    assert_close(
        "27 scheduled + 2 Sunday extras -> salary capped at 10000 + 1000 bonus",
        result["total_salary"],
        10000.0 + 1000.0,
    )
    assert_close(
        "27 scheduled days -> paid_minutes = 27*480",
        result["paid_minutes"],
        27 * 480.0,
    )


# =========================================================
# SALARY ROUNDING TESTS
# =========================================================

def test_salary_rounding():

    print("\n=========================================================")
    print("SALARY ROUNDING EDGE CASES")
    print("=========================================================")

    # Use a salary that does not divide evenly by 31 (calendar days)
    # 12345 / 31 = 398.2258...  ->  1 absent day deduction = 398.23 (rounded)
    # 26 absent days  -> deduction = 26 * (12345/31) = 10373.87
    # total = 12345 - 10373.87 = 1971.13
    monthly_salary = 12345

    employee_id = create_test_employee(
        "ROUNDING",
        monthly_salary=monthly_salary,
    )
    # Insert 1 scheduled day (26 absences)
    insert_full_days(employee_id, 1)
    result = salary_for(employee_id)

    expected = _expected_salary(monthly_salary, 26, 0)
    assert_close(
        f"{monthly_salary}/31 -> 1 day salary rounded correctly",
        result["total_salary"],
        expected,
    )
    assert_close("rounding -> overtime pay remains 0", result["overtime_pay"], 0.0)


# =========================================================
# VALIDATION TESTS
# =========================================================

def test_validation():

    print("\n=========================================================")
    print("VALIDATION EDGE CASES")
    print("=========================================================")

    employee_id = create_test_employee("INVALID_MONTH_BASE")

    for month in ("2026", "July", "", "2026-13", "2026-00"):
        assert_raises(
            f"invalid month {month!r} rejected",
            lambda m=month: generate_salary(employee_id, m),
        )

    assert_raises(
        "missing employee rejected",
        lambda: generate_salary(999999999, TEST_MONTH),
        "Employee not found",
    )


# =========================================================
# SALARY REGENERATION / LOCK TESTS
# =========================================================



# =========================================================
# ATTENDANCE BONUS SYSTEM TESTS
# =========================================================

def test_bonus_system():
    """
    Verify all criteria for the attendance bonus system:
      1. No holiday taken, not even grace.
      2. No half-days taken.
      3. Proper arrival (check_in <= expected_check_in + late_grace_minutes).
      4. Proper departure (check_out >= expected_check_out or overtimed).
      5. Full shift duration fulfilled on every scheduled day.
    """
    print("\n=========================================================")
    print("ATTENDANCE BONUS SYSTEM TESTS")
    print("=========================================================")

    from backend.services.settings import update_attendance_bonus_amount

    # Ensure bonus is set to 1000.0
    update_attendance_bonus_amount(1000.0)
    scheduled = get_scheduled_dates()  # 27 Mon-Sat days in July 2026

    # ------------------------------------------------------------------
    # Case 1: Perfect attendance (27/27 days, strictly on time) -> Bonus awarded
    # ------------------------------------------------------------------
    emp_perfect = create_test_employee("BONUS_PERFECT")
    insert_full_days(emp_perfect, 27)
    res = salary_for(emp_perfect)

    assert_equal("perfect attendance -> bonus_amount=1000", res["bonus_amount"], 1000.0)
    assert_close("perfect attendance -> total_salary includes bonus", res["total_salary"], 11000.0)

    # ------------------------------------------------------------------
    # Case 2: Overtime departure (stayed until 18:00 instead of 16:00) -> Bonus awarded
    # ------------------------------------------------------------------
    emp_ot = create_test_employee("BONUS_OVERTIME", overtime_enabled=1)
    for target in scheduled:
        insert_attendance(
            emp_ot,
            target.isoformat(),
            worked_minutes=600,
            overtime_minutes=120,
            check_in_time="08:00:00",
            check_out_time="18:00:00",
        )
    res = salary_for(emp_ot)

    assert_equal("overtime every day -> bonus_amount=1000", res["bonus_amount"], 1000.0)
    assert_close("overtime every day -> total_salary includes bonus", res["total_salary"], 11000.0)

    # ------------------------------------------------------------------
    # Case 3: Arrival within late grace window (arrived 08:08 with 10m grace) -> Bonus awarded
    # ------------------------------------------------------------------
    # Create employee with 10 min late grace
    add_employee(
        name=f"{TEST_PREFIX}BONUS_GRACE_ARRIVAL",
        role="salary-test",
        phone="0000000000",
        address="TEST ONLY",
        monthly_salary=10000,
        salary_type="monthly",
        daily_hours=8,
        expected_check_in="08:00:00",
        expected_check_out="16:00:00",
        late_grace_minutes=10,
        working_weekdays=DEFAULT_WORKING_WEEKDAYS,
    )
    conn = get_connection()
    row = conn.execute("SELECT employee_id FROM employees WHERE name = ?", (f"{TEST_PREFIX}BONUS_GRACE_ARRIVAL",)).fetchone()
    conn.close()
    emp_grace_in = row[0]
    created_employee_ids.append(emp_grace_in)

    for target in scheduled:
        insert_attendance(
            emp_grace_in,
            target.isoformat(),
            worked_minutes=480,
            check_in_time="08:08:00",  # within 10m grace
            check_out_time="16:08:00",
        )
    res = salary_for(emp_grace_in)

    assert_equal("arrival within grace window -> bonus awarded", res["bonus_amount"], 1000.0)

    # ------------------------------------------------------------------
    # Case 4: Late arrival beyond grace window on 1 day (08:20 vs 08:10 max) -> NO bonus
    # ------------------------------------------------------------------
    emp_late = create_test_employee("BONUS_LATE_DAY")
    # 26 days on time, 1 day late
    for target in scheduled[:26]:
        insert_attendance(emp_late, target.isoformat(), 480, check_in_time="08:00:00", check_out_time="16:00:00")
    # Day 27: arrived at 08:20 (no grace) -> late coming
    insert_attendance(emp_late, scheduled[26].isoformat(), 460, check_in_time="08:20:00", check_out_time="16:00:00")
    res = salary_for(emp_late)

    assert_equal("late arrival on 1 day -> NO bonus", res["bonus_amount"], 0.0)

    # ------------------------------------------------------------------
    # Case 5: Early exit on 1 day (left at 15:30 vs 16:00) -> NO bonus
    # ------------------------------------------------------------------
    emp_early_exit = create_test_employee("BONUS_EARLY_EXIT")
    for target in scheduled[:26]:
        insert_attendance(emp_early_exit, target.isoformat(), 480, check_in_time="08:00:00", check_out_time="16:00:00")
    # Day 27: left at 15:30 -> early exit
    insert_attendance(emp_early_exit, scheduled[26].isoformat(), 450, check_in_time="08:00:00", check_out_time="15:30:00")
    res = salary_for(emp_early_exit)

    assert_equal("early exit on 1 day -> NO bonus", res["bonus_amount"], 0.0)

    # ------------------------------------------------------------------
    # Case 6: 1 absent day without grace -> NO bonus
    # ------------------------------------------------------------------
    emp_absent = create_test_employee("BONUS_ABSENT_DAY")
    insert_full_days(emp_absent, 26)  # 26 attended, 1 absent
    res = salary_for(emp_absent)

    assert_equal("1 absent day -> NO bonus", res["bonus_amount"], 0.0)

    # ------------------------------------------------------------------
    # Case 7: 1 absent day covered by grace holiday ("not even grace") -> NO bonus
    # ------------------------------------------------------------------
    emp_grace_absent = create_test_employee("BONUS_GRACE_ABSENT", grace_holidays=2)
    insert_full_days(emp_grace_absent, 26)  # 26 attended, 1 absent covered by grace
    res = salary_for(emp_grace_absent)

    assert_close("grace holiday used covers salary deduction", res["deducted_holidays"], 0.0)
    assert_equal("grace holiday used -> NO bonus ('not even grace')", res["bonus_amount"], 0.0)
    assert_close("grace holiday used -> salary is 10000 (no bonus added)", res["total_salary"], 10000.0)

    # ------------------------------------------------------------------
    # Case 8: 1 half-day taken (4h instead of 8h) -> NO bonus
    # ------------------------------------------------------------------
    emp_half = create_test_employee("BONUS_HALF_DAY")
    insert_full_days(emp_half, 26)
    insert_attendance(emp_half, scheduled[26].isoformat(), 240, check_in_time="08:00:00", check_out_time="12:00:00")
    res = salary_for(emp_half)

    assert_equal("1 half-day taken -> half_days=1", res["half_days"], 1)
    assert_equal("1 half-day taken -> NO bonus", res["bonus_amount"], 0.0)

    # ------------------------------------------------------------------
    # Case 9: Custom bonus amount configuration (e.g. INR 2,500)
    # ------------------------------------------------------------------
    update_attendance_bonus_amount(2500.0)
    emp_custom_bonus = create_test_employee("BONUS_CUSTOM_AMOUNT")
    insert_full_days(emp_custom_bonus, 27)
    res = salary_for(emp_custom_bonus)

    assert_equal("custom bonus amount INR 2500 awarded", res["bonus_amount"], 2500.0)
    assert_close("total_salary includes INR 2500 bonus", res["total_salary"], 12500.0)

    # Reset back to default 1000.0
    update_attendance_bonus_amount(1000.0)

def test_regeneration_and_locking():

    print("\n=========================================================")
    print("SALARY REGENERATION + LOCKING")
    print("=========================================================")

    employee_id = create_test_employee("REGENERATION")
    insert_full_days(employee_id, 5)   # 5 days attended, 22 absent

    # First generation
    first = salary_for(employee_id)
    assert_equal("first salary generation locks completed month", first["locked"], 1)

    # Normal Admin cannot regenerate locked salary
    assert_raises(
        "locked completed salary cannot regenerate as normal role",
        lambda: generate_salary(employee_id, TEST_MONTH, role="admin"),
        "Only Head Developer can regenerate",
    )

    # Head can regenerate
    second = salary_for(employee_id, role="head")
    expected = _expected_salary(10000, 22, 0)
    assert_close("Head can regenerate locked salary", second["total_salary"], expected)

    # Regeneration must UPDATE, not duplicate
    conn = get_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM salary_cal WHERE employee_id = ? AND month = ?",
            (employee_id, TEST_MONTH),
        ).fetchone()[0]
    finally:
        conn.close()

    assert_equal("regeneration keeps exactly one salary record", count, 1)


# =========================================================
# MAIN
# =========================================================

def main():
    print("=========================================================")
    print("SALARY + ATTENDANCE EDGE-CASE TESTER")
    print("=========================================================")
    print(f"Test month                : {TEST_MONTH}")
    print(f"Calendar days in month    : {DAYS_IN_TEST_MONTH}")
    print(f"Scheduled working days    : {WORKING_DAYS_IN_MONTH} (Mon-Sat)")
    print(f"Default working_weekdays  : {DEFAULT_WORKING_WEEKDAYS}")
    print("Salary deduction formula  : monthly_salary / calendar_days * absent_days")
    print("Half-day threshold        : 50% of daily_hours")
    print("Full-day threshold        : 100% of daily_hours (minus late_grace)")
    print("Overtime policy           : informational only, pay = 0")
    print(f"Test data prefix          : {TEST_PREFIX}")

    try:
        employee_db()
        from backend.services.settings import update_attendance_bonus_amount
        update_attendance_bonus_amount(1000.0)

        test_attendance_metrics()
        test_half_full_day_unit()
        test_salary_basics()
        test_working_schedule_boundaries()
        test_half_days_and_grace()
        test_overtime()
        test_over_attendance()
        test_salary_rounding()
        test_validation()
        test_bonus_system()
        test_regeneration_and_locking()

    except Exception as exc:
        report_fail("TEST RUNNER CRASH", f"{type(exc).__name__}: {exc}")
        traceback.print_exc()

    finally:
        print("\n=========================================================")
        print("CLEANUP")
        print("=========================================================")
        try:
            cleanup()
            print("PASS  Test records cleaned up")
        except Exception as exc:
            print(f"FAIL  Cleanup failed: {type(exc).__name__}: {exc}")

    print("\n=========================================================")
    print("FINAL RESULT")
    print("=========================================================")
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print("=========================================================")

    if failed == 0:
        print("\nALL TESTS PASSED")
        return 0

    print("\nTESTS FAILED - review failures above before shipping.")
    return 1


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    raise SystemExit(main())
