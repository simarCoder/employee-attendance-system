from datetime import datetime, date, timedelta
from backend.database import get_connection


#=====================================================================
#           Helper functions to parse working weekdays
#=====================================================================

def parse_working_weekdays(value):
    """
    Convert an employee's working_weekdays value into a set
    of Python weekday numbers.

    Python weekday:
        Monday    = 0
        Tuesday   = 1
        Wednesday = 2
        Thursday  = 3
        Friday    = 4
        Saturday  = 5
        Sunday    = 6
    """

    if value is None:
        return {0, 1, 2, 3, 4, 5}

    if isinstance(value, str):
        parts = [
            part.strip()
            for part in value.split(",")
            if part.strip()
        ]
    else:
        parts = list(value)

    try:
        weekdays = {
            int(part)
            for part in parts
            if 0 <= int(part) <= 6
        }
    except (TypeError, ValueError):
        return {0, 1, 2, 3, 4, 5}

    # Keep backward-compatible default if the value is empty/invalid.
    if not weekdays:
        return {0, 1, 2, 3, 4, 5}

    return weekdays
  
    
def is_employee_scheduled(target_date, working_weekdays):
    """
    Return True when the employee is scheduled to work
    on the supplied calendar date.
    """

    return target_date.weekday() in parse_working_weekdays(
        working_weekdays
    )  
    
    
     
