"""
simulate_month_attendance.py
----------------------------
Utility script to automatically populate an employee's monthly attendance
with realistic attendance patterns and edge cases, generate payroll, and
validate that calculations (working days, full/half days, grace leave,
deductions, attendance bonus, and net salary) match exact expectations.

Usage:
    # 1. Run all 7 edge-case scenarios on an automatic test employee:
    python simulate_month_attendance.py --all

    # 2. Run a specific scenario on a test employee for July 2026:
    python simulate_month_attendance.py --scenario perfect --month 2026-07
    python simulate_month_attendance.py --scenario late_arrival --month 2026-07
    python simulate_month_attendance.py --scenario early_exit --month 2026-07
    python simulate_month_attendance.py --scenario half_day --month 2026-07
    python simulate_month_attendance.py --scenario grace_leave --month 2026-07
    python simulate_month_attendance.py --scenario absent --month 2026-07

    # 3. Apply a scenario to an EXISTING employee ID in your database:
    python simulate_month_attendance.py --employee-id 1 --scenario perfect --month 2026-07

    # 4. Clean up simulation demo employee records:
    python simulate_month_attendance.py --cleanup
"""

import sys
import math
import argparse
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from backend.database import get_connection
from backend.services.attendance import (
    calculate_attendance_metrics,
    parse_working_weekdays,
    time_to_minutes,
)
from backend.services.salary import generate_salary, get_salary
from backend.services.settings import get_attendance_bonus_amount

DEMO_PREFIX = "__DEMO_SIMULATION__"


