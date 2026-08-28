import os
import sys
import signal
import time
import threading
import webbrowser
from datetime import datetime
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    url_for,
    send_from_directory,
    session,
    redirect,
)
import secrets
from functools import wraps
from backend.utils.security import decrypt_password

def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

# --- UTILS ---
from backend.utils.security import is_subscription_active, decrypt_date

# ---DATABASE IMPORT---
from backend.database import employee_db, get_connection

# ---DOCUMENT IMPORTS---
from backend.services.documents import (
    get_documents_by_employee, 
    add_document, 
    get_document_by_id, 
    delete_document_record
)

# ---EMPLOYEE SERVICE IMPORT---
from backend.services.employee import (
    add_employee,
    get_all_employees,
    update_monthly_salary,
    update_employee,
    deactivate_employee,
    delete_employee,
    get_employee_by_id
)

# ---ATTENDANCE IMPORT---
from backend.services.attendance import (
    check_in,
    check_out,
    get_attendance_by_employee,
    get_attendance_by_date,
    get_attendance_by_range
)

# ---SALARY IMPORT---
from backend.services.salary import (
    generate_salary,
    get_salary,
    get_salary_records,
    update_salary_details
)

# ---SETTINGS IMPORT---
from backend.services.settings import (
    get_working_hours,
    update_working_hours,
    add_system_user,
    get_all_system_users,
    update_user_password,
    delete_system_user,
    create_audit_log,
    get_audit_logs,
    update_subscription_expiry,
    get_subscription_expiry_encrypted,
    create_database_backup,
    get_demo_mode_status, # NEW
    update_demo_mode,      # NEW
    get_secureye_config,
    update_secureye_config
)


# ---DEVICE API ---
from backend.services.secureye_attendance import sync_secureye


# ---MAPPER FUNCTION import ----
from backend.services.biometric import (
    assign_device_to_employee,
    get_device_mappings,
    remove_device_mapping
)

from backend.devices.secureye import test_secureye_connection


# ---------------------------------------------------------
# PATH CONFIGURATION
# ---------------------------------------------------------
if getattr(sys, 'frozen', False):
    # FROZEN (EXE) MODE
    BASE_DIR = os.path.dirname(sys.executable)
    INTERNAL_DIR = sys._MEIPASS
    template_folder = os.path.join(INTERNAL_DIR, 'templates')
    static_folder = os.path.join(INTERNAL_DIR, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    # DEVELOPMENT MODE
    current_dir = os.path.dirname(os.path.abspath(__file__)) 
    project_root = os.path.abspath(os.path.join(current_dir, '..')) 
    template_folder = os.path.join(project_root, 'templates')
    static_folder = os.path.join(project_root, 'static')
    BASE_DIR = project_root
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)

# ---------------------------------------------------------
# FLASK SESSION CONFIGURATION
# ---------------------------------------------------------
SESSION_SECRET = os.environ.get("HR_SESSION_SECRET")

if not SESSION_SECRET:
    secret_file = os.path.join(BASE_DIR, ".session_secret")

    if os.path.exists(secret_file):
        with open(secret_file, "r", encoding="utf-8") as f:
            SESSION_SECRET = f.read().strip()
    else:
        SESSION_SECRET = secrets.token_hex(32)

        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(SESSION_SECRET)

app.config["SECRET_KEY"] = SESSION_SECRET
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'UPLOADS')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize DB (and fix passwords)
employee_db()


#-------------------------
# DEVICE ROUTES
# -------------------------
@app.route("/attendance/device-sync", methods=["POST"])
def device_sync():

    try:

        result = sync_secureye()

        return {
            "success": True,
            **result
        }, 200

    except Exception as exc:

        print("Secureye sync error:", exc)

        return {
            "success": False,
            "error": str(exc)
        }, 500

# -------------------------
# API ATTENDANCE ROUTES
# -------------------------
@app.route("/api/attendance", methods=["GET"])
def api_attendance():
    try:
        target_date = request.args.get("date")

        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        records = get_attendance_by_date(target_date)

        return jsonify({
            "success": True,
            "date": target_date,
            "records": records
        })

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 500