def generate_employee_working_dates(
    employee_id,
    start_date,
    end_date
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT working_weekdays
        FROM employees
        WHERE employee_id = ?
    """, (employee_id,))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return []

    working_weekdays = row[0]

    start = (
        datetime.strptime(start_date, "%Y-%m-%d")
        .date()
    )

    end = (
        datetime.strptime(end_date, "%Y-%m-%d")
        .date()
    )

    dates = []

    current = start

    while current <= end:
        if is_employee_scheduled(
            current,
            working_weekdays
        ):
            dates.append(current.isoformat())

        current += timedelta(days=1)

    return dates


def iter_dates(start_date, end_date):
    """
    Yield every calendar date from start_date through end_date,
    inclusive.

    No fixed 26-day/month assumption is used.
    """

    current = date.fromisoformat(start_date)
    final = date.fromisoformat(end_date)

    while current <= final:
        yield current
        current += timedelta(days=1)
    

def time_to_minutes(time_str):
    if not time_str:
        return None

    dt = datetime.strptime(time_str, "%H:%M:%S")

    return dt.hour * 60 + dt.minute


def minutes_to_hours(minutes):
    if minutes is None:
        return None

    return round(minutes / 60, 4)


def format_duration(minutes):
    if minutes is None:
        return "-"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    return f"{hours}h {remaining_minutes}m"


def calculate_attendance_metrics(
    check_in,
    check_out,
    expected_check_in=None,
    expected_check_out=None,
    daily_hours=8,
    late_grace_minutes=0,
    overtime_enabled=False
):
    """
    Calculate worked time, late time and overtime.

    Overtime is based on the employee's configured DAILY HOURS,
    not on the difference between expected check-in and expected
    check-out.

    Example:
        Daily Hours = 8
        Check In    = 09:00
        Check Out   = 19:00
        Worked      = 10h
        Overtime    = 2h
    """

    worked_minutes = None
    late_minutes = 0
    overtime_minutes = 0

    # -------------------------------------------------
    # WORKED HOURS
    # -------------------------------------------------

    if check_in and check_out:
        check_in_minutes = time_to_minutes(check_in)
        check_out_minutes = time_to_minutes(check_out)

        # Normal same-day shift
        if check_out_minutes >= check_in_minutes:
            worked_minutes = check_out_minutes - check_in_minutes

        # Overnight shift
        else:
            worked_minutes = (
                (24 * 60 - check_in_minutes)
                + check_out_minutes
            )

    # -------------------------------------------------
    # LATE
    # -------------------------------------------------

    if check_in and expected_check_in:
        actual_in = time_to_minutes(check_in)

        expected_in = time_to_minutes(
            expected_check_in
            if len(expected_check_in) == 8
            else expected_check_in + ":00"
        )

        late_minutes = max(
            0,
            actual_in
            - expected_in
            - int(late_grace_minutes or 0)
        )

    # -------------------------------------------------
    # OVERTIME
    # -------------------------------------------------
    #
    # IMPORTANT:
    # Overtime is based on DAILY HOURS.
    #
    # Do NOT calculate it from:
    #     expected_check_out - expected_check_in
    #
    # because that may include breaks or represent a
    # shift window longer than the actual required hours.
    #
    # Example:
    #     Expected: 09:00 - 18:00
    #     Daily Hours: 8
    #     Actual: 09:00 - 19:00
    #
    #     Worked = 10h
    #     Required = 8h
    #     Overtime = 2h
    #

    # if (
    #     overtime_enabled
    #     and worked_minutes is not None
    # ):
    if worked_minutes is not None:
        try:
            required_minutes = int(
                round(float(daily_hours or 0) * 60)
            )
        except (TypeError, ValueError):
            required_minutes = 0

        # Backward-compatible fallback for old records/configurations
        # where daily_hours is unavailable/invalid.
        if required_minutes <= 0 and expected_check_in and expected_check_out:
            expected_in = time_to_minutes(
                expected_check_in
                if len(expected_check_in) == 8
                else expected_check_in + ":00"
            )

            expected_out = time_to_minutes(
                expected_check_out
                if len(expected_check_out) == 8
                else expected_check_out + ":00"
            )

            if expected_out >= expected_in:
                required_minutes = expected_out - expected_in
            else:
                required_minutes = (
                    (24 * 60 - expected_in)
                    + expected_out
                )

        overtime_minutes = max(
            0,
            worked_minutes - required_minutes
        )

    return {
        "worked_minutes": worked_minutes,
        "worked_hours": minutes_to_hours(worked_minutes),
        "late_minutes": late_minutes,
        "overtime_minutes": overtime_minutes,
    }

def check_in(employee_id, custom_time=None, target_date=None):
    # Use target_date if provided (Admin/Head), else today
    today = target_date if target_date else date.today().isoformat()
    
    # Use custom time if provided (Head Override), else current time
    if custom_time:
        # Ensure format allows adding minutes/seconds if user only sent HH:MM
        if len(custom_time) == 5: # HH:MM
            custom_time += ":00"
        now = custom_time
    else:
        now = datetime.now().strftime("%H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()

    # Check if already checked in for the target date
    cursor.execute("""
        SELECT attendance_id, check_out, locked
        FROM attendance
        WHERE employee_id = ? AND date = ?
    """, (employee_id, today))

    existing_record = cursor.fetchone()

    if existing_record:
        attendance_id, current_check_out, locked = existing_record
        
        # If custom_time is provided (Head override), allow update even if record exists/locked
        if custom_time:
            cursor.execute("""
                UPDATE attendance
                SET
                    check_in = ?,
                    check_in_source = 'admin'
                WHERE attendance_id = ?
            """, (
                now,
                attendance_id
            ))
            
            # If there was already a check-out, recalculate worked hours based on new check-in
            if current_check_out:
                try:
                    check_in_dt = datetime.strptime(now, "%H:%M:%S")
                    check_out_dt = datetime.strptime(current_check_out, "%H:%M:%S")
                    
                    if check_out_dt < check_in_dt:
                         # If new in-time is after out-time, this is invalid for a single day shift.
                         # We allow the update but worked hours will be negative or zero.
                         worked_hours = 0.0
                    else:
                        worked_hours = (check_out_dt - check_in_dt).seconds / 3600
                        worked_minutes = int(round(worked_hours * 60))

                    cursor.execute(
                            """
                            UPDATE attendance
                            SET
                                worked_hours = ?,
                                worked_minutes = ?
                            WHERE attendance_id = ?
                            """,
                            (
                                worked_hours,
                                worked_minutes,
                                attendance_id
                            )
                        )
                except ValueError:
                    pass # Ignore time format errors during recalc

        else:
            # Standard user trying to check in again
            cursor.close()
            conn.close()
            raise Exception("Already checked in for this date")
    else:
        # New record
        cursor.execute("""
    INSERT INTO attendance (
        employee_id,
        date,
        check_in,
        check_in_source
    )
    VALUES (?, ?, ?, ?)
""", (
    employee_id,
    today,
    now,
    "admin" if custom_time else "manual"
))

    conn.commit()
    cursor.close()
    conn.close()


def check_out(employee_id, custom_time=None, target_date=None):
    today = target_date if target_date else date.today().isoformat()
    
    # Use custom time if provided
    if custom_time:
        if len(custom_time) == 5:
            custom_time += ":00"
        now = custom_time
    else:
        now = datetime.now().strftime("%H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT attendance_id, check_in, locked
        FROM attendance
        WHERE employee_id = ? AND date = ?
    """, (employee_id, today))
    
    cursor.execute("""
        SELECT
            expected_check_in,
            expected_check_out,
            daily_hours,
            late_grace_minutes,
            overtime_enabled
        FROM employees
        WHERE employee_id = ?
    """, (employee_id,))

    employee_rules = cursor.fetchone()

    expected_check_in = None
    expected_check_out = None
    daily_hours = None
    late_grace_minutes = 0
    overtime_enabled = 0

    if employee_rules:
        (
            expected_check_in,
            expected_check_out,
            daily_hours,
            late_grace_minutes,
            overtime_enabled
        ) = employee_rules

    record = cursor.fetchone()

    if not record:
        cursor.close()
        conn.close()
        raise Exception("No check-in found for this date")

    attendance_id, check_in_time, locked = record

    # Only allow update if NOT locked OR if it IS a custom_time override
    if locked and not custom_time:
        cursor.close()
        conn.close()
        raise Exception("Attendance record is locked")

    try:
        check_in_dt = datetime.strptime(
            check_in_time,
            "%H:%M:%S"
        )

        check_out_dt = datetime.strptime(
            now,
            "%H:%M:%S"
        )

        if check_out_dt < check_in_dt:
            raise ValueError(
                "Check-out time cannot be before check-in time"
            )

        worked_minutes = int(
            round(
                (check_out_dt - check_in_dt).total_seconds() / 60
            )
        )

        worked_hours = round(
            worked_minutes / 60,
            4
        )

    except ValueError as ve:
        cursor.close()
        conn.close()
        raise Exception(
            f"Time Calculation Error: {str(ve)}"
        )

    cursor.execute("""
            UPDATE attendance
            SET
                check_out = ?,
                check_out_source = ?,
                worked_hours = ?,
                worked_minutes = ?
            WHERE attendance_id = ?
        """, (
            now,
            "admin" if custom_time else "manual",
            worked_hours,
            worked_minutes,
            attendance_id
        ))

    conn.commit()
    cursor.close()
    conn.close()


