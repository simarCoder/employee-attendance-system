from backend.database import get_connection


def assign_device_to_employee(
    device_card_id,
    employee_id
):
    conn = get_connection()
    cursor = conn.cursor()

    try:

        # Verify employee exists
        cursor.execute("""
            SELECT employee_id
            FROM employees
            WHERE employee_id = ?
        """, (employee_id,))

        employee = cursor.fetchone()

        if not employee:
            raise ValueError(
                f"Employee {employee_id} does not exist."
            )

        # Check whether this device ID is already assigned
        cursor.execute("""
            SELECT employee_id
            FROM biometric_devices
            WHERE device_card_id = ?
        """, (device_card_id,))

        existing_device = cursor.fetchone()

        if existing_device:

            if existing_device[0] == employee_id:
                return {
                    "success": True,
                    "message": "Mapping already exists."
                }

            raise ValueError(
                f"Device ID {device_card_id} "
                f"is already assigned to employee "
                f"{existing_device[0]}."
            )

        # Check whether employee already has a device
        cursor.execute("""
            SELECT device_card_id
            FROM biometric_devices
            WHERE employee_id = ?
        """, (employee_id,))

        existing_employee = cursor.fetchone()

        if existing_employee:

            raise ValueError(
                f"Employee {employee_id} already has "
                f"device ID {existing_employee[0]}."
            )

        cursor.execute("""
            INSERT INTO biometric_devices (
                device_card_id,
                employee_id
            )
            VALUES (?, ?)
        """, (
            device_card_id,
            employee_id
        ))

        conn.commit()

        return {
            "success": True,
            "message": "Biometric device assigned."
        }

    finally:

        cursor.close()
        conn.close()


def get_device_mappings():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            bd.device_id,
            bd.device_card_id,
            bd.employee_id,
            e.name,
            e.role
        FROM biometric_devices bd
        JOIN employees e
            ON e.employee_id = bd.employee_id
        ORDER BY e.name
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows


def get_employee_for_device(device_card_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT employee_id
        FROM biometric_devices
        WHERE device_card_id = ?
    """, (device_card_id,))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return None

    return row[0]


def remove_device_mapping(device_card_id):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            DELETE FROM biometric_devices
            WHERE device_card_id = ?
        """, (device_card_id,))

        if cursor.rowcount == 0:
            return {
                "success": False,
                "message": "Mapping not found."
            }

        conn.commit()

        return {
            "success": True,
            "message": "Biometric device unmapped."
        }

    finally:
        cursor.close()
        conn.close()