import os
import sys
import sqlite3
from datetime import datetime
from backend.database import get_connection
from backend.services.employee import recalculate_all_employee_rates
from backend.utils.security import encrypt_date, decrypt_date, encrypt_password, decrypt_password

# ---------------------------------------------------------
# PATH LOGIC FOR PYINSTALLER
# ---------------------------------------------------------
if getattr(sys, 'frozen', False):
    # Exe Directory
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Dev Directory (Assuming services/settings.py -> go up 2 levels)
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

DB_SOURCE_PATH = os.path.join(BASE_DIR, 'db', 'attendance.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'BACKUPS')

def get_working_hours():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'daily_hours'")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return float(row[0]) if row else 16.0

def update_working_hours(new_hours):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO system_settings (setting_key, setting_value) 
        VALUES ('daily_hours', ?) 
        ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
    """, (str(new_hours),))
    conn.commit()
    cursor.close()
    conn.close()
    recalculate_all_employee_rates()
    
def get_working_days():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT setting_value
        FROM system_settings
        WHERE setting_key = 'working_days'
    """)

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    # Default: Monday-Saturday
    if not row or not row[0]:
        return [0, 1, 2, 3, 4, 5]

    try:
        return [
            int(day)
            for day in row[0].split(",")
            if day.strip()
        ]
    except ValueError:
        return [0, 1, 2, 3, 4, 5]


def update_working_days(days):
    if not isinstance(days, list):
        raise ValueError("Working days must be a list")

    cleaned_days = sorted(
        set(
            int(day)
            for day in days
            if 0 <= int(day) <= 6
        )
    )

    if not cleaned_days:
        raise ValueError(
            "At least one working day must be selected"
        )

    value = ",".join(
        str(day)
        for day in cleaned_days
    )

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO system_settings (
            setting_key,
            setting_value
        )
        VALUES ('working_days', ?)

        ON CONFLICT(setting_key)
        DO UPDATE SET
            setting_value = excluded.setting_value
    """, (value,))

    conn.commit()

    cursor.close()
    conn.close()


def update_working_days(days):
    """
    days = list of Python weekday numbers.

    Monday = 0
    Tuesday = 1
    Wednesday = 2
    Thursday = 3
    Friday = 4
    Saturday = 5
    Sunday = 6
    """

    cleaned_days = sorted(
        set(
            int(day)
            for day in days
            if 0 <= int(day) <= 6
        )
    )

    value = ",".join(str(day) for day in cleaned_days)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO system_settings (
            setting_key,
            setting_value
        )
        VALUES ('working_days', ?)
        ON CONFLICT(setting_key)
        DO UPDATE SET setting_value = excluded.setting_value
    """, (value,))

    conn.commit()

    cursor.close()
    conn.close()

# --- DEMO MODE LOGIC (NEW) ---
def get_demo_mode_status():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'demo_mode'")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    # Default to True if the row doesn't exist yet
    return row[0] == 'true' if row else True

def update_demo_mode(enabled):
    val = 'true' if enabled else 'false'
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO system_settings (setting_key, setting_value) 
        VALUES ('demo_mode', ?) 
        ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
    """, (val,))
    conn.commit()
    cursor.close()
    conn.close()

# --- BACKUP LOGIC ---
# def create_database_backup():
#     """
#     Creates a timestamped copy of the database in the BACKUPS folder.
#     """
#     if not os.path.exists(DB_SOURCE_PATH):
#         raise FileNotFoundError(f"Live database file not found at {DB_SOURCE_PATH}")

#     # Ensure Backup Directory Exists
#     os.makedirs(BACKUP_DIR, exist_ok=True)

#     # Create filename: attendance_backup_YYYY-MM-DD_HH-MM-SS.db
#     timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
#     backup_filename = f"attendance_backup_{timestamp}.db"
#     backup_path = os.path.join(BACKUP_DIR, backup_filename)

#     # Copy the file (copy2 preserves metadata)
#     shutil.copy2(DB_SOURCE_PATH, backup_path)
    