def get_attendance_by_employee(employee_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
                    SELECT
                        date,
                        check_in,
                        check_out,
                        worked_hours,
                        worked_minutes
                    FROM attendance
                    WHERE employee_id = ?
                    ORDER BY date DESC
                """, (employee_id,))

    rows = cursor.fetchall()

    cursor.close()
    conn.close()
    return rows

def get_attendance_by_date(target_date):
    """
    Return attendance for every active employee for one calendar day.

    Scheduled employee:
        no punch       -> Absent
        one punch      -> Incomplete
        check-in/out   -> Present

    Non-scheduled employee:
        -> Off Day

    The employee's own working_weekdays configuration determines
    whether the date is scheduled.
    """

    target = date.fromisoformat(target_date)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            e.employee_id,
            e.name,
            e.role,
            e.working_weekdays,
            e.daily_hours,
            a.date,
            a.check_in,
            a.check_out,
            a.worked_hours,
            a.worked_minutes,
            a.late_minutes,
            a.overtime_minutes
        FROM employees e
        LEFT JOIN attendance a
            ON e.employee_id = a.employee_id
            AND a.date = ?
        WHERE e.status = 'active'
        ORDER BY e.employee_id ASC
        """,
        (target_date,)
    )

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    result = []

    for row in rows:
        (
            employee_id,
            name,
            role,
            working_weekdays,
            daily_hours,
            attendance_date,
            check_in,
            check_out,
            worked_hours,
            worked_minutes,
            late_minutes,
            overtime_minutes
        ) = row

        scheduled = is_employee_scheduled(
            target,
            working_weekdays
        )

        if not scheduled:
            status = "Off Day"
        elif check_in and check_out:
            status = "Present"
        elif check_in:
            status = "Incomplete"
        else:
            status = "Absent"

        result.append({
            "employee_id": employee_id,
            "name": name,
            "role": role,
            "daily_hours": daily_hours,
            "date": target_date,
            "check_in": check_in,
            "check_out": check_out,
            "worked_hours": worked_hours,
            "worked_minutes": worked_minutes,
            "late_minutes": late_minutes,
            "overtime_minutes": overtime_minutes,
            "scheduled": scheduled,
            "status": status,
        })

    return result


