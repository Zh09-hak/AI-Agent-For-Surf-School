import hashlib
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _i(name, default):
    try:
        return int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return int(default)


def _s(name, default):
    return (os.getenv(name) or default).strip()


BUSINESS_OPEN = _s("BUSINESS_OPEN", "08:00")
BUSINESS_CLOSE = _s("BUSINESS_CLOSE", "18:00")
MIN_LEAD_TIME_HOURS = _i("MIN_LEAD_TIME_HOURS", 4)
AUTO_APPROVE_MAX_DAYS_AHEAD = _i("AUTO_APPROVE_MAX_DAYS_AHEAD", 60)
LESSON_DURATION_MINUTES = _i("LESSON_DURATION_MINUTES", 60)
MAX_AUTO_APPROVE_STUDENTS = _i("MAX_AUTO_APPROVE_STUDENTS", 2)
MAX_ACTIVE_BOOKINGS_PER_CUSTOMER = _i("MAX_ACTIVE_BOOKINGS_PER_CUSTOMER", 3)
MAX_BOOKINGS_PER_CUSTOMER_PER_DAY = _i("MAX_BOOKINGS_PER_CUSTOMER_PER_DAY", 1)
CUSTOMER_WINDOW_DAYS = _i("CUSTOMER_WINDOW_DAYS", 14)
SENDER_HOURLY_LIMIT = _i("SENDER_HOURLY_LIMIT", 5)
DEFAULT_MAX_STUDENTS_PER_SLOT = _i("DEFAULT_MAX_STUDENTS_PER_SLOT", 4)

AUTO_APPROVE_MODE = _s("AUTO_APPROVE_MODE", "shadow").lower()
AUTO_APPROVABLE_LESSONS = {"beginner", "intermediate", "advanced", "private"}


def auto_approve_enabled() -> bool:
    return AUTO_APPROVE_MODE == "live"

def normalize_name(name):
    if not name:
        return ""
    n = re.sub(r"[^a-zа-яё\s]", " ", str(name).lower())
    return " ".join(n.split())


def content_hash(text):
    norm = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def fingerprint(name, date_str, time_str, lesson_type):
    key = f"{normalize_name(name)}|{date_str}|{time_str}|{lesson_type}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]

def intervals_overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def parse_slot(date_str, time_str):
    try:
        start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return None, None
    return start, start + timedelta(minutes=LESSON_DURATION_MINUTES)

def check_time_sanity(date_str, time_str, now=None) -> list:
    flags = []
    now = now or datetime.now()

    if not date_str or not time_str:
        return ["missing_datetime"]

    start, end = parse_slot(date_str, time_str)
    if start is None:
        return ["invalid_datetime"]

    if start < now:
        flags.append("past_date")
    elif (start - now) < timedelta(hours=MIN_LEAD_TIME_HOURS):
        flags.append("short_notice")

    if (start - now) > timedelta(days=AUTO_APPROVE_MAX_DAYS_AHEAD):
        flags.append("too_far_ahead")

    try:
        oh, om = map(int, BUSINESS_OPEN.split(":"))
        ch, cm = map(int, BUSINESS_CLOSE.split(":"))
        if start < start.replace(hour=oh, minute=om, second=0) or \
           end > start.replace(hour=ch, minute=cm, second=0):
            flags.append("outside_business_hours")
    except ValueError:
        pass

    return flags

def remaining_capacity(bookings, start, end, max_students) -> int:
    used = 0
    for b in bookings:
        bs, be = parse_slot(b.get("date"), b.get("start_time"))
        if bs is None:
            continue
        if intervals_overlap(start, end, bs, be):
            used += int(b.get("number_of_students") or 1)
    return max(0, int(max_students) - used)


def filter_candidates_by_capacity(candidates, date_str, start, end, num_students, staff_rows=None) -> list:
    from integrations import db

    caps = {}
    for row in (staff_rows or []):
        name = row.get("instructor") or row.get("name") or row.get("instructor_name")
        if name:
            try:
                caps[name] = int(row.get("max_students") or DEFAULT_MAX_STUDENTS_PER_SLOT)
            except (TypeError, ValueError):
                caps[name] = DEFAULT_MAX_STUDENTS_PER_SLOT

    result = []
    for name in candidates:
        max_st = caps.get(name, DEFAULT_MAX_STUDENTS_PER_SLOT)
        bookings = db.get_active_bookings(name, date_str)
        free = remaining_capacity(bookings, start, end, max_st)
        if free >= int(num_students):
            result.append((name, free))
    return result

def check_customer_rules(name, name_norm, date_str, fp, from_addr=None) -> list:
    from integrations import db

    flags = []

    if fp and db.fingerprint_exists(fp):
        flags.append("duplicate_booking")

    if name_norm:
        if db.count_customer_same_day(name_norm, date_str) >= MAX_BOOKINGS_PER_CUSTOMER_PER_DAY:
            flags.append("same_day_duplicate")
        if db.count_customer_active(name_norm, CUSTOMER_WINDOW_DAYS) >= MAX_ACTIVE_BOOKINGS_PER_CUSTOMER:
            flags.append("customer_booking_limit")

    if from_addr and db.count_sender_recent(from_addr, 60) >= SENDER_HOURLY_LIMIT:
        flags.append("sender_rate_limit")

    return flags

def check_instructor_availability(instructor: str, date_str: str, time_str: str) -> list:
    from integrations import db
    
    flags = []
    if not instructor or not date_str or not time_str:
        return flags
    
    bookings = db.get_active_bookings(instructor, date_str)
    
    for booking in bookings:
        booking_start = booking.get("start_time")
        booking_end = booking.get("end_time")
        
        if not booking_start or not booking_end:
            continue
        
        if booking_start < time_str < booking_end or booking_start == time_str:
            flags.append(f"instructor_busy_{instructor}_at_{booking_start}")
            break
    
    return flags

def gate(proposal: dict, flags: list):
    if not auto_approve_enabled():
        return False, f"mode_is_{AUTO_APPROVE_MODE}"

    if flags:
        return False, "safety_flags:" + ",".join(sorted(set(flags)))

    if proposal.get("intent") != "new_booking":
        return False, f"intent_{proposal.get('intent')}"

    if proposal.get("missing_fields"):
        return False, "missing_fields:" + ",".join(proposal["missing_fields"])

    if not proposal.get("assigned_instructor"):
        return False, "no_instructor_assigned"

    n = int(proposal.get("number_of_students") or 1)
    if n > MAX_AUTO_APPROVE_STUDENTS:
        return False, f"party_size_{n}_over_limit_{MAX_AUTO_APPROVE_STUDENTS}"

    lesson = (proposal.get("lesson_type") or "").lower()
    if lesson not in AUTO_APPROVABLE_LESSONS:
        return False, f"lesson_type_{lesson}_not_auto_approvable"

    if not proposal.get("calendar_start") or not proposal.get("calendar_end"):
        return False, "no_calendar_window"

    return True, "all_checks_passed"