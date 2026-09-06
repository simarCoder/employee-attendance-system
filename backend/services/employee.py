from backend.database import get_connection


DEFAULT_WORKING_WEEKDAYS = "0,1,2,3,4,5"


def normalize_working_weekdays(value):
    """
    Convert employee weekly schedule into normalized DB text.

    Accepted examples:
        [0, 1, 2, 3, 4, 5]
        "0,1,2,3,4,5"

    Returns:
        "0,1,2,3,4,5"
    """

    if value is None:
        return DEFAULT_WORKING_WEEKDAYS

    if isinstance(value, str):
        raw_values = [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]
    else:
        raw_values = list(value)

    try:
        weekdays = sorted({
            int(day)
            for day in raw_values
        })
    except (TypeError, ValueError):
        raise ValueError("Invalid working weekday selection")

    if not weekdays:
        raise ValueError("Select at least one working weekday")

    if any(day < 0 or day > 6 for day in weekdays):
        raise ValueError(
            "Working weekdays must be between Monday (0) and Sunday (6)"
        )

    return ",".join(
        str(day)
        for day in weekdays
    )


def calculate_hourly_rate(
    monthly_salary,
    daily_hours,
    working_days_per_month=26
):
    monthly_salary = float(monthly_salary or 0)
    daily_hours = float(daily_hours or 0)
    working_days_per_month = int(working_days_per_month or 0)

    divisor = daily_hours * working_days_per_month

    if divisor <= 0:
        return 0.0

    return round(monthly_salary / divisor, 2)
# def calculate_hourly_rate(
#     monthly_salary,
#     daily_hours,
#     working_days_per_month=26
# ):
#     monthly_salary = float(monthly_salary or 0)
#     daily_hours = float(daily_hours or 0)
#     working_days_per_month = int(working_days_per_month or 0)

#     divisor = daily_hours * working_days_per_month

#     if divisor <= 0:
#         return 0.0

#     return round(monthly_salary / divisor, 2)

# def calculate_hourly_rate(monthly_salary):
#     today = date.today()
#     days_in_month = calendar.monthrange(today.year, today.month)[1]
    
#     # Fetch dynamic hours from DB
#     required_hours = get_daily_required_hours()
    
#     # Prevent division by zero
#     divisor = days_in_month * required_hours
#     if divisor == 0: return 0
#     return round(monthly_salary / divisor, 2)

# NEW: Helper to refresh everyone's rate when settings change
def recalculate_all_employee_rates():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            employee_id,
            monthly_salary,
            daily_hours,
            working_days,
            salary_type
        FROM employees
    """)

    employees = cursor.fetchall()

    for emp in employees:
        (
            emp_id,
            salary,
            daily_hours,
            working_days,
            salary_type
        ) = emp

        if salary_type == "monthly":
            new_rate = calculate_hourly_rate(
                salary,
                daily_hours,
                working_days
            )
        else:
            new_rate = float(salary or 0)

        cursor.execute("""
            UPDATE employees
            SET hourly_rate = ?
            WHERE employee_id = ?
        """, (
            new_rate,
            emp_id
        ))

    conn.commit()
    cursor.close()
    conn.close()

# def add_employee(name, role, phone, address, monthly_salary):
#     if not name or monthly_salary is None:
#         raise ValueError("Name and monthly salary are required")

#     monthly_salary = float(monthly_salary)
#     hourly_rate = calculate_hourly_rate(monthly_salary)

#     conn = get_connection()
#     cursor = conn.cursor()

#     cursor.execute("""
#         INSERT INTO employees (name, role, phone, address, monthly_salary, hourly_rate)
#         VALUES (?, ?, ?, ?, ?, ?)
#     """, (name, role, phone, address, monthly_salary, hourly_rate))

#     conn.commit()
#     cursor.close()
#     conn.close()

