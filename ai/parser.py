import os
import re
import csv
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

try:
    from groq import Groq
except ImportError:
    Groq = None

load_dotenv()

TODAY = datetime(2026, 10, 28)

api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if Groq and api_key else None
env_model = os.getenv("GROQ_MODEL")

ALLOWED_INTENTS = {"new_booking", "cancellation", "reschedule", "question"}

SYSTEM_PROMPT = f"""You are an expert data extractor for a surf school.
Today's date is {TODAY.strftime('%Y-%m-%d')}.

Extract information from the user's email.

Rules:
- If the email mentions relative dates like "tomorrow", "next Saturday", calculate the exact YYYY-MM-DD date based on today's date.
- If the email mentions "morning", use "09:00".
- If the email mentions "afternoon", use "14:00".
- If the email asks a question, is not ready to book, or has multiple different bookings, set intent to "question".
- If it is a cancellation, set intent to "cancellation".
- If it is a reschedule request, set intent to "reschedule".
- If it is a normal booking request, set intent to "new_booking".

Return ONLY a valid JSON object with this exact schema:
{{
  "student_name": "string or null",
  "lesson_type": "beginner | intermediate | advanced | private | group | unknown",
  "date": "YYYY-MM-DD or null",
  "time": "HH:MM or null",
  "number_of_students": integer,
  "requested_instructor": "string or null",
  "intent": "new_booking | cancellation | reschedule | question"
}}"""

def extract_with_groq(raw_email: str):
    if not client:
        return None

    models = []

    if env_model:
        models.append(env_model)

    models += [
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
    ]

    seen = set()
    models = [m for m in models if m and not (m in seen or seen.add(m))]

    for model in models:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": raw_email}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )

            data = json.loads(completion.choices[0].message.content)

            if isinstance(data, dict) and data.get("intent") in ALLOWED_INTENTS:
                print(f"✅ Groq success with model: {model}")
                return data

            print(f"⚠️ Groq model {model} returned weak JSON.")

        except Exception as e:
            print(f"⚠️ Groq model {model} failed: {e}")

    return None

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

WORDS_TO_NUM = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def extract_intent_regex(text: str) -> str:
    lower = text.lower()

    if "cancel" in lower or "cancellation" in lower:
        return "cancellation"

    if any(word in lower for word in ["move it", "reschedule", "change my booking", "change it"]):
        return "reschedule"

    question_signals = [
        "price",
        "prices",
        "not ready",
        "have not made a booking",
        "is it safe",
        "equipment is included",
        "could you tell",
        "can you tell",
        "what are your",
        "options",
    ]

    if any(signal in lower for signal in question_signals):
        return "question"

    if any(word in lower for word in ["book", "booking", "lesson"]):
        return "new_booking"

    return "question"


def extract_date_regex(text: str):
    lower = text.lower()

    month_names = "|".join(MONTHS.keys())
    pattern = rf"\b({month_names})\s+(\d{{1,2}})(?:,?\s+(\d{{4}}))?\b"

    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        month = MONTHS[match.group(1).lower()]
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else TODAY.year

        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

    if "tomorrow" in lower:
        return (TODAY + timedelta(days=1)).strftime("%Y-%m-%d")

    if "today" in lower:
        return TODAY.strftime("%Y-%m-%d")

    weekday_match = re.search(
        r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        lower
    )

    if weekday_match:
        target = WEEKDAYS[weekday_match.group(1)]
        delta = (target - TODAY.weekday()) % 7

        if delta == 0:
            delta = 7

        return (TODAY + timedelta(days=delta)).strftime("%Y-%m-%d")

    return None


def extract_time_regex(text: str):
    match = re.search(r"\b(\d{1,2})\s*(AM|PM|am|pm)\b", text)

    if match:
        hour = int(match.group(1))
        period = match.group(2).upper()

        if period == "PM" and hour < 12:
            hour += 12
        elif period == "AM" and hour == 12:
            hour = 0

        return f"{hour:02d}:00"

    match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)

    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        return f"{hour:02d}:{minute:02d}"

    lower = text.lower()

    if "morning" in lower:
        return "09:00"

    if "afternoon" in lower:
        return "14:00"

    if "evening" in lower:
        return "17:00"

    return None


