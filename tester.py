import sqlite3

conn = sqlite3.connect("db/attendance.db")
cur = conn.cursor()

print("\n=== EMPLOYEE ===")

cur.execute("""
SELECT
    employee_id,
    name,
    monthly_salary,
    daily_hours,
    salary_type,
    overtime_enabled,
    overtime_rate
FROM employees
WHERE employee_id = 1
""")

print(cur.fetchone())


print("\n=== ATTENDANCE AUGUST ===")

cur.execute("""
SELECT
    date,
    check_in,
    check_out,
    worked_hours,
    worked_minutes,
    late_minutes,
    overtime_minutes
FROM attendance
WHERE employee_id = 1
  AND date LIKE '2026-08-%'
ORDER BY date
""")

rows = cur.fetchall()

for row in rows:
    print(row)


print("\n=== ATTENDANCE TOTALS ===")

cur.execute("""
SELECT
    COALESCE(SUM(worked_minutes), 0),
    COALESCE(SUM(overtime_minutes), 0)
FROM attendance
WHERE employee_id = 1
  AND date LIKE '2026-08-%'
""")

print(cur.fetchone())


print("\n=== SALARY_CAL ===")

cur.execute("""
SELECT
    salary_id,
    employee_id,
    month,
    total_hours,
    hourly_rate_snapshot,
    total_salary,
    locked
FROM salary_cal
WHERE employee_id = 1
  AND month = '2026-08'
""")

print(cur.fetchone())

conn.close()