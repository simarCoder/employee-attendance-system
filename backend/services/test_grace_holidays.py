
import importlib.util
import sqlite3
import sys
import tempfile
import os
from datetime import date, timedelta
import types


def load_salary_module():
    backend = types.ModuleType("backend")
    database = types.ModuleType("backend.database")
    database.get_connection = lambda: None
    sys.modules["backend"] = backend
    sys.modules["backend.database"] = database

    path = os.path.join(os.path.dirname(__file__), "salary.py")
    spec = importlib.util.spec_from_file_location("salary_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, database


def test_three_half_days_equal_1_5_holidays():
    salary, _ = load_salary_module()
    dates = [date(2026, 8, 3) + timedelta(days=i) for i in range(5)]
    attendance = {
        dates[0].isoformat(): 240,
        dates[1].isoformat(): 240,
        dates[2].isoformat(): 240,
        dates[3].isoformat(): 480,
        dates[4].isoformat(): 480,
    }

    result = salary.calculate_holiday_deduction(dates, attendance, 480, 0)

    assert result["absence_days"] == 1.5
    assert result["deducted_holidays"] == 1.5


def test_one_full_holiday_plus_two_half_days_equal_2():
    salary, _ = load_salary_module()
    dates = [date(2026, 8, 3) + timedelta(days=i) for i in range(5)]
    attendance = {
        dates[1].isoformat(): 240,
        dates[2].isoformat(): 240,
        dates[3].isoformat(): 480,
        dates[4].isoformat(): 480,
    }

    result = salary.calculate_holiday_deduction(dates, attendance, 480, 0)

    assert result["absence_days"] == 2.0
    assert result["deducted_holidays"] == 2.0


def test_grace_holidays_are_applied_before_deduction():
    salary, _ = load_salary_module()
    dates = [date(2026, 8, 3) + timedelta(days=i) for i in range(5)]
    attendance = {
        dates[1].isoformat(): 240,
        dates[2].isoformat(): 240,
        dates[3].isoformat(): 480,
        dates[4].isoformat(): 480,
    }

    result = salary.calculate_holiday_deduction(dates, attendance, 480, 2)

    assert result["absence_days"] == 2.0
    assert result["grace_holidays_used"] == 2.0
    assert result["deducted_holidays"] == 0.0
    assert result["paid_minutes"] == 2400


def test_excess_holidays_are_deducted_after_grace():
    salary, _ = load_salary_module()
    dates = [date(2026, 8, 3) + timedelta(days=i) for i in range(5)]
    attendance = {
        dates[1].isoformat(): 240,
        dates[2].isoformat(): 240,
        dates[3].isoformat(): 240,
        dates[4].isoformat(): 480,
    }

    result = salary.calculate_holiday_deduction(dates, attendance, 480, 2)

    assert result["absence_days"] == 2.5
    assert result["grace_holidays_used"] == 2.0
    assert result["deducted_holidays"] == 0.5


def test_full_integration_salary_uses_grace_holidays():
    salary, database = load_salary_module()

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    def connection():
        return sqlite3.connect(db_path)

    database.get_connection = connection
    salary.get_connection = connection

    conn = connection()
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE system_settings(setting_key TEXT PRIMARY KEY, setting_value TEXT)"
    )
    cur.execute(
        "INSERT INTO system_settings VALUES ('working_days', '0,1,2,3,4,5')"
    )
    cur.execute(
        """CREATE TABLE employees(
            employee_id INTEGER PRIMARY KEY,
            name TEXT, role TEXT, monthly_salary REAL, daily_hours REAL,
            overtime_enabled INTEGER, overtime_rate REAL, salary_type TEXT,
            grace_holidays REAL
        )"""
    )
    cur.execute(
        """CREATE TABLE attendance(
            attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER, date TEXT,
            worked_minutes INTEGER, overtime_minutes INTEGER
        )"""
    )
    cur.execute(
        """CREATE TABLE salary_cal(
            salary_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER, month TEXT, employee_name TEXT,
            employee_role TEXT, salary_type TEXT,
            monthly_salary_snapshot REAL, daily_hours REAL,
            working_days INTEGER, expected_monthly_minutes REAL,
            actual_worked_minutes INTEGER, total_hours REAL,
            overtime_minutes INTEGER,
            grace_holidays_snapshot REAL, absence_days REAL,
            grace_holidays_used REAL, deducted_holidays REAL,
            paid_minutes REAL, hourly_rate_snapshot REAL,
            base_salary REAL, overtime_pay REAL, total_salary REAL,
            locked INTEGER, created_at TEXT, updated_at TEXT
        )"""
    )
    cur.execute(
        "INSERT INTO employees VALUES (1,'Test','Staff',26000,8,0,1,'monthly',2)"
    )
    conn.commit()
    conn.close()

    # One full holiday + two half-days, with exactly two grace holidays.
    working = [
        date(2026, 8, d)
        for d in range(1, 32)
        if date(2026, 8, d).weekday() in {0, 1, 2, 3, 4, 5}
    ]
    conn = connection()
    cur = conn.cursor()
    for index, current_date in enumerate(working):
        if index == 0:
            continue
        minutes = 240 if index in (1, 2) else 480
        cur.execute(
            "INSERT INTO attendance(employee_id,date,worked_minutes,overtime_minutes)"
            " VALUES (1,?,?,0)",
            (current_date.isoformat(), minutes),
        )
    conn.commit()
    conn.close()

    result = salary.generate_salary(1, "2026-08")

    assert result["working_days"] == 26
    assert result["absence_days"] == 2.0
    assert result["grace_holidays_used"] == 2.0
    assert result["deducted_holidays"] == 0.0
    assert result["total_salary"] == 26000.0

    os.remove(db_path)
