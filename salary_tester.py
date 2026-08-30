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
    Full day = configured daily hours
    Half day = half of configured daily hours
    Overtime = informational only
    Overtime pay = ₹0
    Salary is based on the employee's configured working days
    Grace holidays reduce deductible absence
    Salary cannot exceed the configured monthly salary
    Completed-month salary becomes locked
    Only Head can regenerate a locked completed salary
"""

import os
import sys
import traceback
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

# July 2026 is completed, which makes salary locking deterministic.
TEST_MONTH = "2026-07"


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

    report_fail(
        name,
        f"expected {expected!r}, got {actual!r}",
    )

    return False


def assert_close(name, actual, expected, tolerance=0.01):
    try:
        ok = abs(float(actual) - float(expected)) <= tolerance

    except (TypeError, ValueError):
        ok = False

    if ok:
        report_pass(name)
        return True

    report_fail(
        name,
        f"expected {expected}, got {actual}",
    )

    return False


def assert_raises(name, func, expected_message=None):
    try:
        func()

    except Exception as exc:

        if (
            expected_message is None
            or expected_message in str(exc)
        ):
            report_pass(name)
            return True

        report_fail(
            name,
            (
                f"raised {type(exc).__name__}: {exc!s}, "
                f"expected message containing "
                f"{expected_message!r}"
            ),
        )

        return False

    report_fail(
        name,
        "expected an exception, but no exception was raised",
    )

    return False


# =========================================================
# DATABASE / TEST DATA HELPERS
# =========================================================

def create_test_employee(
    suffix,
    monthly_salary=10000,
    working_days=10,
    grace_holidays=0,
    daily_hours=8,
    overtime_enabled=0,
    overtime_rate=1.5,
    salary_type="monthly",
):
    """
    Create an isolated employee for this test run.

    The production add_employee() function is used so that employee
    creation itself remains representative of the real application.
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
        working_days=working_days,
        grace_holidays=grace_holidays,
    )

    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT employee_id
            FROM employees
            WHERE name = ?
            ORDER BY employee_id DESC
            LIMIT 1
            """,
            (name,),
        ).fetchone()

    finally:
        conn.close()

    if not row:
        raise RuntimeError(
            f"Could not locate newly created test employee: {name}"
        )

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
    Insert a processed attendance record.

    This represents the result produced after Secureye punches have
    been processed into an attendance record.

    No lunch/break deduction is applied.
    """

    worked_hours = round(
        worked_minutes / 60.0,
        4,
    )

    conn = get_connection()

    try:
        conn.execute(
            """
            INSERT INTO attendance (
                employee_id,
                date,
                check_in,
                check_out,
                check_in_source,
                check_out_source,
                worked_hours,
                worked_minutes,
                late_minutes,
                overtime_minutes,
                locked
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                'test',
                'test',
                ?,
                ?,
                0,
                ?,
                0
            )
            """,
            (
                employee_id,
                target_date,
                check_in_time,
                check_out_time,
                worked_hours,
                int(worked_minutes),
                int(overtime_minutes),
            ),
        )

        conn.commit()

    finally:
        conn.close()


def insert_full_days(
    employee_id,
    count,
    start_day=1,
    month=TEST_MONTH,
):
    """
    Insert `count` full 8-hour attendance days.
    """

    year, month_number = map(
        int,
        month.split("-"),
    )

    for offset in range(count):

        day_number = start_day + offset

        target = date(
            year,
            month_number,
            day_number,
        ).isoformat()

        insert_attendance(
            employee_id,
            target,
            480,
        )


def salary_for(
    employee_id,
    month=TEST_MONTH,
    role=None,
):
    """
    Generate and immediately retrieve a salary record.
    """

    generate_salary(
        employee_id,
        month,
        role=role,
    )

    result = get_salary(
        employee_id,
        month,
    )

    if result is None:
        raise AssertionError(
            "Salary generation succeeded but no salary record "
            "was returned"
        )

    return result


