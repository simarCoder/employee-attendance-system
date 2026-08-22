import sqlite3
import os
import sys
from backend.utils.security import encrypt_password

# ---------------------------------------------------------
# PATH LOGIC FOR PYINSTALLER
# ---------------------------------------------------------
if getattr(sys, 'frozen', False):
    # If frozen, DB should be next to executable
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # If Dev, assuming file is in /backend/database.py, go up one level
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

DB_FOLDER = os.path.join(BASE_DIR, "db")
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, "attendance.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def employee_db():
    conn = get_connection()
    cursor = conn.cursor()

    # =========================
    # EMPLOYEE RECORDS
    # =========================
    cursor.execute ('''
    CREATE TABLE IF NOT EXISTS employees (
        employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        role TEXT,
        phone TEXT,
        address TEXT,
        hourly_rate NUMERIC,
        monthly_salary REAL NOT NULL,
        status TEXT DEFAULT 'active',
        salary_type TEXT NOT NULL DEFAULT 'monthly',
        daily_hours REAL NOT NULL DEFAULT 8,
        expected_check_in TEXT,
        expected_check_out TEXT,
        late_grace_minutes INTEGER NOT NULL DEFAULT 0,
        overtime_enabled INTEGER NOT NULL DEFAULT 0,
        overtime_rate REAL NOT NULL DEFAULT 1
    )
    ''')

    # =========================
    # ATTENDANCE
    # =========================
    # cursor.execute ("""
    #     CREATE TABLE IF NOT EXISTS attendance (
    #         attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    #         employee_id INTEGER NOT NULL, 
    #         date TEXT NOT NULL,
    #         check_in TEXT,
    #         check_out TEXT,
    #         check_in_source TEXT DEFAULT 'manual',
    #         check_out_source TEXT DEFAULT 'manual',
    #         worked_hours REAL,
    #         locked INTEGER DEFAULT 0,
    #         FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
    #     )
    # """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        check_in TEXT,
        check_out TEXT,
        check_in_source TEXT DEFAULT 'manual',
        check_out_source TEXT DEFAULT 'manual',

        worked_hours REAL,
        worked_minutes INTEGER,

        late_minutes INTEGER DEFAULT 0,
        overtime_minutes INTEGER DEFAULT 0,

        locked INTEGER DEFAULT 0,

        FOREIGN KEY (employee_id)
            REFERENCES employees(employee_id)
    )
