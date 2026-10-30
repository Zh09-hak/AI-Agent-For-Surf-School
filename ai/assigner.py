import csv
import os
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent.parent

def get_staff_from_csv(csv_path=None):
    if csv_path is None:
        csv_path = ROOT / "project" / "data" / "staff_availability.csv"
    csv_path = Path(csv_path)

    staff = []
    if not csv_path.exists():
        return staff

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            available = (row.get("available") or "true").lower()
            if available in ["true", "1", "yes", ""]:
                staff.append(row)
    return staff

def assign_instructor(parsed_email: dict, available_staff: list = None) -> dict:
    if parsed_email.get("intent") != "new_booking":
        parsed_email["assigned_instructor"] = None
        parsed_email["assignment_reason"] = f"Intent is {parsed_email.get('intent')}, needs manual review"
        parsed_email["status"] = "needs_manual_review"
        return parsed_email

    missing = parsed_email.get("missing_fields", [])
    if not parsed_email.get("date") or not parsed_email.get("time"):
        parsed_email["assigned_instructor"] = None
        parsed_email["assignment_reason"] = "Missing date or time"
        parsed_email["status"] = "needs_manual_review"
        return parsed_email

    if "student_name" in missing or not parsed_email.get("student_name"):
        parsed_email["assigned_instructor"] = None
        parsed_email["assignment_reason"] = "Missing student name, needs manual review"
        parsed_email["status"] = "needs_manual_review"
        return parsed_email

    lesson_type = parsed_email.get("lesson_type", "unknown").lower()
    if lesson_type == "unknown":
        parsed_email["assigned_instructor"] = None
        parsed_email["assignment_reason"] = "Unknown lesson level, needs manual review"
        parsed_email["status"] = "needs_manual_review"
        return parsed_email

    if parsed_email.get("number_of_students", 1) > 4 and lesson_type != "group":
        parsed_email["assigned_instructor"] = None
        parsed_email["assignment_reason"] = "Large party (5+ people) needs manual review"
        parsed_email["status"] = "needs_manual_review"
        return parsed_email

    if available_staff is None:
        available_staff = get_staff_from_csv()

    if not available_staff:
        parsed_email["assigned_instructor"] = None
        parsed_email["assignment_reason"] = "No staff data available"
        parsed_email["status"] = "needs_manual_review"
        return parsed_email

    lesson_type = parsed_email.get("lesson_type", "unknown").lower()
    requested = parsed_email.get("requested_instructor")
    
    date_str = parsed_email["date"]
    time_str = parsed_email["time"]
    
    try:
        target_start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        target_end = target_start + timedelta(hours=1)
    except ValueError:
        parsed_email["assigned_instructor"] = None
        parsed_email["assignment_reason"] = "Invalid date/time format"
        parsed_email["status"] = "needs_manual_review"
        return parsed_email

    candidates = []
    
    for row in available_staff:
        instructor_name = row.get("instructor") or row.get("name") or row.get("instructor_name")
        row_date = row.get("date")
        row_start = row.get("start_time")
        row_end = row.get("end_time")
        skill = (row.get("skill_level") or row.get("skills") or "").lower()

        if not all([instructor_name, row_date, row_start, row_end]):
            continue

        if lesson_type == "intermediate" and skill not in ["intermediate", "advanced", "all", ""]:
            continue
        if lesson_type == "advanced" and skill not in ["advanced", "all", ""]:
            continue
            
        try:
            row_start_dt = datetime.strptime(f"{row_date} {row_start}", "%Y-%m-%d %H:%M")
            row_end_dt = datetime.strptime(f"{row_date} {row_end}", "%Y-%m-%d %H:%M")
            
            if row_start_dt <= target_start and row_end_dt >= target_end:
                candidates.append(instructor_name)
        except ValueError:
            continue

    num_students = parsed_email.get("number_of_students", 1)
    manual_override = (num_students >= 5 or lesson_type == "group")

    if not candidates:
        parsed_email["assigned_instructor"] = None
        parsed_email["assignment_reason"] = "No available instructor for this time/skill"
        parsed_email["status"] = "needs_manual_review"
        return parsed_email

    if requested and requested in candidates:
        parsed_email["assigned_instructor"] = requested
        parsed_email["assignment_reason"] = "Requested instructor available"
    else:
        parsed_email["assigned_instructor"] = candidates[0]
        parsed_email["assignment_reason"] = "Matched by availability"

    if manual_override:
        parsed_email["assignment_reason"] = "Large/group lesson needs manual review"
        parsed_email["status"] = "needs_manual_review"
    else:
        parsed_email["status"] = "pending"

    return parsed_email