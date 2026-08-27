import sqlite3
from backend.services.salary import generate_salary

DB = "db/attendance.db"
TEST_EMPLOYEE_ID = 999999
MONTH = "2026-09"

conn = sqlite3.connect(DB)
cur = conn.cursor()

try:
    # Clean previous test data
    cur.execute(
        "DELETE FROM attendance WHERE employee_id = ?",
        (TEST_EMPLOYEE_ID,)
    )

    cur.execute(
        "DELETE FROM salary_cal WHERE employee_id = ?",
        (TEST_EMPLOYEE_ID,)
    )

    cur.execute(
        "DELETE FROM employees WHERE employee_id = ?",
        (TEST_EMPLOYEE_ID,)
    )

    # Create controlled test employee
    cur.execute("""
        INSERT INTO employees (
            employee_id,
            name,
            role,
            monthly_salary,
            daily_hours,
            working_days,
            salary_type,
            grace_holidays,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        TEST_EMPLOYEE_ID,
        "SALARY TEST",
        "Tester",
        26000,
        8,
        26,
        "monthly",
        2,
        "active"
    ))

    # Attendance:
    # Sep 1 = full day -> 480 min
    # Sep 2 = half day -> 240 min
    # Sep 3 = half day -> 240 min
    #
    # Absence:
    # 0 + 0.5 + 0.5 = 1.0 day
    #
    # Grace:
    # 2.0 available
    #
    # Therefore:
    # Absence = 1.0
    # Grace used = 1.0
    # Deducted = 0.0

    attendance = [
        ("2026-09-01", 480),
        ("2026-09-02", 240),
        ("2026-09-03", 240),
    ]

    for attendance_date, worked_minutes in attendance:
        cur.execute("""
            INSERT INTO attendance (
                employee_id,
                date,
                worked_minutes
            )
            VALUES (?, ?, ?)
        """, (
            TEST_EMPLOYEE_ID,
            attendance_date,
            worked_minutes
        ))

    conn.commit()

    print("\n=== SALARY TEST ===")

    result = generate_salary(
        TEST_EMPLOYEE_ID,
        MONTH
    )

    print("Employee:", result["employee_name"])
    print("Monthly salary:", result["monthly_salary"])
    print("Working days:", result["working_days"])
    print("Daily hours:", result["daily_hours"])
    print("Expected minutes:", result["expected_monthly_minutes"])
    print("Actual worked minutes:", result["actual_worked_minutes"])
    print("Absence days:", result["absence_days"])
    print("Grace used:", result["grace_holidays_used"])
    print("Deducted holidays:", result["deducted_holidays"])
    print("Paid minutes:", result["paid_minutes"])
    print("Base salary:", result["base_salary"])
    print("Total salary:", result["total_salary"])

    print("\n=== EXPECTED ===")
    print("Absence: 1.0")
    print("Grace used: 1.0")
    print("Deducted holidays: 0.0")
    print("Total salary: 26000.0")

finally:
    # Remove test data
    cur.execute(
        "DELETE FROM attendance WHERE employee_id = ?",
        (TEST_EMPLOYEE_ID,)
    )

    cur.execute(
        "DELETE FROM salary_cal WHERE employee_id = ?",
        (TEST_EMPLOYEE_ID,)
    )

    cur.execute(
        "DELETE FROM employees WHERE employee_id = ?",
        (TEST_EMPLOYEE_ID,)
    )

    conn.commit()
    conn.close()

    print("\n=== TEST DATA CLEANED ===")