"""
populate_month_attendance.py
----------------------------
Populate full-month attendance records for all active employees based on
their configured expected check-in and check-out timings on their scheduled
working weekdays.

Instructions:
1. Change `TARGET_MONTH` below to any month you want (e.g., "2026-10", "2026-11").
   Alternatively, you can pass the month via command line:
       python populate_month_attendance.py 2026-10
       python populate_month_attendance.py 2026-10 --dry-run
2. Run the script:
       python populate_month_attendance.py
"""

import sys
import os
import calendar
import sqlite3
from datetime import datetime, date

# =====================================================================
# CONFIGURATION - CHANGE AS NEEDED
# =====================================================================
TARGET_MONTH = "2026-10"           # Format: YYYY-MM
OVERWRITE_EXISTING = True          # If True, updates existing punches for that day
EXCLUDE_TEST_ACCOUNTS = True       # If True, skips employee names starting with '__'
RECORD_SOURCE = "admin"            # Source label: 'admin', 'system', or 'manual'
# =====================================================================

def get_db_path():
    """Locate the attendance database relative to this script."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    primary = os.path.join(base_dir, "db", "attendance.db")
    if os.path.exists(primary):
        return primary
    # Fallback to local db if run from another folder
    if os.path.exists("db/attendance.db"):
        return os.path.abspath("db/attendance.db")
    return primary


def normalize_time(time_str, default="09:00:00"):
    """Normalize 'HH:MM' or 'HH:MM:SS' to standard 'HH:MM:SS'."""
    if not time_str or not str(time_str).strip():
        return default
    time_str = str(time_str).strip()
    parts = time_str.split(":")
    if len(parts) == 2:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
    elif len(parts) == 3:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
    return default


def parse_weekdays(weekdays_str):
    """Parse comma-separated weekday numbers (0=Mon, 1=Tue, ..., 6=Sun)."""
    if not weekdays_str or not str(weekdays_str).strip():
        return {0, 1, 2, 3, 4, 5}  # Default Mon-Sat
    result = set()
    for token in str(weekdays_str).split(","):
        token = token.strip()
        if token.isdigit():
            val = int(token)
            if 0 <= val <= 6:
                result.add(val)
    return result if result else {0, 1, 2, 3, 4, 5}


def time_to_minutes(time_str):
    """Convert 'HH:MM' or 'HH:MM:SS' string into minutes from midnight."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def calculate_metrics(check_in, check_out, daily_hours=8.0):
    """Calculate worked minutes, hours, late minutes and overtime minutes."""
    in_mins = time_to_minutes(check_in)
    out_mins = time_to_minutes(check_out)

    if out_mins >= in_mins:
        worked_minutes = out_mins - in_mins
    else:
        # Overnight shift
        worked_minutes = (24 * 60 - in_mins) + out_mins

    worked_hours = round(worked_minutes / 60.0, 2)
    late_minutes = 0  # Since checking in exactly at expected time

    required_minutes = int(round(float(daily_hours or 0) * 60))
    overtime_minutes = max(0, worked_minutes - required_minutes)

    return worked_minutes, worked_hours, late_minutes, overtime_minutes