def get_attendance_by_range(start_date, end_date):
    """
    Return scheduled attendance rows for every active employee
    between start_date and end_date, inclusive.

    Each employee's own working_weekdays determines which
    calendar dates are included.

    Off-days are not returned in month/year range views.
    This prevents an employee's regular weekly off-days from
    being counted as absent.
    """

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if start > end:
        raise ValueError("start_date cannot be after end_date")

    conn = get_connection()
    cursor = conn.cursor()

    # Get active employees and their individual schedules.
    cursor.execute(
        """
        SELECT
            employee_id,
            name,
            role,
            working_weekdays,
            daily_hours
        FROM employees
        WHERE status = 'active'
        ORDER BY employee_id ASC
        """
    )

    employees = cursor.fetchall()

    # Get actual attendance records in the requested range.
    cursor.execute(
        """
        SELECT
            employee_id,
            date,
            check_in,
            check_out,
            worked_hours,
            worked_minutes,
            late_minutes,
            overtime_minutes
        FROM attendance
        WHERE date >= ?
          AND date <= ?
        ORDER BY date ASC, employee_id ASC
        """,
        (start_date, end_date)
    )

    attendance_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    # Fast lookup:
    # (employee_id, date) -> attendance data
    attendance_by_employee_date = {}

    for row in attendance_rows:
        (
            employee_id,
            attendance_date,
            check_in,
            check_out,
            worked_hours,
            worked_minutes,
            late_minutes,
            overtime_minutes
        ) = row

        attendance_by_employee_date[
            (employee_id, attendance_date)
        ] = {
            "check_in": check_in,
            "check_out": check_out,
            "worked_hours": worked_hours,
            "worked_minutes": worked_minutes,
            "late_minutes": late_minutes,
            "overtime_minutes": overtime_minutes,
        }

    result = []

    # Generate actual calendar dates.
    for current_date in iter_dates(
        start_date,
        end_date
    ):
        current_date_string = current_date.isoformat()

        for (
            employee_id,
            name,
            role,
            working_weekdays,
            daily_hours
        ) in employees:

            # IMPORTANT:
            # The employee's own schedule decides whether
            # this calendar date is a working day.
            if not is_employee_scheduled(
                current_date,
                working_weekdays
            ):
                continue

            attendance = attendance_by_employee_date.get(
                (employee_id, current_date_string)
            )

            if attendance:
                check_in = attendance["check_in"]
                check_out = attendance["check_out"]
                worked_hours = attendance["worked_hours"]
                worked_minutes = attendance["worked_minutes"]
                late_minutes = attendance["late_minutes"]
                overtime_minutes = attendance["overtime_minutes"]

                if check_in and check_out:
                    status = "Present"
                elif check_in:
                    status = "Incomplete"
                else:
                    status = "Absent"
            else:
                check_in = None
                check_out = None
                worked_hours = None
                worked_minutes = None
                late_minutes = None
                overtime_minutes = None

                status = "Absent"

            result.append({
                "employee_id": employee_id,
                "name": name,
                "role": role,
                "daily_hours": daily_hours,
                "date": current_date_string,
                "check_in": check_in,
                "check_out": check_out,
                "worked_hours": worked_hours,
                "worked_minutes": worked_minutes,
                "late_minutes": late_minutes,
                "overtime_minutes": overtime_minutes,
                "scheduled": True,
                "status": status,
            })

    # Latest dates first, employee ID ascending.
    result.sort(
        key=lambda record: (
            record["date"],
            record["employee_id"]
        ),
        reverse=False
    )

    result.reverse()

    return result