#     return backup_filename

def create_database_backup():
    """
    Creates a consistent SQLite backup using SQLite's backup API.
    Safe to use while the application is running.
    """
    if not os.path.exists(DB_SOURCE_PATH):
        raise FileNotFoundError(
            f"Live database file not found at {DB_SOURCE_PATH}"
        )

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"attendance_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    source_conn = None
    backup_conn = None

    try:
        source_conn = get_connection()

        backup_conn = sqlite3.connect(
            backup_path,
            timeout=30
        )

        source_conn.backup(backup_conn)

        backup_conn.commit()

    finally:
        if backup_conn:
            backup_conn.close()

        if source_conn:
            source_conn.close()

    return backup_filename


# --- SaaS SUBSCRIPTION LOGIC ---

def update_subscription_expiry(date_str):
    encrypted_val = encrypt_date(date_str)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO system_settings (setting_key, setting_value) 
        VALUES ('sub_expiry', ?) 
        ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
    """, (encrypted_val,))
    conn.commit()
    cursor.close()
    conn.close()

def get_subscription_expiry_encrypted():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'sub_expiry'")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None

# --- USER MANAGEMENT HELPERS ---

# def _renumber_users(cursor):
#     cursor.execute("PRAGMA foreign_keys = OFF")
#     cursor.execute("SELECT user_id FROM users ORDER BY user_id ASC")
#     users = cursor.fetchall()
    
#     for index, user in enumerate(users):
#         current_id = user[0]
#         expected_id = index + 1
#         if current_id != expected_id:
#             cursor.execute("UPDATE users SET user_id = ? WHERE user_id = ?", (expected_id, current_id))

#     cursor.execute("DELETE FROM sqlite_sequence WHERE name='users'")
#     cursor.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('users', ?)", (len(users),))
#     cursor.execute("PRAGMA foreign_keys = ON")

def add_system_user(username, password, role):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        raise ValueError("Username already exists")

    # ENCRYPT PASSWORD (Reversible)
    encrypted_pw = encrypt_password(password)

    cursor.execute("""
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
    """, (username, encrypted_pw, role))
    # _renumber_users(cursor)
    conn.commit()
    cursor.close()
    conn.close()

def get_all_system_users():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, username, password_hash, role
        FROM users
        ORDER BY user_id ASC
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    users = []

    for row in rows:
        user_id, username, encrypted_pw, role = row

        try:
            password = decrypt_password(encrypted_pw)
        except Exception:
            password = None

        users.append((
            user_id,
            username,
            password,
            role
        ))

    return users


def update_user_password(user_id, new_password):
    conn = get_connection()
    cursor = conn.cursor()
    
    # ENCRYPT PASSWORD
    encrypted_pw = encrypt_password(new_password)
    
    cursor.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (encrypted_pw, user_id))
    conn.commit()
    cursor.close()
    conn.close()

# def delete_system_user(target_user_id, current_user_id_requesting=None):
#     conn = get_connection()
#     cursor = conn.cursor()
    
#     cursor.execute("SELECT role FROM users WHERE user_id = ?", (target_user_id,))
#     target = cursor.fetchone()
    
#     if not target:
#         cursor.close()
#         conn.close()
#         raise ValueError("User not found")
        
#     target_role = target[0]

#     if current_user_id_requesting and str(target_user_id) == str(current_user_id_requesting):
#         cursor.close()
#         conn.close()
#         raise ValueError("You cannot delete your own account while logged in.")

#     if target_role == 'head':
#         cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'head'")
#         head_count = cursor.fetchone()[0]
#         if head_count <= 1:
#             cursor.close()
#             conn.close()
#             raise ValueError("Cannot delete the only remaining Head/Developer account.")

#     # Preserve audit history even after the user account is deleted.
#     cursor.execute(
#         "UPDATE audit_logs SET user_id = NULL WHERE user_id = ?",
#         (target_user_id,)
#     )

#     cursor.execute(
#         "DELETE FROM users WHERE user_id = ?",
#         (target_user_id,)
#     )

#     conn.commit()
    
#     conn.commit()
#     cursor.close()
#     conn.close()
    
    
def delete_system_user(target_user_id, current_user_id_requesting=None):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT role FROM users WHERE user_id = ?",
            (target_user_id,)
        )

        target = cursor.fetchone()

        if not target:
            raise ValueError("User not found")

        target_role = target[0]

        # Prevent deleting the currently logged-in account.
        if (
            current_user_id_requesting
            and str(target_user_id) == str(current_user_id_requesting)
        ):
            raise ValueError(
                "You cannot delete your own account while logged in."
            )

        # Never allow the final Head/Developer account to be deleted.
        if target_role == "head":
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'head'"
            )

            head_count = cursor.fetchone()[0]

            if head_count <= 1:
                raise ValueError(
                    "Cannot delete the only remaining Head/Developer account."
                )

        # Preserve audit history.
        # The account can disappear, but the audit record must remain.
        cursor.execute(
            "UPDATE audit_logs SET user_id = NULL WHERE user_id = ?",
            (target_user_id,)
        )

        # Delete the actual user.
        cursor.execute(
            "DELETE FROM users WHERE user_id = ?",
            (target_user_id,)
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()
    
# ========== DEVICE COONFIGURATION =====================
def get_secureye_config():
    conn = get_connection()
    cursor = conn.cursor()

    keys = {
        "secureye_ip": None,
        "secureye_port": 5005,
        "secureye_timeout": 10,
    }

    for key in keys:
        cursor.execute("""
            SELECT setting_value
            FROM system_settings
            WHERE setting_key = ?
        """, (key,))

        row = cursor.fetchone()

        if row is not None:
            keys[key] = row[0]

    cursor.close()
    conn.close()

    return {
        "ip": keys["secureye_ip"],
        "port": int(keys["secureye_port"]),
        "timeout": int(keys["secureye_timeout"]),
    }


def update_secureye_config(ip, port, timeout):
    if not ip:
        raise ValueError("Secureye IP address is required.")

    try:
        port = int(port)
        timeout = int(timeout)
    except (TypeError, ValueError):
        raise ValueError("Port and timeout must be numbers.")

    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535.")

    if timeout <= 0:
        raise ValueError("Timeout must be greater than 0.")

    conn = get_connection()
    cursor = conn.cursor()

    settings = {
        "secureye_ip": str(ip).strip(),
        "secureye_port": str(port),
        "secureye_timeout": str(timeout),
    }

    for key, value in settings.items():
        cursor.execute("""
            INSERT INTO system_settings (setting_key, setting_value)
            VALUES (?, ?)
            ON CONFLICT(setting_key)
            DO UPDATE SET setting_value = excluded.setting_value
        """, (key, value))

    conn.commit()

    cursor.close()
    conn.close()

    return True 



# ---------------------------------------------------------
# AUDIT LOGS
# ---------------------------------------------------------

def create_audit_log(user_id, action, entity=None, reason=None):
    """
    Create an audit log entry for important system actions.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO audit_logs (
                user_id,
                action,
                entity,
                timestamp,
                reason
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
        """, (
            user_id,
            action,
            entity,
            reason
        ))

        conn.commit()

    finally:
        cursor.close()
        conn.close()


def get_audit_logs(limit=200):
    """
    Return the most recent audit log entries.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                log_id,
                user_id,
                action,
                entity,
                timestamp,
                reason
            FROM audit_logs
            ORDER BY log_id DESC
            LIMIT ?
        """, (int(limit),))

        rows = cursor.fetchall()

        return [
            {
                "log_id": row[0],
                "user_id": row[1],
                "action": row[2],
                "entity": row[3],
                "timestamp": row[4],
                "reason": row[5]
            }
            for row in rows
        ]

    finally:
        cursor.close()
        conn.close()