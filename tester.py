from backend.services.attendance import calculate_attendance_metrics


tests = [
    ("09:00:00", "19:00:00", 8),
    ("09:00:00", "17:30:00", 8),
    ("09:00:00", "17:00:00", 7),
    ("09:00:00", "17:00:00", 6),
    ("22:00:00", "08:00:00", 8),
]


for check_in, check_out, daily_hours in tests:

    result = calculate_attendance_metrics(
        check_in=check_in,
        check_out=check_out,
        expected_check_in="09:00:00",
        expected_check_out="18:00:00",
        daily_hours=daily_hours,
        late_grace_minutes=0,
        overtime_enabled=False
    )

    print("\n----------------------------------------")
    print(f"Check in     : {check_in}")
    print(f"Check out    : {check_out}")
    print(f"Daily hours  : {daily_hours}")
    print(f"Worked       : {result['worked_minutes']} minutes")
    print(f"Overtime     : {result['overtime_minutes']} minutes")
    print("----------------------------------------")