def update_employee_working_days(
    employee_id,
    working_days,
):
    """
    Directly alter working_days after employee creation.

    This is intentionally used only for validation testing.

    Why?

    add_employee() may correctly reject invalid employee settings before
    the salary engine ever sees them. We specifically want to test that
    generate_salary() also protects itself against invalid values.
    """

    conn = get_connection()

    try:
        conn.execute(
            """
            UPDATE employees
            SET working_days = ?
            WHERE employee_id = ?
            """,
            (
                working_days,
                employee_id,
            ),
        )

        conn.commit()

    finally:
        conn.close()


# =========================================================
# CLEANUP
# =========================================================

def cleanup():
    """
    Remove only records created by this test runner.
    """

    conn = get_connection()

    try:

        if created_employee_ids:

            placeholders = ",".join(
                "?" for _ in created_employee_ids
            )

            params = tuple(created_employee_ids)

            conn.execute(
                f"""
                DELETE FROM attendance
                WHERE employee_id IN ({placeholders})
                """,
                params,
            )

            conn.execute(
                f"""
                DELETE FROM salary_cal
                WHERE employee_id IN ({placeholders})
                """,
                params,
            )

            conn.execute(
                f"""
                DELETE FROM employee_docs
                WHERE employee_id IN ({placeholders})
                """,
                params,
            )

            conn.execute(
                f"""
                DELETE FROM employees
                WHERE employee_id IN ({placeholders})
                """,
                params,
            )

        # Defensive cleanup for interrupted/previous runs.

        conn.execute(
            """
            DELETE FROM attendance
            WHERE employee_id IN (
                SELECT employee_id
                FROM employees
                WHERE name LIKE ?
            )
            """,
            (f"{TEST_PREFIX}%",),
        )

        conn.execute(
            """
            DELETE FROM salary_cal
            WHERE employee_id IN (
                SELECT employee_id
                FROM employees
                WHERE name LIKE ?
            )
            """,
            (f"{TEST_PREFIX}%",),
        )

        conn.execute(
            """
            DELETE FROM employee_docs
            WHERE employee_id IN (
                SELECT employee_id
                FROM employees
                WHERE name LIKE ?
            )
            """,
            (f"{TEST_PREFIX}%",),
        )

        conn.execute(
            """
            DELETE FROM employees
            WHERE name LIKE ?
            """,
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
        (
            "8h same-day",
            "08:00:00",
            "16:00:00",
            480,
        ),
        (
            "4h same-day",
            "08:00:00",
            "12:00:00",
            240,
        ),
        (
            "30m same-day",
            "08:00:00",
            "08:30:00",
            30,
        ),
        (
            "zero duration",
            "08:00:00",
            "08:00:00",
            0,
        ),
        (
            "2h overnight",
            "23:00:00",
            "01:00:00",
            120,
        ),
    ]

    for (
        label,
        check_in_time,
        check_out_time,
        expected_minutes,
    ) in cases:

        metrics = calculate_attendance_metrics(
            check_in_time,
            check_out_time,
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

    # -----------------------------------------------------
    # Late calculation
    # -----------------------------------------------------

    metrics = calculate_attendance_metrics(
        "08:15:00",
        "16:00:00",
        expected_check_in="08:00:00",
        expected_check_out="16:00:00",
        late_grace_minutes=10,
        overtime_enabled=False,
    )

    assert_equal(
        "15m late with 10m grace -> 5m late",
        metrics["late_minutes"],
        5,
    )

    # -----------------------------------------------------
    # Overtime detection
    # -----------------------------------------------------

    metrics = calculate_attendance_metrics(
        "08:00:00",
        "18:00:00",
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
# SALARY BASIC TESTS
# =========================================================

def test_salary_basics():

    print("\n=========================================================")
    print("SALARY BASIC EDGE CASES")
    print("=========================================================")

    # -----------------------------------------------------
    # Zero attendance
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "ZERO_ATTENDANCE"
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "zero attendance -> base salary ₹0",
        result["base_salary"],
        0.0,
    )

    assert_equal(
        "zero attendance -> final salary ₹0",
        result["total_salary"],
        0.0,
    )

    assert_equal(
        "zero attendance -> paid minutes 0",
        result["paid_minutes"],
        0.0,
    )

    # -----------------------------------------------------
    # One full day
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "ONE_FULL_DAY"
    )

    insert_full_days(
        employee_id,
        1,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "1 full day -> worked 480m",
        result["actual_worked_minutes"],
        480,
    )

    assert_equal(
        "1 full day -> paid 480m",
        result["paid_minutes"],
        480.0,
    )

    assert_close(
        "1 full day -> salary ₹1000",
        result["total_salary"],
        1000.0,
    )

    # -----------------------------------------------------
    # Five full days
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "FIVE_FULL_DAYS"
    )

    insert_full_days(
        employee_id,
        5,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "5 full days -> worked 2400m",
        result["actual_worked_minutes"],
        2400,
    )

    assert_close(
        "5 full days -> salary ₹5000",
        result["total_salary"],
        5000.0,
    )

    # -----------------------------------------------------
    # Full attendance
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "FULL_ATTENDANCE"
    )

    insert_full_days(
        employee_id,
        10,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "10 full days -> worked 4800m",
        result["actual_worked_minutes"],
        4800,
    )

    assert_close(
        "10 full days -> salary ₹10000",
        result["total_salary"],
        10000.0,
    )

    assert_close(
        "full attendance -> hourly rate ₹125",
        result["hourly_rate"],
        125.0,
    )


