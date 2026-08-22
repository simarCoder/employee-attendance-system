from datetime import datetime

from backend.database import get_connection
from backend.devices.secureye import create_configured_secureye
from backend.services.attendance import process_device_attendance


EVENT_TYPES = {
    0x21: "fingerprint",
    0x34: "face",
}


def sync_secureye():

    device = create_configured_secureye()

    records = device.download_records()

    conn = get_connection()
    cursor = conn.cursor()

    inserted = 0
    skipped = 0

    try:

        for record in records:

            punch_time = record["timestamp"]

            if hasattr(punch_time, "strftime"):
                punch_time_str = punch_time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                punch_time_str = str(punch_time)

            event_code = record["event"]

            verification_type = EVENT_TYPES.get(
                event_code,
                "unknown"
            )

            try:

                cursor.execute("""
                    INSERT INTO device_punches (
                        device_card_id,
                        punch_time,
                        event_code,
                        verification_type,
                        raw_timestamp,
                        raw_data,
                        imported_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    record["card_id"],
                    punch_time_str,
                    event_code,
                    verification_type,
                    record["timestamp_raw"],
                    record["raw"],
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                ))

                inserted += 1

            except Exception as exc:

                # Duplicate punch
                if "UNIQUE constraint failed" in str(exc):
                    skipped += 1
                else:
                    raise

        conn.commit()

    finally:
        cursor.close()
        conn.close()

    # Process newly imported biometric punches
    attendance_result = process_device_attendance()

    return {
        "device_records": len(records),
        "inserted": inserted,
        "skipped": skipped,
        **attendance_result,
    }