""")
    
    
    
    
    # =========================
    # BIOMETRIC DEVICE PUNCHES
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS device_punches (
            punch_id INTEGER PRIMARY KEY AUTOINCREMENT,

            device_card_id INTEGER NOT NULL,

            punch_time TEXT NOT NULL,

            event_code INTEGER NOT NULL,

            verification_type TEXT,

            raw_timestamp TEXT,

            raw_data TEXT,

            imported_at TEXT NOT NULL,

            UNIQUE (
                device_card_id,
                punch_time,
                event_code,
                raw_timestamp
            )
        )
    """)

    # =========================
    # SALARY
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salary_cal(
            salary_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            month TEXT NOT NULL,

            employee_name TEXT,
            employee_role TEXT,
            salary_type TEXT,
            monthly_salary_snapshot REAL,
            daily_hours REAL,
            working_days INTEGER,

            expected_monthly_minutes REAL,
            actual_worked_minutes INTEGER,
            total_hours REAL,
            overtime_minutes INTEGER DEFAULT 0,

            hourly_rate_snapshot REAL,
            base_salary REAL,
            overtime_pay REAL DEFAULT 0,
            total_salary REAL,

            locked INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,

            FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
        )
    """)

    # Existing installations already have salary_cal. CREATE TABLE IF NOT
    # EXISTS does not add columns, so migrate missing columns safely.
    salary_columns = {
        "employee_name": "TEXT",
        "employee_role": "TEXT",
        "salary_type": "TEXT",
        "monthly_salary_snapshot": "REAL",
        "daily_hours": "REAL",
        "working_days": "INTEGER",
        "expected_monthly_minutes": "REAL",
        "actual_worked_minutes": "INTEGER",
        "overtime_minutes": "INTEGER DEFAULT 0",
        "base_salary": "REAL",
        "overtime_pay": "REAL DEFAULT 0",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }

    cursor.execute("PRAGMA table_info(salary_cal)")
    existing_salary_columns = {row[1] for row in cursor.fetchall()}

    for column_name, column_definition in salary_columns.items():
        if column_name not in existing_salary_columns:
            cursor.execute(
                f"ALTER TABLE salary_cal ADD COLUMN {column_name} {column_definition}"
            )

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_salary_cal_employee_month
        ON salary_cal(employee_id, month)
    """)

    # Safely enrich older salary records with values that can be recovered.
    cursor.execute("""
        UPDATE salary_cal
        SET
            employee_name = COALESCE(
                employee_name,
                (SELECT name FROM employees e
                 WHERE e.employee_id = salary_cal.employee_id)
            ),
            employee_role = COALESCE(
                employee_role,
                (SELECT role FROM employees e
                 WHERE e.employee_id = salary_cal.employee_id)
            ),
            salary_type = COALESCE(
                salary_type,
                (SELECT salary_type FROM employees e
                 WHERE e.employee_id = salary_cal.employee_id)
            ),
            monthly_salary_snapshot = COALESCE(
                monthly_salary_snapshot,
                (SELECT monthly_salary FROM employees e
                 WHERE e.employee_id = salary_cal.employee_id)
            ),
            daily_hours = COALESCE(
                daily_hours,
                (SELECT daily_hours FROM employees e
                 WHERE e.employee_id = salary_cal.employee_id)
            ),
            actual_worked_minutes = COALESCE(
                actual_worked_minutes,
                CAST(ROUND(COALESCE(total_hours, 0) * 60) AS INTEGER)
            ),
            base_salary = COALESCE(base_salary, total_salary),
            overtime_pay = COALESCE(overtime_pay, 0),
            overtime_minutes = COALESCE(overtime_minutes, 0),
            created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
            updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
        WHERE 1 = 1
    """)

    # USERS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)
    
    # =========================
    # SEEDING & REPAIR (Reversible Encryption)
    # =========================
    # Generate encrypted passwords (not one-way hashes)
    admin_enc = encrypt_password('admin')
    dev_enc = encrypt_password('DEV1234')

    # 1. Ensure users exist
    cursor.execute("""
        INSERT OR IGNORE INTO users (username, password_hash, role)
        VALUES ('admin', ?, 'admin')
    """, (admin_enc,))

    cursor.execute("""
        INSERT OR IGNORE INTO users (username, password_hash, role)
        VALUES ('developer', ?, 'head')
    """, (dev_enc,))

    # 2. FORCE UPDATE to ensure correct encryption is applied
    cursor.execute("""
        UPDATE users SET password_hash = ? WHERE username = 'admin'
    """, (admin_enc,))

    cursor.execute("""
        UPDATE users SET password_hash = ? WHERE username = 'developer'
    """, (dev_enc,))

    # =========================
    # SYSTEM SETTINGS (New)
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings(
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        )
    """)

    # Seed Default Working Hours (16)
    cursor.execute("""
        INSERT OR IGNORE INTO system_settings (setting_key, setting_value)
        VALUES ('daily_hours', '16')
    """)
    
    # Seed Default Working Days
# Monday-Saturday
    cursor.execute("""
        INSERT OR IGNORE INTO system_settings (
            setting_key,
            setting_value
        )
        VALUES ('working_days', '0,1,2,3,4,5')
    """)
    # New installations start with no active subscription.
    # Developer must activate the subscription.
    cursor.execute("""
        INSERT OR IGNORE INTO system_settings
        (setting_key, setting_value)
        VALUES ('subscription_expiry', '')
    """)

    # Seed Default Demo Mode (true)
    cursor.execute("""
        INSERT OR IGNORE INTO system_settings (setting_key, setting_value)
        VALUES ('demo_mode', 'true')
    """)

    # =========================
    # DOCUMENT TABLES
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employee_docs(
            doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            adhaar_no INTEGER NOT NULL,
            doc_type TEXT NOT NULL,
            file_path TEXT,
            upload_at TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
        )
    """)
    
    # =========================
    # AUDIT LOGS
    # =========================
    cursor.execute("""  
        CREATE TABLE IF NOT EXISTS audit_logs(
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                entity TEXT,
                timestamp TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    
    #=====================
    # BIOMETRIC DEVICES
    #=====================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS biometric_devices (
        device_id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_card_id INTEGER NOT NULL UNIQUE,
        employee_id INTEGER NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (employee_id)
            REFERENCES employees(employee_id)
    )
""")

    conn.commit()
    cursor.close()
    conn.close()





if __name__ == "__main__":
    employee_db()