def get_device_punches(
    start_date=None,
    end_date=None,
    card_id=None
):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            punch_id,
            device_card_id,
            punch_time,
            event_code,
            verification_type,
            raw_timestamp
        FROM device_punches
        WHERE 1 = 1
    """

    params = []

    if start_date:
        query += """
            AND punch_time >= ?
        """

        params.append(
            start_date + " 00:00:00"
        )

    if end_date:
        query += """
            AND punch_time < datetime(?, '+1 day')
        """

        params.append(end_date)

    if card_id:
        query += """
            AND device_card_id = ?
        """

        params.append(card_id)

    query += """
        ORDER BY punch_time ASC
    """

    cursor.execute(
        query,
        params
    )

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows

def process_device_attendance(start_date=None, end_date=None):
    """
    Build attendance from Secureye machine punches.

    Rules:
    - First punch of an employee on a date = check-in.
    - Last punch of an employee on a date = check-out.
    - One punch = check-in only, no checkout.
    - Every sync recalculates machine attendance from raw punches.
    - Raw device_punches are never modified.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # -------------------------------------------------
        # FETCH MAPPED DEVICE PUNCHES
        # -------------------------------------------------

        query = """
            SELECT
                bd.employee_id,
                dp.device_card_id,
                dp.punch_time
            FROM device_punches dp
            INNER JOIN biometric_devices bd
                ON bd.device_card_id = dp.device_card_id
            WHERE 1 = 1
        """

        params = []

        if start_date:
            query += """
                AND dp.punch_time >= ?
            """
            params.append(start_date + " 00:00:00")

        if end_date:
            query += """
                AND dp.punch_time < datetime(?, '+1 day')
            """
            params.append(end_date)

        query += """
            ORDER BY dp.punch_time ASC
        """

        cursor.execute(query, params)

        punches = cursor.fetchall()

        # -------------------------------------------------
        # GROUP BY EMPLOYEE + DATE
        # -------------------------------------------------

        employee_days = {}

        for employee_id, device_card_id, punch_time in punches:

            punch_dt = datetime.strptime(
                punch_time,
                "%Y-%m-%d %H:%M:%S"
            )

            day = punch_dt.date().isoformat()

            key = (employee_id, day)

            employee_days.setdefault(
                key,
                []
            ).append(punch_dt)

        processed = 0

        # -------------------------------------------------
        # PROCESS EACH EMPLOYEE / DATE
        # -------------------------------------------------

        for (employee_id, day), punches_for_day in employee_days.items():

            # Make absolutely sure chronological order is correct.
            punches_for_day.sort()

            # -------------------------------------------------
            # FIRST PUNCH = CHECK-IN
            # -------------------------------------------------

            machine_check_in = punches_for_day[0].strftime(
                "%H:%M:%S"
            )

            # -------------------------------------------------
            # LAST PUNCH = CHECK-OUT
            # -------------------------------------------------

            machine_check_out = None

            if len(punches_for_day) > 1:
                machine_check_out = punches_for_day[-1].strftime(
                    "%H:%M:%S"
                )

            # # -------------------------------------------------
            # # WORKED HOURS
            # # -------------------------------------------------

            # worked_hours = None

            # if machine_check_in and machine_check_out:

            #     check_in_dt = datetime.strptime(
            #         machine_check_in,
            #         "%H:%M:%S"
            #     )

            #     check_out_dt = datetime.strptime(
            #         machine_check_out,
            #         "%H:%M:%S"
            #     )

            #     if check_out_dt >= check_in_dt:

            #         worked_hours = (
            #             check_out_dt - check_in_dt
            #         ).total_seconds() / 3600