def add_employee(
    name,
    role,
    phone,
    address,
    monthly_salary,
    salary_type="monthly",
    daily_hours=8,
    expected_check_in=None,
    expected_check_out=None,
    late_grace_minutes=0,
    overtime_enabled=0,
    overtime_rate=1.5,
    working_days=26,  # legacy, kept temporarily for route compatibility
    grace_holidays=0,
    working_weekdays=None,
):
    if not name:
        raise ValueError("Name is required")

    if monthly_salary is None:
        raise ValueError("Salary is required")

    monthly_salary = float(monthly_salary)

    daily_hours = float(daily_hours or 8)
    late_grace_minutes = int(late_grace_minutes or 0)
    overtime_enabled = int(bool(overtime_enabled))
    overtime_rate = float(overtime_rate or 1.5)
    working_days = float(working_days or 26)
    grace_holidays = float(grace_holidays or 0)
    working_weekdays = normalize_working_weekdays(
                                                    working_weekdays
                                                )

    if salary_type not in ("monthly", "hourly"):
        raise ValueError("Invalid salary type")

    if daily_hours <= 0:
        raise ValueError("Daily hours must be greater than 0")

    if late_grace_minutes < 0:
        raise ValueError("Late grace cannot be negative")

    if overtime_rate <= 0:
        raise ValueError("Overtime rate must be greater than 0")

    if salary_type == "monthly":
        hourly_rate = calculate_hourly_rate(
            monthly_salary,
            daily_hours,
            working_days
        )
    else:
        hourly_rate = monthly_salary
    
    if working_days <= 0 or working_days > 31:
        raise ValueError("Working days must be between 1 and 31")

    if grace_holidays < 0:
        raise ValueError("Grace holidays cannot be negative")
    
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
                    INSERT INTO employees (
                        name,
                        role,
                        phone,
                        address,
                        monthly_salary,
                        hourly_rate,
                        salary_type,
                        daily_hours,
                        expected_check_in,
                        expected_check_out,
                        late_grace_minutes,
                        overtime_enabled,
                        overtime_rate,
                        working_days,
                        working_weekdays,
                        grace_holidays
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    role,
                    phone,
                    address,
                    monthly_salary,
                    hourly_rate,
                    salary_type,
                    daily_hours,
                    expected_check_in,
                    expected_check_out,
                    late_grace_minutes,
                    overtime_enabled,
                    overtime_rate,
                    working_days,
                    working_weekdays,
                    grace_holidays
                ))

    conn.commit()

    cursor.close()
    conn.close()


# def get_all_employees():
#     conn = get_connection()
#     cursor = conn.cursor()
#     cursor.execute("""
#         SELECT employee_id, name, role, phone, address, monthly_salary, status
#         FROM employees
#     """)
#     rows = cursor.fetchall()
#     cursor.close()
#     conn.close()
#     return rows

def get_all_employees():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT employee_id, name, role, phone, address, monthly_salary, status
        FROM employees
        ORDER BY employee_id ASC
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows

# def get_employee_by_id(employee_id):
#     conn = get_connection()
#     cursor = conn.cursor()
#     cursor.execute("""
#         SELECT employee_id, name, role, phone, address, monthly_salary, status
#         FROM employees
#         WHERE employee_id = ?
#     """, (employee_id,))
#     row = cursor.fetchone()
#     cursor.close()
#     conn.close()
#     return row

def get_employee_by_id(employee_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            employee_id,
            name,
            role,
            phone,
            address,
            monthly_salary,
            hourly_rate,
            salary_type,
            daily_hours,
            working_days,
            grace_holidays,
            expected_check_in,
            expected_check_out,
            late_grace_minutes,
            overtime_enabled,
            overtime_rate,
            status
        FROM employees
        WHERE employee_id = ?
    """, (employee_id,))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return row


def update_monthly_salary(employee_id, new_monthly_salary):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
                    SELECT
                        daily_hours,
                        working_days
                    FROM employees
                    WHERE employee_id = ?
                """, (employee_id,))

    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        raise ValueError("Employee not found")

    daily_hours = float(row[0] or 8)
    working_days = float(row[1] or 26)

    hourly_rate = calculate_hourly_rate(
        new_monthly_salary,
        daily_hours,
        working_days,
    )

    cursor.execute("""
        UPDATE employees
        SET monthly_salary = ?,
            hourly_rate = ?
        WHERE employee_id = ?
    """, (
        float(new_monthly_salary),
        hourly_rate,
        employee_id
    ))

    conn.commit()

    cursor.close()
    conn.close()