# =========================================================
# WORKING-DAY BOUNDARY TESTS
# =========================================================

def test_working_day_boundaries():

    print("\n=========================================================")
    print("WORKING-DAY BOUNDARY TESTS")
    print("=========================================================")

    # -----------------------------------------------------
    # Minimum valid value = 1
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "WORKING_DAYS_1",
        monthly_salary=1000,
        working_days=1,
        daily_hours=8,
    )

    insert_attendance(
        employee_id,
        "2026-07-01",
        480,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "working_days=1 -> expected minutes 480",
        result["expected_monthly_minutes"],
        480,
    )

    assert_close(
        "working_days=1 -> full attendance salary ₹1000",
        result["total_salary"],
        1000.0,
    )

    # -----------------------------------------------------
    # 30 working days
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "WORKING_DAYS_30",
        monthly_salary=30000,
        working_days=30,
        daily_hours=8,
    )

    insert_full_days(
        employee_id,
        30,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "working_days=30 -> expected minutes 14400",
        result["expected_monthly_minutes"],
        14400,
    )

    assert_equal(
        "working_days=30 -> actual minutes 14400",
        result["actual_worked_minutes"],
        14400,
    )

    assert_close(
        "working_days=30 -> salary ₹30000",
        result["total_salary"],
        30000.0,
    )

    # -----------------------------------------------------
    # Maximum valid value = 31
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "WORKING_DAYS_31",
        monthly_salary=31000,
        working_days=31,
        daily_hours=8,
    )

    insert_full_days(
        employee_id,
        31,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "working_days=31 -> expected minutes 14880",
        result["expected_monthly_minutes"],
        14880,
    )

    assert_equal(
        "working_days=31 -> actual minutes 14880",
        result["actual_worked_minutes"],
        14880,
    )

    assert_close(
        "working_days=31 -> salary ₹31000",
        result["total_salary"],
        31000.0,
    )

    assert_close(
        "working_days=31 -> hourly rate ₹125",
        result["hourly_rate"],
        125.0,
    )


# =========================================================
# HALF-DAY / GRACE HOLIDAY TESTS
# =========================================================