# -------------------------------------------------
# GET EMPLOYEE WORK RULES
# -------------------------------------------------

            cursor.execute("""
                    SELECT
                        expected_check_in,
                        expected_check_out,
                        daily_hours,
                        late_grace_minutes,
                        overtime_enabled
                    FROM employees
                    WHERE employee_id = ?
                """, (employee_id,))

            employee_rules = cursor.fetchone()

            expected_check_in = None
            expected_check_out = None
            daily_hours = 8
            late_grace_minutes = 0
            overtime_enabled = 0

            if employee_rules:
                (
                    expected_check_in,
                    expected_check_out,
                    daily_hours,
                    late_grace_minutes,
                    overtime_enabled
                ) = employee_rules


            # -------------------------------------------------
            # CALCULATE ATTENDANCE METRICS
            # -------------------------------------------------

            metrics = calculate_attendance_metrics(
                check_in=machine_check_in,
                check_out=machine_check_out,
                expected_check_in=expected_check_in,
                expected_check_out=expected_check_out,
                daily_hours=daily_hours,
                late_grace_minutes=late_grace_minutes,
                overtime_enabled=bool(overtime_enabled)
            )

            worked_minutes = metrics["worked_minutes"]
            worked_hours = metrics["worked_hours"]
            late_minutes = metrics["late_minutes"]
            overtime_minutes = metrics["overtime_minutes"]



            # -------------------------------------------------
            # CHECK EXISTING ATTENDANCE
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT attendance_id
                FROM attendance
                WHERE employee_id = ?
                  AND date = ?
                """,
                (
                    employee_id,
                    day
                )
            )

            existing = cursor.fetchone()

            # -------------------------------------------------
            # CREATE NEW RECORD
            # -------------------------------------------------

            if not existing:

                cursor.execute(
                """
                INSERT INTO attendance (
                    employee_id,
                    date,
                    check_in,
                    check_out,
                    worked_hours,
                    worked_minutes,
                    late_minutes,
                    overtime_minutes,
                    check_in_source,
                    check_out_source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    day,
                    machine_check_in,
                    machine_check_out,
                    worked_hours,
                    worked_minutes,
                    late_minutes,
                    overtime_minutes,
                    "machine",
                    "machine" if machine_check_out else None
                )
            )

            # -------------------------------------------------
            # UPDATE EXISTING MACHINE RECORD
            # -------------------------------------------------

            else:

                attendance_id = existing[0]

                cursor.execute(
                """
                UPDATE attendance
                SET
                    check_in = ?,
                    check_out = ?,
                    worked_hours = ?,
                    worked_minutes = ?,
                    late_minutes = ?,
                    overtime_minutes = ?,
                    check_in_source = 'machine',
                    check_out_source = ?
                WHERE attendance_id = ?
                """,
                (
                    machine_check_in,
                    machine_check_out,
                    worked_hours,
                    worked_minutes,
                    late_minutes,
                    overtime_minutes,
                    "machine" if machine_check_out else None,
                    attendance_id
                )
            )

            processed += 1

        conn.commit()

        return {
            "days_processed": processed,
            "punches_found": len(punches)
        }

    finally:

        cursor.close()
        conn.close()
        
