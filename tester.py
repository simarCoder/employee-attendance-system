import sqlite3

conn = sqlite3.connect("db/attendance.db")
cur = conn.cursor()

print("\n=== EMPLOYEE ===")

cur.execute("PRAGMA table_info(employees)")
existing_employee_columns = {
    row[1] for row in cur.fetchall()
}

if "working_days" not in existing_employee_columns:
    cur.execute("""
        ALTER TABLE employees
        ADD COLUMN working_days REAL NOT NULL DEFAULT 26
    """)
    
    


print("\n=== ATTENDANCE AUGUST ===")


conn.close()