def test_half_days_and_grace():

    print("\n=========================================================")
    print("HALF-DAY + GRACE HOLIDAY EDGE CASES")
    print("=========================================================")

    # -----------------------------------------------------
    # One half-day
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "ONE_HALF_DAY"
    )

    insert_attendance(
        employee_id,
        "2026-07-01",
        240,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "1 half-day -> worked 240m",
        result["actual_worked_minutes"],
        240,
    )

    assert_close(
        "1 half-day -> salary ₹500",
        result["total_salary"],
        500.0,
    )

    # -----------------------------------------------------
    # Two half-days = one full day
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "TWO_HALF_DAYS"
    )

    insert_attendance(
        employee_id,
        "2026-07-01",
        240,
    )

    insert_attendance(
        employee_id,
        "2026-07-02",
        240,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "2 half-days -> worked 480m",
        result["actual_worked_minutes"],
        480,
    )

    assert_close(
        "2 half-days -> salary ₹1000",
        result["total_salary"],
        1000.0,
    )

    # -----------------------------------------------------
    # Three half-days
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "THREE_HALF_DAYS"
    )

    insert_attendance(
        employee_id,
        "2026-07-01",
        240,
    )

    insert_attendance(
        employee_id,
        "2026-07-02",
        240,
    )

    insert_attendance(
        employee_id,
        "2026-07-03",
        240,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "3 half-days -> worked 720m",
        result["actual_worked_minutes"],
        720,
    )

    assert_close(
        "3 half-days -> salary ₹1500",
        result["total_salary"],
        1500.0,
    )

    # -----------------------------------------------------
    # 1 full + 1 half = 1.5 days
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "FULL_PLUS_HALF"
    )

    insert_attendance(
        employee_id,
        "2026-07-01",
        480,
    )

    insert_attendance(
        employee_id,
        "2026-07-02",
        240,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "1 full + 1 half -> worked 720m",
        result["actual_worked_minutes"],
        720,
    )

    assert_close(
        "1 full + 1 half -> salary ₹1500",
        result["total_salary"],
        1500.0,
    )

    # -----------------------------------------------------
    # 9 full days + 1 half day = 9.5 days
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "NINE_AND_HALF_DAYS",
        monthly_salary=10000,
        working_days=10,
        daily_hours=8,
    )

    insert_full_days(
        employee_id,
        9,
    )

    insert_attendance(
        employee_id,
        "2026-07-10",
        240,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "9 full + 1 half -> worked 4560m",
        result["actual_worked_minutes"],
        4560,
    )

    assert_close(
        "9 full + 1 half -> salary ₹9500",
        result["total_salary"],
        9500.0,
    )

    # -----------------------------------------------------
    # 9.5 days means 0.5 absence
    # -----------------------------------------------------

    assert_close(
        "9.5 worked -> absence 0.5",
        result["absence_days"],
        0.5,
    )

    # -----------------------------------------------------
    # Grace holidays = 0
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "GRACE_ZERO",
        grace_holidays=0,
    )

    insert_full_days(
        employee_id,
        8,
    )

    result = salary_for(
        employee_id
    )

    assert_close(
        "8 worked + 2 absent + 0 grace -> deducted 2",
        result["deducted_holidays"],
        2.0,
    )

    assert_close(
        "8 worked + 2 absent + 0 grace -> salary ₹8000",
        result["total_salary"],
        8000.0,
    )

    # -----------------------------------------------------
    # Two grace holidays, zero attendance
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "GRACE_ZERO_ATTENDANCE",
        grace_holidays=2,
    )

    result = salary_for(
        employee_id
    )

    assert_close(
        "2 grace holidays, zero attendance -> grace used 2",
        result["grace_holidays_used"],
        2.0,
    )

    assert_close(
        "2 grace holidays, zero attendance -> deducted 8",
        result["deducted_holidays"],
        8.0,
    )

    assert_close(
        "2 grace holidays, zero attendance -> salary ₹2000",
        result["total_salary"],
        2000.0,
    )

    # -----------------------------------------------------
    # Eight worked + two absent + two grace
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "GRACE_TWO_ABSENCES",
        grace_holidays=2,
    )

    insert_full_days(
        employee_id,
        8,
    )

    result = salary_for(
        employee_id
    )

    assert_close(
        "8 worked + 2 absent + 2 grace -> grace used 2",
        result["grace_holidays_used"],
        2.0,
    )

    assert_close(
        "8 worked + 2 absent + 2 grace -> no deduction",
        result["deducted_holidays"],
        0.0,
    )

    assert_close(
        "8 worked + 2 absent + 2 grace -> salary ₹10000",
        result["total_salary"],
        10000.0,
    )

    # -----------------------------------------------------
    # Seven worked + three absent + two grace
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "GRACE_THREE_ABSENCES",
        grace_holidays=2,
    )

    insert_full_days(
        employee_id,
        7,
    )

    result = salary_for(
        employee_id
    )

    assert_close(
        "7 worked + 3 absent + 2 grace -> grace used 2",
        result["grace_holidays_used"],
        2.0,
    )

    assert_close(
        "7 worked + 3 absent + 2 grace -> deducted 1",
        result["deducted_holidays"],
        1.0,
    )

    assert_close(
        "7 worked + 3 absent + 2 grace -> salary ₹9000",
        result["total_salary"],
        9000.0,
    )

    # -----------------------------------------------------
    # Grace greater than absence
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "GRACE_GREATER_THAN_ABSENCE",
        grace_holidays=5,
    )

    insert_full_days(
        employee_id,
        8,
    )

    result = salary_for(
        employee_id
    )

    assert_close(
        "grace 5 with 2 absences -> grace used only 2",
        result["grace_holidays_used"],
        2.0,
    )

    assert_close(
        "grace 5 with 2 absences -> deducted 0",
        result["deducted_holidays"],
        0.0,
    )

    assert_close(
        "grace 5 with 2 absences -> full salary",
        result["total_salary"],
        10000.0,
    )

    # -----------------------------------------------------
    # Half-day absence covered by grace
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "HALF_DAY_WITH_GRACE",
        grace_holidays=1,
    )

    insert_full_days(
        employee_id,
        9,
    )

    insert_attendance(
        employee_id,
        "2026-07-10",
        240,
    )

    result = salary_for(
        employee_id
    )

    assert_close(
        "0.5 absence with grace -> absence 0.5",
        result["absence_days"],
        0.5,
    )

    assert_close(
        "0.5 absence with grace -> grace used 0.5",
        result["grace_holidays_used"],
        0.5,
    )

    assert_close(
        "0.5 absence with grace -> deducted 0",
        result["deducted_holidays"],
        0.0,
    )

    assert_close(
        "0.5 absence with grace -> full ₹10000 salary",
        result["total_salary"],
        10000.0,
    )

    # -----------------------------------------------------
    # Equivalence:
    #
    # 9 full days + 1 half day
    #
    # MUST equal
    #
    # 19 half days
    # -----------------------------------------------------

    employee_a = create_test_employee(
        "EQUIVALENCE_A",
        monthly_salary=10000,
        working_days=10,
        daily_hours=8,
    )

    insert_full_days(
        employee_a,
        9,
    )

    insert_attendance(
        employee_a,
        "2026-07-10",
        240,
    )

    result_a = salary_for(
        employee_a
    )

    employee_b = create_test_employee(
        "EQUIVALENCE_B",
        monthly_salary=10000,
        working_days=10,
        daily_hours=8,
    )

    for day_number in range(1, 20):

        insert_attendance(
            employee_b,
            f"2026-07-{day_number:02d}",
            240,
        )

    result_b = salary_for(
        employee_b
    )

    assert_equal(
        "9.5 days vs 19 half-days -> same worked minutes",
        result_a["actual_worked_minutes"],
        result_b["actual_worked_minutes"],
    )

    assert_close(
        "9.5 days vs 19 half-days -> same salary",
        result_a["total_salary"],
        result_b["total_salary"],
    )