def extract_name_regex(text: str):
    patterns = [
        r"under the name\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
        r"My name is\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
        r"my name is\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
        r"under\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
        r"I am\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
        r"I'm\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
    ]

    bad_names = {"the", "a", "an", "instructor", "name", "booking"}

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            name = match.group(1).strip()

            if name.lower() not in bad_names:
                return name

    return None


def extract_requested_instructor_regex(text: str):
    patterns = [
        r"with instructor\s+([A-Z][a-zA-Z]+)",
        r"instructor\s+([A-Z][a-zA-Z]+)",
        r"with\s+([A-Z][a-zA-Z]+)",
    ]

    bad_names = {"instructor", "the", "an", "a", "is", "available"}

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            name = match.group(1).strip()

            if name.lower() not in bad_names:
                return name

    return None


def extract_lesson_type_regex(text: str) -> str:
    lower = text.lower()

    if "advanced" in lower:
        return "advanced"

    if "intermediate" in lower:
        return "intermediate"

    if "beginner" in lower:
        return "beginner"

    if "private" in lower:
        return "private"

    if "group" in lower:
        return "group"

    return "unknown"


def extract_num_students_regex(text: str) -> int:
    lower = text.lower()

    match = re.search(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s*(?:people|persons|person|students|student|of us)\b",
        lower
    )

    if match:
        value = match.group(1)

        if value.isdigit():
            return int(value)

        return WORDS_TO_NUM.get(value, 1)

    if "myself" in lower or "for me" in lower:
        return 1

    return 1


def extract_with_regex(raw_email: str) -> dict:
    return {
        "student_name": extract_name_regex(raw_email),
        "lesson_type": extract_lesson_type_regex(raw_email),
        "date": extract_date_regex(raw_email),
        "time": extract_time_regex(raw_email),
        "number_of_students": extract_num_students_regex(raw_email),
        "requested_instructor": extract_requested_instructor_regex(raw_email),
        "intent": extract_intent_regex(raw_email),
    }

def normalize_extracted(data: dict) -> dict:
    if not isinstance(data, dict):
        data = {}

    try:
        number_of_students = int(data.get("number_of_students", 1) or 1)
    except Exception:
        number_of_students = 1

    return {
        "student_name": data.get("student_name"),
        "lesson_type": data.get("lesson_type") or "unknown",
        "date": data.get("date"),
        "time": data.get("time"),
        "number_of_students": number_of_students,
        "requested_instructor": data.get("requested_instructor"),
        "intent": data.get("intent") or "question",
    }

def find_instructor(date_str: str, time_str: str, lesson_type: str, requested: str):
    csv_path = "project/data/staff_availability.csv"

    if not os.path.exists(csv_path):
        csv_path = "data/staff_availability.csv"

        if not os.path.exists(csv_path):
            return {
                "assigned_instructor": None,
                "reason": "Staff availability file not found"
            }

    target_start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    target_end = target_start + timedelta(hours=1)

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        candidates = []

        for row in reader:
            if row.get("available", "false").lower() != "true":
                continue

            skill = row.get("skill_level", "").lower()

            if lesson_type == "intermediate" and skill not in ["intermediate", "advanced"]:
                continue

            if lesson_type == "advanced" and skill != "advanced":
                continue

            row_start = datetime.strptime(
                f"{row['date']} {row['start_time']}",
                "%Y-%m-%d %H:%M"
            )

            row_end = datetime.strptime(
                f"{row['date']} {row['end_time']}",
                "%Y-%m-%d %H:%M"
            )

            if row_start <= target_start and row_end >= target_end:
                candidates.append(row["instructor"])

    if not candidates:
        return {
            "assigned_instructor": None,
            "reason": "No available instructor for this time/skill"
        }

    if requested and requested in candidates:
        return {
            "assigned_instructor": requested,
            "reason": "Requested instructor available"
        }

    return {
        "assigned_instructor": candidates[0],
        "reason": "Matched by availability"
    }