def populate_attendance(target_month, dry_run=False):
    # Parse and validate month
    try:
        year, month = map(int, target_month.split("-"))
        _, days_in_month = calendar.monthrange(year, month)
    except Exception as exc:
        print(f"[ERROR] Invalid target month '{target_month}'. Expected format: YYYY-MM (e.g. 2026-10). Error: {exc}")
        return

    db_path = get_db_path()
    print(f"\n=======================================================")
    print(f" ATTENDANCE AUTO-POPULATION SCRIPT")
    print(f"=======================================================")
    print(f" Target Month   : {target_month} ({days_in_month} calendar days)")
    print(f" Database Path  : {db_path}")
    print(f" Dry Run Mode   : {'YES (No changes will be saved)' if dry_run else 'NO (Changes will be written to DB)'}")
    print(f" Overwrite Mode : {'YES' if OVERWRITE_EXISTING else 'NO (Skip existing records)'}")
    print(f"=======================================================\n")

    if not os.path.exists(db_path):
        print(f"[ERROR] Database file not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query active employees
    cursor.execute("""
        SELECT
            employee_id,
            name,
            working_weekdays,
            daily_hours,
            expected_check_in,
            expected_check_out,
            late_grace_minutes
        FROM employees
        WHERE status = 'active'
        ORDER BY employee_id
    """)
    employees = cursor.fetchall()

    if not employees:
        print("[INFO] No active employees found in the database.")
        conn.close()
        return

    total_inserted = 0
    total_updated = 0
    total_skipped = 0

    print(f"Found {len(employees)} active employee(s).\n")

    for emp in employees:
        emp_id, emp_name, w_weekdays, daily_hours, exp_in, exp_out, grace = emp

        if EXCLUDE_TEST_ACCOUNTS and emp_name.startswith("__"):
            continue

        scheduled_weekdays = parse_weekdays(w_weekdays)
        check_in_time = normalize_time(exp_in, default="09:00:00")
        check_out_time = normalize_time(exp_out, default="17:00:00")
        emp_daily_hours = float(daily_hours) if daily_hours else 8.0

        worked_mins, worked_hrs, late_mins, ot_mins = calculate_metrics(
            check_in_time, check_out_time, emp_daily_hours
        )

        emp_inserted = 0
        emp_updated = 0
        emp_skipped = 0

        # Loop through each day of the month
        for day in range(1, days_in_month + 1):
            cur_date = date(year, month, day)
            date_str = cur_date.isoformat()  # 'YYYY-MM-DD'
            day_of_week = cur_date.weekday() # 0 = Monday, ..., 6 = Sunday

            # If not a scheduled working day for this employee, skip it (off day)
            if day_of_week not in scheduled_weekdays:
                continue

            # Check if record already exists
            cursor.execute(
                "SELECT attendance_id FROM attendance WHERE employee_id = ? AND date = ?",
                (emp_id, date_str)
            )
            existing = cursor.fetchone()

            if existing:
                if OVERWRITE_EXISTING:
                    if not dry_run:
                        cursor.execute("""
                            UPDATE attendance
                            SET check_in = ?,
                                check_out = ?,
                                check_in_source = ?,
                                check_out_source = ?,
                                worked_hours = ?,
                                worked_minutes = ?,
                                late_minutes = ?,
                                overtime_minutes = ?
                            WHERE attendance_id = ?
                        """, (
                            check_in_time,
                            check_out_time,
                            RECORD_SOURCE,
                            RECORD_SOURCE,
                            worked_hrs,
                            worked_mins,
                            late_mins,
                            ot_mins,
                            existing[0]
                        ))
                    emp_updated += 1
                else:
                    emp_skipped += 1
            else:
                if not dry_run:
                    cursor.execute("""
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
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (
                        emp_id,
                        date_str,
                        check_in_time,
                        check_out_time,
                        RECORD_SOURCE,
                        RECORD_SOURCE,
                        worked_hrs,
                        worked_mins,
                        late_mins,
                        ot_mins
                    ))
                emp_inserted += 1

        total_inserted += emp_inserted
        total_updated += emp_updated
        total_skipped += emp_skipped

        weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        schedule_label = ",".join(weekday_names[d] for d in sorted(scheduled_weekdays))
        print(f"  - ID {emp_id:3d} | {emp_name:<30} | {check_in_time[:5]}-{check_out_time[:5]} ({schedule_label}) -> "
              f"+{emp_inserted} added, ~{emp_updated} updated, {emp_skipped} skipped")

    if not dry_run:
        conn.commit()
        print("\n[SUCCESS] All records committed successfully to the database!")
    else:
        print("\n[INFO] Dry-run complete. No database changes were made.")

    print(f"Summary: Total Added = {total_inserted}, Total Updated = {total_updated}, Total Skipped = {total_skipped}")
    print("=======================================================\n")
    conn.close()


if __name__ == "__main__":
    target = TARGET_MONTH
    dry = False

    # CLI arguments support:
    #   python populate_month_attendance.py 2026-10
    #   python populate_month_attendance.py 2026-10 --dry-run
    #   python populate_month_attendance.py --dry-run
    args = sys.argv[1:]
    for arg in args:
        if arg in ("--dry-run", "-d"):
            dry = True
        elif not arg.startswith("-"):
            target = arg

    populate_attendance(target, dry_run=dry)