# =========================================================
# OVERTIME TESTS
# =========================================================

def test_overtime():

    print("\n=========================================================")
    print("OVERTIME TESTS (INFORMATIONAL ONLY)")
    print("=========================================================")

    employee_id = create_test_employee(
        "OVERTIME",
        overtime_enabled=1,
        overtime_rate=2.0,
    )

    # Keep worked time at 8h and attach 120 informational
    # overtime minutes.
    #
    # This isolates the business rule:
    #
    # overtime_minutes = informational
    # overtime_pay     = ₹0

    insert_attendance(
        employee_id,
        "2026-07-01",
        worked_minutes=480,
        overtime_minutes=120,
        check_in_time="08:00:00",
        check_out_time="16:00:00",
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "overtime record -> 120 informational overtime minutes",
        result["overtime_minutes"],
        120,
    )

    assert_close(
        "overtime pay remains ₹0",
        result["overtime_pay"],
        0.0,
    )

    assert_close(
        "informational overtime does not add overtime pay",
        result["total_salary"],
        1000.0,
    )


# =========================================================
# OVER-ATTENDANCE TESTS
# =========================================================

def test_over_attendance():

    print("\n=========================================================")
    print("OVER-ATTENDANCE TEST")
    print("=========================================================")

    employee_id = create_test_employee(
        "OVER_ATTENDANCE"
    )

    # Employee is configured for 10 working days.
    insert_full_days(
        employee_id,
        10,
    )

    # Two additional attended days.
    insert_attendance(
        employee_id,
        "2026-07-11",
        480,
    )

    insert_attendance(
        employee_id,
        "2026-07-12",
        480,
    )

    result = salary_for(
        employee_id
    )

    assert_equal(
        "12 attended days -> actual 5760m",
        result["actual_worked_minutes"],
        5760,
    )

    assert_close(
        "12 attended days -> salary capped at ₹10000",
        result["total_salary"],
        10000.0,
    )

    assert_close(
        "12 attended days -> paid minutes capped at 4800",
        result["paid_minutes"],
        4800.0,
    )