def update_employee(
    employee_id,
    name,
    role,
    phone,
    address,
    monthly_salary,
    salary_type="monthly",
    daily_hours=None,
    expected_check_in=None,
    working_days=26,
    expected_check_out=None,
    late_grace_minutes=0,
    overtime_enabled=0,
    overtime_rate=1,
    grace_holidays=0,
    working_weekdays=None,
):
    if not name:
        raise ValueError("Name is required")

    if monthly_salary is None:
        raise ValueError("Salary is required")

    monthly_salary = float(monthly_salary)

    # Preserve the existing value if an older caller omits daily_hours.
    # Updates must never silently overwrite it with 8.
    if daily_hours is None or daily_hours == "":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT daily_hours FROM employees WHERE employee_id = ?",
            (employee_id,),
        )
        existing_employee = cursor.fetchone()
        cursor.close()
        conn.close()

        if not existing_employee:
            raise ValueError("Employee not found")

        daily_hours = existing_employee[0]

    daily_hours = float(daily_hours)
    late_grace_minutes = int(late_grace_minutes or 0)
    overtime_enabled = int(bool(overtime_enabled))
    overtime_rate = float(overtime_rate or 1)
    working_days = float(working_days or 26)
    grace_holidays = float(grace_holidays or 0)
    working_weekdays = normalize_working_weekdays(
        working_weekdays
    )

    if working_days <= 0 or working_days > 31:
        raise ValueError("Working days must be between 1 and 31")

    if grace_holidays < 0:
        raise ValueError("Grace holidays cannot be negative")

    if salary_type not in ("monthly", "hourly"):
        raise ValueError("Invalid salary type")

    if daily_hours <= 0:
        raise ValueError("Daily hours must be greater than 0")

    if late_grace_minutes < 0:
        raise ValueError("Late grace cannot be negative")

    if overtime_rate <= 0:
        raise ValueError("Overtime rate must be greater than 0")

    if salary_type == "monthly":
        hourly_rate = calculate_hourly_rate(
            monthly_salary,
            daily_hours,
            working_days
        )
    else:
        hourly_rate = monthly_salary

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE employees
        SET
            name = ?,
            role = ?,
            phone = ?,
            address = ?,
            monthly_salary = ?,
            hourly_rate = ?,
            salary_type = ?,
            daily_hours = ?,
            working_days = ?,
            working_weekdays = ?,
            grace_holidays = ?,
            expected_check_in = ?,
            expected_check_out = ?,
            late_grace_minutes = ?,
            overtime_enabled = ?,
            overtime_rate = ?
        WHERE employee_id = ?
    """, (
        name,
        role,
        phone,
        address,
        monthly_salary,
        hourly_rate,
        salary_type,
        daily_hours,
        working_days,
        working_weekdays,
        grace_holidays,
        expected_check_in,
        expected_check_out,
        late_grace_minutes,
        overtime_enabled,
        overtime_rate,
        employee_id,
    ))

    if cursor.rowcount == 0:
        cursor.close()
        conn.close()
        raise ValueError("Employee not found")

    conn.commit()
    cursor.close()
    conn.close()


def deactivate_employee(employee_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE employees SET status = 'inactive' WHERE employee_id = ?", (employee_id,))
    conn.commit()
    cursor.close()
    conn.close()

def delete_employee(employee_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM attendance WHERE employee_id = ?", (employee_id,))
    cursor.execute("DELETE FROM salary_cal WHERE employee_id = ?", (employee_id,))
    cursor.execute("DELETE FROM employee_docs WHERE employee_id = ?", (employee_id,))
    cursor.execute("DELETE FROM employees WHERE employee_id = ?", (employee_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