def parse_email(raw_email: str, source_id: str = "unknown") -> dict:
    extracted = extract_with_groq(raw_email)
    if not extracted or extracted.get("intent") not in ALLOWED_INTENTS:
        print("⚠️ Using regex fallback")
        extracted = extract_with_regex(raw_email)
    else:
        if extracted.get("intent") == "new_booking":
            useful = any([
                extracted.get("date"),
                extracted.get("time"),
                extracted.get("student_name"),
            ])

            if not useful:
                print("⚠️ Groq returned weak booking data. Using regex fallback.")
                extracted = extract_with_regex(raw_email)

    extracted = normalize_extracted(extracted)

    raw_lower = raw_email.lower()

    if "advanced" in raw_lower and extracted["lesson_type"] in ["private", "group", "unknown"]:
        extracted["lesson_type"] = "advanced"

    manual_override = (
        extracted["number_of_students"] >= 5
        or extracted["lesson_type"] == "group"
    )
    
    relative_date_signals = [
        "tomorrow",
        "today",
        "next monday",
        "next tuesday",
        "next wednesday",
        "next thursday",
        "next friday",
        "next saturday",
        "next sunday",
    ]

    if any(signal in raw_lower for signal in relative_date_signals):
        regex_date = extract_date_regex(raw_email)

        if regex_date:
            extracted["date"] = regex_date

    approximate_time_signals = [
        "do not know the exact time",
        "don't know the exact time",
        "not sure about the time",
        "we haven't decided which day or time",
        "haven't decided which day or time",
    ]

    if any(signal in raw_lower for signal in approximate_time_signals):
        extracted["time"] = None

    booking_signals = ["book", "lesson", "reserve"]
    not_ready_signals = [
        "not ready",
        "prices",
        "price",
        "have not made a booking",
        "is it safe",
        "equipment is included",
    ]

    if (
        extracted["intent"] == "question"
        and any(signal in raw_lower for signal in booking_signals)
        and not any(signal in raw_lower for signal in not_ready_signals)
    ):
        extracted["intent"] = "new_booking"

    name = extracted["student_name"]

    date = extracted["date"]
    time = extracted["time"]
    lesson_type = extracted["lesson_type"]
    num_students = extracted["number_of_students"]
    requested = extracted["requested_instructor"]
    intent = extracted["intent"]

    assigned = {
        "assigned_instructor": None,
        "reason": "Needs manual review"
    }

    missing_fields = []

    if intent == "new_booking":
        if not date:
            missing_fields.append("date")

        if not time:
            missing_fields.append("time")

        if not name:
            missing_fields.append("student_name")

        if date and time and lesson_type != "unknown":
            assigned = find_instructor(date, time, lesson_type, requested)

    if manual_override:
        assigned["reason"] = "Large/group lesson needs manual review"

    calendar_start = None
    calendar_end = None

    if date and time:
        try:
            dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            calendar_start = dt.strftime("%Y-%m-%dT%H:%M:%S+04:00")
            calendar_end = (dt + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S+04:00")
        except ValueError:
            pass

    return {
        "source": "email",
        "source_id": source_id,
        "intent": intent,
        "student_name": name,
        "lesson_type": lesson_type,
        "date": date,
        "time": time,
        "number_of_students": num_students,
        "requested_instructor": requested,
        "assigned_instructor": assigned["assigned_instructor"],
        "assignment_reason": assigned["reason"],
        "missing_fields": missing_fields,
        "status": "pending" if (
            intent == "new_booking"
            and not missing_fields
            and assigned["assigned_instructor"]
            and not manual_override
        ) else "needs_manual_review",
        "calendar_start": calendar_start,
        "calendar_end": calendar_end,
        "raw_text": raw_email.strip()
    }