@app.route("/api/attendance/range", methods=["GET"])
def api_attendance_range():
    try:
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")

        if not start_date or not end_date:
            return jsonify({
                "success": False,
                "error": "start_date and end_date are required."
            }), 400

        records = get_attendance_by_range(
            start_date,
            end_date
        )

        return jsonify({
            "success": True,
            "start_date": start_date,
            "end_date": end_date,
            "records": records
        })

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 500



# -------------------------
# MAPPING  ROUTES
# -------------------------
        
@app.route("/biometric/mappings", methods=["GET"])
def get_biometric_mappings_route():
    try:
        mappings = get_device_mappings()

        result = []

        for row in mappings:
            result.append({
                "device_id": row[0],
                "device_card_id": row[1],
                "employee_id": row[2],
                "name": row[3],
                "role": row[4]
            })

        return jsonify({
            "success": True,
            "mappings": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500 


@app.route("/biometric/mapping", methods=["POST"])
def assign_biometric_mapping_route():
    data = request.json or {}

    device_card_id = data.get("device_card_id")
    employee_id = data.get("employee_id")

    if device_card_id is None or employee_id is None:
        return jsonify({
            "success": False,
            "error": "Device Card ID and Employee ID are required."
        }), 400

    try:
        device_card_id = int(device_card_id)
        employee_id = int(employee_id)

        result = assign_device_to_employee(
            device_card_id=device_card_id,
            employee_id=employee_id
        )

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


@app.route("/biometric/mapping", methods=["DELETE"])
def remove_biometric_mapping_route():
    data = request.json or {}

    device_card_id = data.get("device_card_id")

    if device_card_id is None:
        return jsonify({
            "success": False,
            "error": "Device Card ID is required."
        }), 400

    try:
        result = remove_device_mapping(
            int(device_card_id)
        )

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400




# -------------------------
# VIEW ROUTES
# -------------------------
@app.route("/")
def home():
    encrypted_expiry = get_subscription_expiry_encrypted()
    expiry_date = None
    if encrypted_expiry:
        expiry_date = decrypt_date(encrypted_expiry)
    
    # Pass demo mode status to template
    demo_mode = get_demo_mode_status()
    return render_template("login.html", expiry_date=expiry_date, demo_mode=demo_mode)

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({
                "error": "AUTH_REQUIRED",
                "message": "Please login again."
            }), 401

        return view_func(*args, **kwargs)

    return wrapped_view


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if "user_id" not in session:
                return jsonify({
                    "error": "AUTH_REQUIRED",
                    "message": "Please login again."
                }), 401

            if session.get("role") not in allowed_roles:
                return jsonify({
                    "error": "FORBIDDEN",
                    "message": "You do not have permission."
                }), 403

            return view_func(*args, **kwargs)

        return wrapped_view

    return decorator

def system_user_permission_required(action):
    """
    System user management permissions.

    head = Developer / highest authority
    admin = can manage users, but not admin/head
    user = no system-user management
    """

    @wraps(action)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({
                "error": "AUTH_REQUIRED",
                "message": "Please login again."
            }), 401

        role = session.get("role")

        # Developer / Head has full authority
        if role == "head":
            return action(*args, **kwargs)

        # Admin has restricted authority
        if role == "admin":
            return action(*args, **kwargs)

        return jsonify({
            "error": "FORBIDDEN",
            "message": "You do not have permission."
        }), 403

    return wrapped

@app.route("/dashboard")
@login_required
def dashboard():
    # Pass demo mode status to template
    demo_mode = get_demo_mode_status()
    return render_template("dashboard.html", demo_mode=demo_mode)

# -------------------------
# AUTH ROUTES
# -------------------------
@app.route("/login", methods=["POST"])
def login_route():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, role, password_hash
        FROM users
        WHERE username = ?
    """, (username,))

    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    user_id, role, stored_encrypted_pw = user

    decrypted_pw = decrypt_password(stored_encrypted_pw)

    if decrypted_pw != password:
        return jsonify({"error": "Invalid credentials"}), 401

    if role != 'head':
        # A new installation has no subscription expiry.
        # Normal users cannot login until the developer activates it.
        encrypted_expiry = get_subscription_expiry_encrypted()

        if not encrypted_expiry:
            return jsonify({
                "error": "SUBSCRIPTION EXPIRED",
                "message": "Subscription is not activated. Please contact the Developer."
            }), 403

        is_active, expiry_str = is_subscription_active(encrypted_expiry)

        if not is_active:
            return jsonify({
                "error": "SUBSCRIPTION EXPIRED",
                "message": f"License expired on {expiry_str}. Please contact the Developer to renew."
            }), 403

    session.clear()

    session["user_id"] = user_id
    session["role"] = role
    
    create_audit_log(
        user_id=user_id,
        action="LOGIN",
        entity="AUTH",
        reason="Successful login"
    )

    return jsonify({
        "success": True,
        "user_id": user_id,
        "role": role
    })
    
    
    
@app.route("/auth/session", methods=["GET"])
@login_required
def get_current_session():
    return jsonify({
        "authenticated": True,
        "user_id": session["user_id"],
        "role": session["role"]
    })

@app.route("/logout", methods=["POST"])
def logout():
    user_id = session.get("user_id")

    if user_id:
        create_audit_log(
            user_id=user_id,
            action="LOGOUT",
            entity="AUTH",
            reason="User logged out"
        )

    session.clear()

    return jsonify({
        "success": True,
        "message": "Logged out successfully."
    })


# -------------------------
# EMPLOYEE ROUTES
# -------------------------
@app.route("/employee/add", methods=["POST"])
def add_employee_route():
    data = request.json or {}

    try:
        add_employee(
            name=data.get("name"),
            role=data.get("role"),
            phone=data.get("phone"),
            address=data.get("address"),
            monthly_salary=data.get("monthly_salary"),

            salary_type=data.get(
                "salary_type",
                "monthly"
            ),

            daily_hours=data.get(
                "daily_hours",
                8
            ),

            expected_check_in=data.get(
                "expected_check_in"
            ),

            expected_check_out=data.get(
                "expected_check_out"
            ),

            late_grace_minutes=data.get(
                "late_grace_minutes",
                0
            ),

            overtime_enabled=data.get(
                "overtime_enabled",
                0
            ),

            overtime_rate=data.get(
                "overtime_rate",
                1.5
            ),
            working_days=data.get(
                "working_days",
                26
            ),
            grace_holidays=data.get(
                "grace_holidays",
                0
            )
        )

        return jsonify({
            "message": "Employee added successfully"
        })

    except Exception as e:
        return jsonify({
            "message": str(e)
        }), 400

@app.route("/employees", methods=["GET"])
def get_employees_route():
    employees = get_all_employees()
    result = []
    for emp in employees:
            result.append({
        "id": emp[0],
        "name": emp[1],
        "role": emp[2],
        "phone": emp[3],
        "address": emp[4],
        "monthly_salary": emp[5],
        "status": emp[6]
    })
    return jsonify(result)

@app.route("/employee/update", methods=["POST"])
@role_required("admin", "head")
def update_employee_route():
    data = request.json or {}

    try:
        update_employee(
            employee_id=data.get("employee_id"),
            name=data.get("name"),
            role=data.get("role"),
            phone=data.get("phone"),
            address=data.get("address"),
            monthly_salary=data.get("monthly_salary"),
            salary_type=data.get("salary_type", "monthly"),
            daily_hours=data.get("daily_hours", 8),
            working_days=data.get("working_days", 26),
            grace_holidays=data.get("grace_holidays", 0),
            expected_check_in=data.get("expected_check_in"),
            expected_check_out=data.get("expected_check_out"),
            late_grace_minutes=data.get("late_grace_minutes", 0),
            overtime_enabled=data.get("overtime_enabled", 0),
            overtime_rate=data.get("overtime_rate", 1)
        )

        return jsonify({
            "success": True,
            "message": "Employee updated successfully"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

@app.route("/employee/update_salary", methods=["POST"])
def update_salary_route():
    data = request.json
    update_monthly_salary(data.get("employee_id"), data.get("monthly_salary"))
    return jsonify({"message": "Salary updated successfully"})

@app.route("/employee/deactivate", methods=["POST"])
def deactivate_employee_route():
    data = request.json
    deactivate_employee(data.get("employee_id"))
    return jsonify({"message": "Employee deactivated"})

@app.route("/employee/activate", methods=["POST"])
def activate_employee_route():
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE employees
        SET status = 'active'
        WHERE employee_id = ?
    """, (data.get("employee_id"),))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Employee activated"})

@app.route("/employee/delete", methods=["POST"])
def delete_employee_route():
    data = request.json
    try:
        delete_employee(data.get("employee_id"))
        return jsonify({"message": "Employee permanently deleted"})
    except Exception as e:
        return jsonify({"message": str(e)}), 400

@app.route("/employee/<int:employee_id>", methods=["GET"])
def get_employee_profile(employee_id):
    emp = get_employee_by_id(employee_id)
    if not emp:
        return jsonify({"error": "Employee not found"}), 404
    return jsonify({
    "id": emp[0],
    "name": emp[1],
    "role": emp[2],
    "phone": emp[3],
    "address": emp[4],
    "monthly_salary": emp[5],
    "hourly_rate": emp[6],
    "salary_type": emp[7],
    "daily_hours": emp[8],
    "working_days": emp[9],
    "grace_holidays": emp[10],
    "expected_check_in": emp[11],
    "expected_check_out": emp[12],
    "late_grace_minutes": emp[13],
    "overtime_enabled": emp[14],
    "overtime_rate": emp[15],
    "status": emp[16]
})
    
    
    
# -------------------------
# ATTENDANCE ROUTES
# -------------------------
@app.route("/attendance/checkin", methods=["POST"])
def checkin_route():
    data = request.json
    manual_time = data.get("manual_time")
    manual_date = data.get("manual_date")
    role = data.get("role")

    if (manual_time or manual_date) and role not in ['head', 'admin']:
        return jsonify({"message": "Unauthorized: Only Admin/Head can set manual time or date"}), 403

    try:
        check_in(data.get("employee_id"), custom_time=manual_time, target_date=manual_date)
        return jsonify({"message": "Check-in successful"})
    except Exception as e:
        return jsonify({"message": str(e)}), 400

@app.route("/attendance/checkout", methods=["POST"])
def checkout_route():
    data = request.json
    manual_time = data.get("manual_time")
    manual_date = data.get("manual_date")
    role = data.get("role")

    if (manual_time or manual_date) and role not in ['head', 'admin']:
        return jsonify({"message": "Unauthorized: Only Admin/Head can set manual time or date"}), 403

    try:
        check_out(data.get("employee_id"), custom_time=manual_time, target_date=manual_date)
        return jsonify({"message": "Check-out successful"})
    except Exception as e:
        return jsonify({"message": str(e)}), 400

@app.route("/attendance/<int:employee_id>", methods=["GET"])
def attendance_view_route(employee_id):
    records = get_attendance_by_employee(employee_id)

    result = []

    for r in records:
        result.append({
            "date": r[0],
            "check_in": r[1],
            "check_out": r[2],
            "worked_hours": r[3],
            "worked_minutes": r[4]
        })

    return jsonify(result)

# -------------------------
# SALARY ROUTES
# -------------------------
@app.route("/salary/generate", methods=["POST"])
def generate_salary_route():
    data = request.json
    try:
        generate_salary(data.get("employee_id"), data.get("month"), data.get("role"))
        return jsonify({"message": "Salary generated", "status": "new"})
    except Exception as e:
        if "already generated" in str(e):
            return jsonify({"message": "Salary already generated", "status": "exists"}), 200
        return jsonify({"message": str(e), "status": "error"}), 400

@app.route("/salary/view", methods=["GET"])
def get_salary_route():
    employee_id = request.args.get("employee_id", type=int)
    month = request.args.get("month")

    if employee_id is None or not month:
        return jsonify({
            "error": "employee_id and month are required"
        }), 400

    salary = get_salary(employee_id, month)

    if not salary:
        return jsonify({"error": "Salary not found"}), 404

    return jsonify(salary)


@app.route("/salary/records", methods=["GET"])
def get_salary_records_route():
    employee_id = request.args.get("employee_id", type=int)
    month = request.args.get("month")

    try:
        records = get_salary_records(
            employee_id=employee_id,
            month=month
        )

        return jsonify({
            "success": True,
            "count": len(records),
            "records": records
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/salary/update", methods=["POST"])
def update_generated_salary_route():
    data = request.json
    try:
        update_salary_details(
            data.get("employee_id"), 
            data.get("month"), 
            data.get("total_salary"),
            data.get("role") 
        )
        return jsonify({"message": "Salary updated successfully"})
    except Exception as e:
        return jsonify({"message": str(e)}), 400

# -------------------------
# DOCUMENT ROUTES
# -------------------------
@app.route("/employee/<int:employee_id>/documents", methods=["GET"])
def get_employee_documents_route(employee_id):
    docs = get_documents_by_employee(employee_id)
    result = []
    for d in docs:
        doc_id = d[0]
        file_path_db = d[3]
        # Resolve path relative to the persistent UPLOAD folder
        abs_path = os.path.join(BASE_DIR, file_path_db)
        if not os.path.exists(abs_path):
            pass 
        result.append({
            "doc_id": d[0],
            "doc_type": d[1],
            "adhaar_no": d[2],
            "file_path": d[3],
            "uploaded_at": d[4]
        })
    return jsonify(result)

@app.route("/employee/<int:employee_id>/documents", methods=["POST"])
def upload_employee_document(employee_id):
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    doc_type = request.form.get("doc_type")
    adhaar_no = request.form.get("adhaar_no")
    if file.filename == "":
        return jsonify({"error": "Empty file"}), 400
    
    # Save physical file
    emp_folder_name = f"employee_{employee_id}"
    emp_folder = os.path.join(UPLOAD_FOLDER, emp_folder_name)
    os.makedirs(emp_folder, exist_ok=True)
    
    file_path = os.path.join(emp_folder, file.filename)
    file.save(file_path)
    
    # Save DB record (Relative path for portability)
    db_path = os.path.join("UPLOADS", emp_folder_name, file.filename)
    add_document(employee_id, doc_type, adhaar_no, db_path)
    return jsonify({"message": "Document uploaded successfully"})

@app.route("/documents/delete", methods=["POST"])
def delete_document_route_api():
    data = request.json
    doc_id = data.get("doc_id")
    doc = get_document_by_id(doc_id)
    if not doc:
        return jsonify({"message": "Document not found"}), 404
    file_path_db = doc[0]
    delete_document_record(doc_id)
    try:
        abs_path = os.path.join(BASE_DIR, file_path_db)
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception as e:
        print(f"Error deleting file: {e}")
    return jsonify({"message": "Document deleted successfully"})

@app.route('/UPLOADS/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# -------------------------
# SECUREYE DEVICE CONFIG
# -------------------------

def require_developer():
    """
    Developer-only authorization.

    The current application uses the 'head' role
    as the highest-level/developer account.
    """

    user_id = request.headers.get("X-User-ID")

    if not user_id:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return row is not None and row[0] == "head"


@app.route("/settings/secureye", methods=["GET"])
def get_secureye_settings_route():

    if not require_developer():
        return jsonify({
            "success": False,
            "error": "Developer access required."
        }), 403

    try:
        config = get_secureye_config()

        return jsonify({
            "success": True,
            **config
        })

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 500


@app.route("/settings/secureye", methods=["POST"])
def update_secureye_settings_route():

    if not require_developer():
        return jsonify({
            "success": False,
            "error": "Developer access required."
        }), 403

    try:
        data = request.get_json() or {}

        ip = data.get("ip")
        port = data.get("port")
        timeout = data.get("timeout")

        update_secureye_config(
            ip,
            port,
            timeout
        )

        return jsonify({
            "success": True,
            "message": "Secureye configuration saved."
        })

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400     

@app.route("/settings/secureye/test", methods=["POST"])
def test_secureye_connection_route():

    if not require_developer():
        return jsonify({
            "success": False,
            "error": "Developer access required."
        }), 403

    try:
        result = test_secureye_connection()

        return jsonify(result), 200

    except Exception as exc:
        print("Secureye connection test error:", exc)

        return jsonify({
            "success": False,
            "error": str(exc)
        }), 500



# -------------------------
# SETTINGS & RENEWAL ROUTES
# -------------------------
@app.route("/settings/hours", methods=["GET"])
def get_hours_route():
    try:
        hours = get_working_hours()
        return jsonify({"hours": hours})
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route("/settings/hours", methods=["POST"])
def update_hours_route():
    try:
        update_working_hours(request.json.get("hours"))
        return jsonify({"message": "Working hours updated"})
    except Exception as e:
        return jsonify({"message": str(e)}), 400
    

# @app.route("/settings/working-days", methods=["GET"])
# def get_working_days_route():
#     try:
#         days = get_working_days()

#         return jsonify({
#             "success": True,
#             "days": days
#         })

#     except Exception as e:
#         print("Get working days error:", e)

#         return jsonify({
#             "success": False,
#             "message": str(e)
#         }), 500


# @app.route("/settings/working-days", methods=["POST"])
# def update_working_days_route():
#     try:
#         data = request.get_json() or {}

#         days = data.get("days")

#         update_working_days(days)

#         return jsonify({
#             "success": True,
#             "message": "Working days updated successfully"
#         })

#     except Exception as e:
#         print("Update working days error:", e)

#         return jsonify({
#             "success": False,
#             "message": str(e)
#         }), 400



@app.route("/settings/backup", methods=["POST"])
def backup_db_route():
    try:
        filename = create_database_backup()
        return jsonify({"message": f"Backup created successfully: {filename}"})
    except Exception as e:
        return jsonify({"message": str(e)}), 500

# @app.route("/users/add", methods=["POST"])
# def add_user_route():
#     data = request.json
#     try:
#         add_system_user(data.get("username"), data.get("password"), data.get("role"))
#         return jsonify({"message": "User added successfully"})
#     except Exception as e:
#         return jsonify({"message": str(e)}), 400


@app.route("/users/add", methods=["POST"])
@login_required
def add_user_route():
    data = request.json or {}

    username = data.get("username")
    password = data.get("password")
    role = data.get("role")

    current_role = session.get("role")

    # USER cannot create accounts
    if current_role == "user":
        return jsonify({
            "success": False,
            "message": "You do not have permission to create users."
        }), 403

    # ADMIN can create USER only
    if current_role == "admin" and role != "user":
        return jsonify({
            "success": False,
            "message": "Admins can create User accounts only."
        }), 403

    # DEVELOPER / HEAD can create anything
    if current_role == "head":
        if role not in ("user", "admin", "head"):
            return jsonify({
                "success": False,
                "message": "Invalid role."
            }), 400

    try:
        add_system_user(
            username,
            password,
            role
        )
        create_audit_log(
            user_id=session.get("user_id"),
            action="CREATE_USER",
            entity=f"user:{username}",
            reason=f"Created system user with role {role}"
        )

        return jsonify({
            "success": True,
            "message": "User added successfully."
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400
        
        
# @app.route("/users", methods=["GET"])
# def get_users_route():
#     try:
#         users = get_all_system_users()
#         result = [{"id": u[0], "username": u[1], "password": u[2], "role": u[3]} for u in users]
#         return jsonify(result)
#     except Exception as e:
#         return jsonify({"message": str(e)}), 500

@app.route("/users", methods=["GET"])
@login_required
def get_users_route():

    current_role = session.get("role")

    if current_role not in ("admin", "head"):
        return jsonify({
            "success": False,
            "message": "You do not have permission."
        }), 403

    try:
        users = get_all_system_users()

        result = []

        for u in users:
            user_id = u[0]
            username = u[1]
            password = u[2]
            role = u[3]

            # Developer sees everyone.
            if current_role == "head":
                result.append({
                    "id": user_id,
                    "username": username,
                    "password": password,
                    "role": role
                })
                continue

            # Admin sees only Users and Admins.
            if current_role == "admin" and role in ("user", "admin"):
                result.append({
                    "id": user_id,
                    "username": username,
                    "password": password,
                    "role": role
                })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500



@app.route("/users/password", methods=["POST"])
@login_required
def update_password_route():

    data = request.json or {}

    target_user_id = data.get("user_id")
    new_password = data.get("password")

    current_user_id = session.get("user_id")
    current_role = session.get("role")

    if not target_user_id or not new_password:
        return jsonify({
            "success": False,
            "message": "User ID and password are required."
        }), 400

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, username, role
        FROM users
        WHERE user_id = ?
    """, (target_user_id,))

    target = cursor.fetchone()

    cursor.close()
    conn.close()

    if not target:
        return jsonify({
            "success": False,
            "message": "User not found."
        }), 404

    target_user_id_db = target[0]
    target_username = target[1]
    target_role = target[2]

    # # ---------------------------------------------------------
    # # PASSWORD PERMISSIONS
    # #
    # # USER
    # # -> Can change own password
    # # -> Can change User passwords
    # # -> Cannot change Admin/Developer
    # #
    # # ADMIN
    # # -> Can change own password
    # # -> Can change User passwords
    # # -> Can change Admin passwords
    # # -> Cannot change Developer
    # #
    # # DEVELOPER / HEAD
    # # -> Can change everyone's password
    # # ---------------------------------------------------------

    # if current_role == "head":
    #     # Developer has full password control.
    #     pass

    # elif current_role == "admin":
    #     # Admin can change:
    #     # 1. Own password
    #     # 2. Any User password
    #     # 3. Any Admin password
    #     if target_role in ("user", "admin"):
    #         pass
    #     else:
    #         return jsonify({
    #             "success": False,
    #             "message": "Admins cannot change Developer passwords."
    #         }), 403

    # elif current_role == "user":
    #     # User can change:
    #     # 1. Own password
    #     # 2. Other User passwords
    #     if target_role == "user":
    #         pass
    #     else:
    #         return jsonify({
    #             "success": False,
    #             "message": "Users can only change User passwords."
    #         }), 403

    # else:
    #     return jsonify({
    #         "success": False,
    #         "message": "Invalid account role."
    #     }), 403


# ---------------------------------------------------------
# PASSWORD PERMISSIONS
# ---------------------------------------------------------

    if current_role == "head":

        # Developer can change everybody.
        pass


    elif current_role == "admin":

        # Admin can change own password.
        if target_user_id_db == current_user_id:
            pass

        # Admin can change normal User passwords.
        elif target_role == "user":
            pass

        # Admin cannot change Developer password.
        else:
            return jsonify({
                "success": False,
                "error": "Admins cannot change Developer passwords."
            }), 403


    elif current_role == "user":

        # User can change ONLY their own password.
        if target_user_id_db != current_user_id:
            return jsonify({
                "success": False,
                "error": "Users can only change their own password."
            }), 403


    else:

        return jsonify({
            "success": False,
            "error": "Unauthorized."
        }), 403



    # ---------------------------------------------------------
    # ACTUALLY UPDATE PASSWORD
    # ---------------------------------------------------------

    try:
        update_user_password(
            target_user_id_db,
            new_password
        )
        create_audit_log(
            user_id=current_user_id,
            action="CHANGE_PASSWORD",
            entity=f"user:{target_user_id_db}",
            reason=f"Password changed for {target_username}"
        )

        return jsonify({
            "success": True,
            "message": f"Password updated for {target_username}."
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# @app.route("/users/delete", methods=["POST"])
# def delete_user_route():
#     data = request.json
#     try:
#         delete_system_user(data.get("user_id"), data.get("current_user_id"))
#         return jsonify({"message": "User deleted and IDs reordered"})
#     except Exception as e:
#         return jsonify({"message": str(e)}), 400

@app.route("/users/delete", methods=["POST"])
@login_required
def delete_user_route():

    data = request.json or {}

    target_user_id = data.get("user_id")
    current_user_id = session.get("user_id")
    current_role = session.get("role")

    if not target_user_id:
        return jsonify({
            "success": False,
            "message": "User ID is required."
        }), 400

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE user_id = ?
    """, (target_user_id,))

    target = cursor.fetchone()

    cursor.close()
    conn.close()

    if not target:
        return jsonify({
            "success": False,
            "message": "User not found."
        }), 404

    target_role = target[0]

    # User cannot delete anyone
    if current_role == "user":
        return jsonify({
            "success": False,
            "message": "Users cannot delete accounts."
        }), 403

    # Admin can delete Users only
    if current_role == "admin" and target_role != "user":
        return jsonify({
            "success": False,
            "message": "Admins can delete User accounts only."
        }), 403

    # Nobody can delete their own logged-in account
    if str(target_user_id) == str(current_user_id):
        return jsonify({
            "success": False,
            "message": "You cannot delete your own account while logged in."
        }), 403

    try:
        delete_system_user(
            target_user_id,
            current_user_id
        )
        
        create_audit_log(
            user_id=current_user_id,
            action="DELETE_USER",
            entity=f"user:{target_user_id}",
            reason=f"Deleted system user with role {target_role}"
        )

        return jsonify({
            "success": True,
            "message": "User deleted successfully."
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@app.route("/settings/renewal", methods=["GET"])
def get_renewal_route():
    enc = get_subscription_expiry_encrypted()
    if enc:
        return jsonify({"date": decrypt_date(enc)})
    return jsonify({"date": None})

@app.route("/settings/renewal", methods=["POST"])
def update_renewal_route():
    data = request.json
    try:
        update_subscription_expiry(data.get("date"))
        return jsonify({"message": "Subscription renewed successfully"})
    except Exception as e:
        return jsonify({"message": str(e)}), 400
    
    
# @app.route("/api/settings/working-days", methods=["GET"])
# def api_get_working_days():
#     try:
#         return jsonify({
#             "success": True,
#             "days": get_working_days()
#         })
#     except Exception as exc:
#         return jsonify({
#             "success": False,
#             "error": str(exc)
#         }), 500

# @app.route("/api/settings/working-days", methods=["POST"])
# def api_update_working_days():
#     try:
#         data = request.get_json() or {}

#         days = data.get("days", [])

#         update_working_days(days)

#         return jsonify({
#             "success": True,
#             "message": "Working days updated successfully."
#         })

#     except Exception as exc:
#         return jsonify({
#             "success": False,
#             "error": str(exc)
#         }), 500
        
        
        
@app.route("/audit-logs", methods=["GET"])
@login_required
def audit_logs_route():
    if session.get("role") != "head":
        return jsonify({
            "success": False,
            "message": "Developer access required."
        }), 403

    try:
        limit = request.args.get("limit", 200, type=int)
        limit = max(1, min(limit, 500))

        return jsonify({
            "success": True,
            "logs": get_audit_logs(limit)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# -------------------------
# DEMO MODE ROUTES (NEW)
# -------------------------
@app.route("/settings/demo", methods=["GET"])
@role_required("head")
def get_demo_route():
    status = get_demo_mode_status()
    return jsonify({
        "success": True,
        "enabled": status
    })


@app.route("/settings/demo", methods=["POST"])
@role_required("head")
def update_demo_route():
    data = request.get_json() or {}

    try:
        update_demo_mode(data.get("enabled"))

        return jsonify({
            "success": True,
            "message": "Demo mode updated successfully."
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# -------------------------
# SHUTDOWN ROUTE
# -------------------------
@app.route("/shutdown", methods=["POST"])
def shutdown_server():
    """Completely terminates the Flask application and PyInstaller process."""
    try:
        def kill_process():
            time.sleep(1)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=kill_process).start()
        
        return jsonify({"message": "Server shutting down..."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # threading.Timer(1.0, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    # ---------------------------------------------------------
    # SESSION CONFIGURATION
    # ---------------------------------------------------------