def _money(val):
    return float(Decimal(str(val or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def get_calendar_days_in_month(month_str):
    year, month = map(int, month_str.split("-"))
    _, num_days = calendar.monthrange(year, month)
    return num_days


def get_scheduled_dates_for_employee(month_str, working_weekdays_str):
    year, month = map(int, month_str.split("-"))
    num_days = calendar.monthrange(year, month)[1]
    active_weekdays = parse_working_weekdays(working_weekdays_str)
    scheduled = []
    for day in range(1, num_days + 1):
        cur_date = date(year, month, day)
        if cur_date.weekday() in active_weekdays:
            scheduled.append(cur_date)
    return scheduled


def _normalize_time_str(val, default="09:00:00"):
    if not val:
        return default
    val = str(val).strip()
    parts = val.split(":")
    if len(parts) == 2:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
    elif len(parts) >= 3:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
    return default


def _minutes_to_time(minutes):
    minutes = int(minutes) % (24 * 60)
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}:00"


def create_or_get_demo_employee(name_suffix="DEMO", monthly_salary=30000.0, grace_holidays=2):
    full_name = f"{DEMO_PREFIX}{name_suffix}"
    conn = get_connection()
    try:
        row = conn.execute("SELECT employee_id FROM employees WHERE name = ?", (full_name,)).fetchone()
        if row:
            emp_id = row[0]
            conn.execute(
                """
                UPDATE employees SET
                    monthly_salary = ?,
                    grace_holidays = ?,
                    daily_hours = 8,
                    expected_check_in = '09:00:00',
                    expected_check_out = '17:00:00',
                    late_grace_minutes = 15,
                    working_weekdays = '0,1,2,3,4,5',
                    status = 'active',
                    overtime_enabled = 1
                WHERE employee_id = ?
                """,
                (monthly_salary, grace_holidays, emp_id),
            )
            conn.commit()
            return emp_id

        cursor = conn.execute(
            """
            INSERT INTO employees (
                name, role, salary_type,
                monthly_salary, working_days, grace_holidays,
                daily_hours, expected_check_in, expected_check_out,
                late_grace_minutes, working_weekdays, status,
                overtime_enabled
            ) VALUES (
                ?, 'Software Engineer', 'monthly',
                ?, 26, ?,
                8, '09:00:00', '17:00:00',
                15, '0,1,2,3,4,5', 'active',
                1
            )
            """,
            (full_name, monthly_salary, grace_holidays),
        )
        emp_id = cursor.lastrowid
        conn.commit()
        return emp_id
    finally:
        conn.close()


def clean_attendance_and_salary(employee_id, month_str):
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM attendance WHERE employee_id = ? AND date LIKE ?",
            (employee_id, f"{month_str}%"),
        )
        conn.execute(
            "DELETE FROM salary_cal WHERE employee_id = ? AND month = ?",
            (employee_id, month_str),
        )
        conn.commit()
    finally:
        conn.close()


def insert_day_attendance(employee_id, date_str, check_in_str, check_out_str, emp_info):
    daily_hours = float(emp_info.get("daily_hours") or 8.0)
    expected_in = _normalize_time_str(emp_info.get("expected_check_in"), "09:00:00")
    expected_out = _normalize_time_str(emp_info.get("expected_check_out"), "17:00:00")
    late_grace = int(emp_info.get("late_grace_minutes") or 0)
    ot_enabled = bool(emp_info.get("overtime_enabled", 0))

    check_in_clean = _normalize_time_str(check_in_str, expected_in)
    check_out_clean = _normalize_time_str(check_out_str, expected_out)

    metrics = calculate_attendance_metrics(
        check_in_clean,
        check_out_clean,
        expected_check_in=expected_in,
        expected_check_out=expected_out,
        daily_hours=daily_hours,
        late_grace_minutes=late_grace,
        overtime_enabled=ot_enabled,
    )

    worked_minutes = metrics["worked_minutes"] or 0
    worked_hours = metrics["worked_hours"] or 0.0
    late_minutes = metrics["late_minutes"] or 0
    overtime_minutes = metrics["overtime_minutes"] or 0

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO attendance (
                employee_id, date, check_in, check_out,
                check_in_source, check_out_source,
                worked_hours, worked_minutes,
                late_minutes, overtime_minutes, locked
            ) VALUES (?, ?, ?, ?, 'manual', 'manual', ?, ?, ?, ?, 0)
            """,
            (
                employee_id,
                date_str,
                check_in_clean,
                check_out_clean,
                worked_hours,
                worked_minutes,
                late_minutes,
                overtime_minutes,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_employee_details(employee_id):
    conn = get_connection()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    try:
        row = conn.execute("SELECT * FROM employees WHERE employee_id = ?", (employee_id,)).fetchone()
        return row
    finally:
        conn.close()


def simulate_scenario(employee_id, month_str, scenario_name):
    """
    Populates the entire month with attendance according to the requested scenario,
    generates salary, computes expectations, and outputs validation results.
    """
    emp = get_employee_details(employee_id)
    if not emp:
        print(f"Error: Employee #{employee_id} not found.")
        return False

    clean_attendance_and_salary(employee_id, month_str)

    working_weekdays = emp.get("working_weekdays") or "0,1,2,3,4,5"
    scheduled_dates = get_scheduled_dates_for_employee(month_str, working_weekdays)
    calendar_days = get_calendar_days_in_month(month_str)
    scheduled_count = len(scheduled_dates)
    base_salary = float(emp.get("monthly_salary") or emp.get("base_salary") or 30000.0)
    grace_allowance = float(emp.get("grace_holidays") or 0.0)
    daily_hours = float(emp.get("daily_hours") or 8.0)
    late_grace = int(emp.get("late_grace_minutes") or 0)
    bonus_configured = float(get_attendance_bonus_amount())

    expected_in_str = _normalize_time_str(emp.get("expected_check_in"), "09:00:00")
    expected_out_str = _normalize_time_str(emp.get("expected_check_out"), "17:00:00")

    exp_in_mins = time_to_minutes(expected_in_str)
    exp_out_mins = time_to_minutes(expected_out_str)
    if exp_out_mins is None or exp_out_mins <= exp_in_mins:
        exp_out_mins = exp_in_mins + int(daily_hours * 60)

    standard_in = _minutes_to_time(exp_in_mins)
    standard_out = _minutes_to_time(exp_out_mins)

    print("=" * 70)
    print(f"SIMULATION RUN: Scenario '{scenario_name.upper()}'")
    print("=" * 70)
    print(f"Employee ID       : #{employee_id} ({emp['name']})")
    print(f"Month             : {month_str} ({calendar_days} calendar days)")
    print(f"Scheduled Workdays: {scheduled_count} days (Weekdays: {working_weekdays})")
    print(f"Shift Hours       : {daily_hours} hrs/day ({standard_in} - {standard_out}, Grace: {late_grace}m)")
    print(f"Base Salary       : INR {base_salary:,.2f}")
    print(f"Grace Allowance   : {grace_allowance} days")
    print(f"System Bonus Conf : INR {bonus_configured:,.2f}")
    print("-" * 70)

    # Scenarios logic
    expected_full_days = 0
    expected_half_days = 0
    expected_absence_days = 0.0
    expected_grace_used = 0.0
    expected_charged_leaves = 0.0
    expected_bonus = 0.0
    bonus_reason = ""

    if scenario_name == "perfect":
        # Every scheduled day attended strictly on time, full shift
        for d in scheduled_dates:
            insert_day_attendance(employee_id, d.isoformat(), standard_in, standard_out, emp)
        expected_full_days = scheduled_count
        expected_half_days = 0
        expected_absence_days = 0.0
        expected_grace_used = 0.0
        expected_charged_leaves = 0.0
        expected_bonus = bonus_configured
        bonus_reason = "Full attendance, on-time check-in, full shift, 0 absences, 0 grace used -> Bonus Awarded"

    elif scenario_name == "late_arrival":
        # Day 1: Arrived 15 minutes beyond grace window
        late_in_mins = exp_in_mins + late_grace + 15
        shift_duration_mins = int(daily_hours * 60)
        late_out_mins = late_in_mins + shift_duration_mins
        late_in_str = _minutes_to_time(late_in_mins)
        late_out_str = _minutes_to_time(late_out_mins)

        insert_day_attendance(employee_id, scheduled_dates[0].isoformat(), late_in_str, late_out_str, emp)
        for d in scheduled_dates[1:]:
            insert_day_attendance(employee_id, d.isoformat(), standard_in, standard_out, emp)
        expected_full_days = scheduled_count
        expected_half_days = 0
        expected_absence_days = 0.0
        expected_grace_used = 0.0
        expected_charged_leaves = 0.0
        expected_bonus = 0.0
        bonus_reason = f"Late arrival on Day 1 ({late_in_str} > grace limit) -> Disqualified from bonus"

    elif scenario_name == "early_exit":
        # Day 1: Checked out early (30 min before expected checkout)
        early_out_mins = max(exp_in_mins + 60, exp_out_mins - 30)
        early_out_str = _minutes_to_time(early_out_mins)

        insert_day_attendance(employee_id, scheduled_dates[0].isoformat(), standard_in, early_out_str, emp)
        for d in scheduled_dates[1:]:
            insert_day_attendance(employee_id, d.isoformat(), standard_in, standard_out, emp)

        # Check whether working duration still reaches full day or half day
        worked_d1 = early_out_mins - exp_in_mins
        full_thresh = int((daily_hours * 60) - late_grace)
        half_thresh = math.ceil(daily_hours * 60 * 0.5)

        if worked_d1 >= full_thresh:
            expected_full_days = scheduled_count
            expected_half_days = 0
            expected_absence_days = 0.0
            expected_grace_used = 0.0
            expected_charged_leaves = 0.0
        elif worked_d1 >= half_thresh:
            expected_full_days = scheduled_count - 1
            expected_half_days = 1
            expected_absence_days = 0.5
            expected_grace_used = min(0.5, grace_allowance)
            expected_charged_leaves = 0.5 - expected_grace_used
        else:
            expected_full_days = scheduled_count - 1
            expected_half_days = 0
            expected_absence_days = 1.0
            expected_grace_used = min(1.0, grace_allowance)
            expected_charged_leaves = 1.0 - expected_grace_used

        expected_bonus = 0.0
        bonus_reason = f"Early check-out on Day 1 ({early_out_str} < {standard_out}) -> Disqualified from bonus"

    elif scenario_name == "half_day":
        # Day 1: Worked at least 50% of daily shift (half day)
        half_duration_mins = math.ceil(daily_hours * 60 * 0.5)
        half_out_mins = exp_in_mins + half_duration_mins
        half_out_str = _minutes_to_time(half_out_mins)

        insert_day_attendance(employee_id, scheduled_dates[0].isoformat(), standard_in, half_out_str, emp)
        for d in scheduled_dates[1:]:
            insert_day_attendance(employee_id, d.isoformat(), standard_in, standard_out, emp)
        expected_full_days = scheduled_count - 1
        expected_half_days = 1
        expected_absence_days = 0.5
        expected_grace_used = min(0.5, grace_allowance)
        expected_charged_leaves = 0.5 - expected_grace_used
        expected_bonus = 0.0
        bonus_reason = "1 half-day taken -> Disqualified from bonus (half_days > 0)"

    elif scenario_name == "grace_leave":
        # Day 1: Absent (no attendance record). Remaining days attended on time.
        for d in scheduled_dates[1:]:
            insert_day_attendance(employee_id, d.isoformat(), standard_in, standard_out, emp)
        expected_full_days = scheduled_count - 1
        expected_half_days = 0
        expected_absence_days = 1.0
        expected_grace_used = min(1.0, grace_allowance)
        expected_charged_leaves = 1.0 - expected_grace_used
        expected_bonus = 0.0
        bonus_reason = "1 absent day covered by grace holiday ('not even grace' rule) -> Disqualified from bonus"

    elif scenario_name == "absent":
        # First 3 days absent.
        for d in scheduled_dates[3:]:
            insert_day_attendance(employee_id, d.isoformat(), standard_in, standard_out, emp)
        expected_full_days = scheduled_count - 3
        expected_half_days = 0
        expected_absence_days = 3.0
        expected_grace_used = min(3.0, grace_allowance)
        expected_charged_leaves = 3.0 - expected_grace_used
        expected_bonus = 0.0
        bonus_reason = "Unpaid absences taken -> Disqualified from bonus"

    elif scenario_name == "overtime_perfect":
        # Every day worked 1 hour overtime
        ot_out_mins = exp_out_mins + 60
        ot_out_str = _minutes_to_time(ot_out_mins)
        for d in scheduled_dates:
            insert_day_attendance(employee_id, d.isoformat(), standard_in, ot_out_str, emp)
        expected_full_days = scheduled_count
        expected_half_days = 0
        expected_absence_days = 0.0
        expected_grace_used = 0.0
        expected_charged_leaves = 0.0
        expected_bonus = bonus_configured
        bonus_reason = "Perfect attendance with daily overtime -> Bonus Awarded"

    else:
        print(f"Unknown scenario '{scenario_name}'.")
        return False

    # Generate salary via backend service
    salary_res = generate_salary(employee_id, month_str, role="head")

    # Theoretical expected calculations
    daily_rate = Decimal(str(base_salary)) / Decimal(str(calendar_days))
    expected_deduction = _money(daily_rate * Decimal(str(expected_charged_leaves)))
    expected_net = _money(Decimal(str(base_salary)) - Decimal(str(expected_deduction)) + Decimal(str(expected_bonus)))

    actual_full = salary_res.get("full_days") or 0
    actual_half = salary_res.get("half_days") or 0
    actual_absent = float(salary_res.get("absence_days") or 0.0)
    actual_grace_used = float(salary_res.get("grace_holidays_used") or 0.0)
    actual_charged = float(salary_res.get("deducted_holidays") or 0.0)
    actual_deduction = _money(salary_res.get("salary_deduction") or 0.0)
    actual_bonus = _money(salary_res.get("bonus_amount") or 0.0)
    actual_net = _money(salary_res.get("total_salary") or 0.0)

    # Comparison Table
    checks = [
        ("Scheduled Days", scheduled_count, salary_res.get("working_days")),
        ("Full Days", expected_full_days, actual_full),
        ("Half Days", expected_half_days, actual_half),
        ("Absent Days", expected_absence_days, actual_absent),
        ("Grace Used", expected_grace_used, actual_grace_used),
        ("Charged Leaves", expected_charged_leaves, actual_charged),
        ("Leave Deduction", expected_deduction, actual_deduction),
        ("Attendance Bonus", expected_bonus, actual_bonus),
        ("Net Salary", expected_net, actual_net),
    ]

    print(f"{'METRIC':<20} | {'EXPECTED':<15} | {'GENERATED':<15} | {'STATUS'}")
    print("-" * 70)
    all_ok = True
    for name, exp, act in checks:
        if isinstance(exp, float) and isinstance(act, (int, float)):
            match = abs(exp - float(act)) < 0.02
        else:
            match = (exp == act)
        status_str = "MATCH (PASS)" if match else "MISMATCH (FAIL)"
        if not match:
            all_ok = False
        print(f"{name:<20} | {str(exp):<15} | {str(act):<15} | {status_str}")

    print("-" * 70)
    print(f"Bonus Policy Assessment : {bonus_reason}")
    if all_ok:
        print(f"OVERALL RESULT          : PASS - Generated salary perfectly matches expectations!")
    else:
        print(f"OVERALL RESULT          : FAIL - Discrepancy detected.")
    print("=" * 70 + "\n")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Simulate monthly attendance and test payroll/bonus calculations.")
    parser.add_argument("--employee-id", type=int, help="Target employee ID (default: creates/uses a demo employee)")
    parser.add_argument("--month", default="2026-07", help="Payroll month in YYYY-MM format (default: 2026-07)")
    parser.add_argument(
        "--scenario",
        default="perfect",
        choices=["perfect", "late_arrival", "early_exit", "half_day", "grace_leave", "absent", "overtime_perfect", "all"],
        help="Scenario to run: perfect, late_arrival, early_exit, half_day, grace_leave, absent, overtime_perfect, all",
    )
    parser.add_argument("--all", action="store_true", help="Run all 7 edge case scenarios sequentially")
    parser.add_argument("--cleanup", action="store_true", help="Delete all demo employees and records created by this tool")

    args = parser.parse_args()

    if args.cleanup:
        conn = get_connection()
        try:
            conn.execute(
                "DELETE FROM attendance WHERE employee_id IN (SELECT employee_id FROM employees WHERE name LIKE ?)",
                (f"{DEMO_PREFIX}%",),
            )
            conn.execute(
                "DELETE FROM salary_cal WHERE employee_id IN (SELECT employee_id FROM employees WHERE name LIKE ?)",
                (f"{DEMO_PREFIX}%",),
            )
            cursor = conn.execute("DELETE FROM employees WHERE name LIKE ?", (f"{DEMO_PREFIX}%",))
            conn.commit()
            print(f"Cleaned up {cursor.rowcount} demo employee record(s).")
            sys.exit(0)
        finally:
            conn.close()

    month_str = args.month

    if args.all or args.scenario == "all":
        scenarios = ["perfect", "overtime_perfect", "late_arrival", "early_exit", "half_day", "grace_leave", "absent"]
        emp_id = args.employee_id or create_or_get_demo_employee("AUTO_TEST")
        results = {}
        for sc in scenarios:
            results[sc] = simulate_scenario(emp_id, month_str, sc)

        print("\n" + "=" * 50)
        print("SUMMARY OF ALL SCENARIO RUNS:")
        print("=" * 50)
        for sc, ok in results.items():
            print(f"  {sc:<20}: {'PASS [OK]' if ok else 'FAIL [X]'}")
        print("=" * 50)
        sys.exit(0 if all(results.values()) else 1)
    else:
        emp_id = args.employee_id or create_or_get_demo_employee(args.scenario.upper())
        ok = simulate_scenario(emp_id, month_str, args.scenario)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