# =========================================================
# SALARY ROUNDING TESTS
# =========================================================

def test_salary_rounding():

    print("\n=========================================================")
    print("SALARY ROUNDING EDGE CASES")
    print("=========================================================")

    employee_id = create_test_employee(
        "ROUNDING",
        monthly_salary=12345,
        working_days=26,
        daily_hours=8,
    )

    insert_attendance(
        employee_id,
        "2026-07-01",
        480,
    )

    result = salary_for(
        employee_id
    )

    expected_daily_salary = (
        12345 / 26
    )

    assert_close(
        "₹12345 / 26 -> one day salary rounded correctly",
        result["total_salary"],
        round(expected_daily_salary, 2),
    )

    assert_close(
        "rounding -> overtime pay remains ₹0",
        result["overtime_pay"],
        0.0,
    )


# =========================================================
# VALIDATION TESTS
# =========================================================

def test_validation():

    print("\n=========================================================")
    print("VALIDATION EDGE CASES")
    print("=========================================================")

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # These tests deliberately modify working_days AFTER
    # employee creation.
    #
    # This ensures we test generate_salary() itself rather
    # than merely testing add_employee() validation.
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "INVALID_WORKING_DAYS_BASE",
        working_days=10,
    )

    for working_days in (
        0,
        -1,
        32,
    ):

        update_employee_working_days(
            employee_id,
            working_days,
        )

        assert_raises(
            f"salary rejects working_days={working_days}",
            lambda eid=employee_id: generate_salary(
                eid,
                TEST_MONTH,
            ),
            "Employee working days must be between 1 and 31",
        )

    # Restore valid value before continuing.
    update_employee_working_days(
        employee_id,
        10,
    )

    # -----------------------------------------------------
    # Invalid month values
    # -----------------------------------------------------

    employee_id = create_test_employee(
        "INVALID_MONTH_BASE"
    )

    for month in (
        "2026",
        "July",
        "",
        "2026-13",
        "2026-00",
    ):

        assert_raises(
            f"invalid month {month!r} rejected",
            lambda m=month: generate_salary(
                employee_id,
                m,
            ),
        )

    # -----------------------------------------------------
    # Missing employee
    # -----------------------------------------------------

    assert_raises(
        "missing employee rejected",
        lambda: generate_salary(
            999999999,
            TEST_MONTH,
        ),
        "Employee not found",
    )


# =========================================================
# SALARY REGENERATION / LOCK TESTS
# =========================================================

