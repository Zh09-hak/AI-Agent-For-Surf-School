import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def get_staff_from_csv(csv_path=None):
    if csv_path is None:
        csv_path = ROOT / "project" / "data" / "staff_availability.csv"
    csv_path = Path(csv_path)

    staff = []
    if not csv_path.exists():
        return staff

    with open(csv_path, mode="r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("available") or "true").lower() in ("true", "1", "yes", ""):
                staff.append(row)
    return staff


def _manual(parsed, reason):
    parsed["assigned_instructor"] = None
    parsed["assignment_reason"] = reason
    parsed["status"] = "needs_manual_review"
    return parsed


def assign_instructor(parsed_email: dict, available_staff: list = None) -> dict:
    from ai import safety

    if parsed_email.get("intent") != "new_booking":
        return _manual(parsed_email, f"Intent is {parsed_email.get('intent')}, needs manual review")

    missing = parsed_email.get("missing_fields") or []
    date_str = parsed_email.get("date")
    time_str = parsed_email.get("time")

    if not date_str or not time_str:
        return _manual(parsed_email, "Missing date or time")
    if "student_name" in missing or not parsed_email.get("student_name"):
        return _manual(parsed_email, "Missing student name, needs manual review")

    lesson_type = (parsed_email.get("lesson_type") or "unknown").lower()
    if lesson_type == "unknown":
        return _manual(parsed_email, "Unknown lesson level, needs manual review")

    num_students = int(parsed_email.get("number_of_students") or 1)
    if num_students > 4 and lesson_type != "group":
        return _manual(parsed_email, "Large party (5+ people) needs manual review")

    start, end = safety.parse_slot(date_str, time_str)
    if start is None:
        return _manual(parsed_email, "Invalid date/time format")

    if available_staff is None:
        available_staff = get_staff_from_csv()
    if not available_staff:
        return _manual(parsed_email, "No staff data available")

    requested = parsed_email.get("requested_instructor")
    window_ok = []
    for row in available_staff:
        name = row.get("instructor") or row.get("name") or row.get("instructor_name")
        r_date, r_start, r_end = row.get("date"), row.get("start_time"), row.get("end_time")
        skill = (row.get("skill_level") or row.get("skills") or "").lower()

        if not all([name, r_date, r_start, r_end]):
            continue
        if lesson_type == "intermediate" and skill not in ("intermediate", "advanced", "all", ""):
            continue
        if lesson_type == "advanced" and skill not in ("advanced", "all", ""):
            continue

        rs, re_ = safety.parse_slot(r_date, r_start)
        r_end_dt, _ = safety.parse_slot(r_date, r_end)
        if rs is None or r_end_dt is None:
            continue
        if rs <= start and r_end_dt >= end:
            window_ok.append((name, row))

    if not window_ok:
        return _manual(parsed_email, "No available instructor for this time/skill")

    staff_rows = [row for _, row in window_ok]
    with_capacity = safety.filter_candidates_by_capacity(
        [n for n, _ in window_ok], date_str, start, end, num_students, staff_rows
    )

    if not with_capacity:
        return _manual(parsed_email, "Instructors matched by skill but all slots are already booked")

    names = [n for n, _ in with_capacity]
    if requested and requested in names:
        chosen, free = next(x for x in with_capacity if x[0] == requested)
        reason = "Requested instructor available"
    else:
        chosen, free = max(with_capacity, key=lambda x: x[1])
        reason = "Matched by availability and capacity"

    parsed_email["assigned_instructor"] = chosen
    parsed_email["assignment_reason"] = f"{reason} (free capacity: {free})"

    if num_students >= 5 or lesson_type == "group":
        parsed_email["assignment_reason"] = "Large/group lesson needs manual review"
        parsed_email["status"] = "needs_manual_review"
    else:
        parsed_email["status"] = "pending"

    return parsed_email