def test_regeneration_and_locking():

    print("\n=========================================================")
    print("SALARY REGENERATION + LOCKING")
    print("=========================================================")

    employee_id = create_test_employee(
        "REGENERATION"
    )

    insert_full_days(
        employee_id,
        5,
    )

    # -----------------------------------------------------
    # First generation
    # -----------------------------------------------------

    first = salary_for(
        employee_id
    )

    assert_equal(
        "first salary generation locks completed month",
        first["locked"],
        1,
    )

    # -----------------------------------------------------
    # Normal Admin cannot regenerate locked salary
    # -----------------------------------------------------

    assert_raises(
        "locked completed salary cannot regenerate as normal role",
        lambda: generate_salary(
            employee_id,
            TEST_MONTH,
            role="admin",
        ),
        "Only Head Developer can regenerate",
    )

    # -----------------------------------------------------
    # Head can regenerate
    # -----------------------------------------------------

    second = salary_for(
        employee_id,
        role="head",
    )

    assert_close(
        "Head can regenerate locked salary",
        second["total_salary"],
        5000.0,
    )

    # -----------------------------------------------------
    # Regeneration must UPDATE, not duplicate
    # -----------------------------------------------------

    conn = get_connection()

    try:

        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM salary_cal
            WHERE employee_id = ?
              AND month = ?
            """,
            (
                employee_id,
                TEST_MONTH,
            ),
        ).fetchone()[0]

    finally:
        conn.close()

    assert_equal(
        "regeneration keeps exactly one salary record",
        count,
        1,
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=========================================================")
    print("SALARY + ATTENDANCE EDGE-CASE TESTER")
    print("=========================================================")

    print(f"Test month: {TEST_MONTH}")

    print(
        "Attendance model: "
        "first machine punch = check-in, "
        "last machine punch = check-out"
    )

    print(
        "Break/lunch deduction: NONE"
    )

    print(
        "Overtime policy: informational only, pay = ₹0"
    )

    print(
        "Test data prefix:",
        TEST_PREFIX,
    )

    try:

        # Ensure database/tables are initialized.
        employee_db()

        # -------------------------------------------------
        # Attendance mathematics
        # -------------------------------------------------

        test_attendance_metrics()

        # -------------------------------------------------
        # Salary basics
        # -------------------------------------------------

        test_salary_basics()

        # -------------------------------------------------
        # Working-day boundaries
        # -------------------------------------------------

        test_working_day_boundaries()

        # -------------------------------------------------
        # Half-day + grace logic
        # -------------------------------------------------

        test_half_days_and_grace()

        # -------------------------------------------------
        # Overtime
        # -------------------------------------------------

        test_overtime()

        # -------------------------------------------------
        # Over-attendance
        # -------------------------------------------------

        test_over_attendance()

        # -------------------------------------------------
        # Rounding
        # -------------------------------------------------

        test_salary_rounding()

        # -------------------------------------------------
        # Validation
        # -------------------------------------------------

        test_validation()

        # -------------------------------------------------
        # Locking / regeneration
        # -------------------------------------------------

        test_regeneration_and_locking()

    except Exception as exc:

        report_fail(
            "TEST RUNNER CRASH",
            f"{type(exc).__name__}: {exc}",
        )

        traceback.print_exc()

    finally:

        print("\n=========================================================")
        print("CLEANUP")
        print("=========================================================")

        try:

            cleanup()

            print(
                "PASS  Test records cleaned up"
            )

        except Exception as exc:

            print(
                "FAIL  Cleanup failed: "
                f"{type(exc).__name__}: {exc}"
            )

    print("\n=========================================================")
    print("FINAL RESULT")
    print("=========================================================")

    print(
        f"PASSED: {passed}"
    )

    print(
        f"FAILED: {failed}"
    )

    print("=========================================================")

    if failed == 0:

        print("\nALL TESTS PASSED")

        return 0

    print(
        "\nTESTS FAILED - "
        "DO NOT CHANGE PRODUCTION CODE UNTIL FAILURES ARE REVIEWED"
    )

    return 1


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    raise SystemExit(
        main()
    )