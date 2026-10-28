# app.py
import json
from datetime import datetime, timedelta
from pathlib import Path
import streamlit as st

REQUESTS = Path("data/requests.json")
DECISIONS = Path("data/decisions.json")

STATUSES = ["pending", "needs_manual_review"]
INTENTS = ["new_booking", "cancellation", "reschedule", "question"]
LESSONS = ["beginner", "intermediate", "advanced", "private", "group", "unknown"]
INSTRUCTORS = ["Alex"]  # TODO: load from project/data/staff_availability.csv
TZ = "+04:00"
DEFAULT_MINUTES = 60  # UI default for calendar_end; confirm with backend


def read(path):
    return json.loads(path.read_text()) if path.exists() else []


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def create_calendar_event(p):
    """Wrap integrations/calendar.py; adjust to its real function name and args."""
    try:
        from integrations.calendar import create_event
        return create_event(
            summary=f"{p['lesson_type']} lesson - {p['student_name']}",
            start=p["calendar_start"],
            end=p["calendar_end"],
        )
    except ImportError:
        return f"fake_event_{p['source_id']}"  # stub until the integration works


def build_calendar(date_str, time_str):
    start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    end = start + timedelta(minutes=DEFAULT_MINUTES)
    fmt = "%Y-%m-%dT%H:%M:%S"
    return start.strftime(fmt) + TZ, end.strftime(fmt) + TZ


def missing_of(p):
    return [k for k in ("student_name", "date", "time") if not p.get(k)]


def decide(items, i, decision, event_id=None):
    p = items.pop(i)
    log = read(DECISIONS)
    log.append({"decision": decision, "calendar_event_id": event_id,
                "decided_at": datetime.now().isoformat(timespec="seconds"), "request": p})
    write(DECISIONS, log)
    write(REQUESTS, items)
    st.session_state["msg"] = (
        f"Approved. Calendar event {event_id} created." if decision == "approved"
        else f"Rejected {p['source_id']}."
    )
    st.rerun()


def requests_page():
    items = read(REQUESTS)
    if "msg" in st.session_state:
        st.success(st.session_state.pop("msg"))

    st.sidebar.subheader("Filters")
    f_status = st.sidebar.multiselect("Status", STATUSES, default=STATUSES)
    f_intent = st.sidebar.multiselect("Intent", INTENTS, default=INTENTS)

    shown = [(i, p) for i, p in enumerate(items)
             if p["status"] in f_status and p["intent"] in f_intent]
    st.subheader(f"Requests ({len(shown)})")

    for i, p in shown:
        no_instructor = not p.get("assigned_instructor")
        flag = " ⚠ MANUAL REVIEW" if no_instructor or p["status"] == "needs_manual_review" else ""
        title = (f"{p['source_id']} · {p.get('student_name') or '?'} · {p['lesson_type']} · "
                 f"{p.get('date')} {p.get('time')} · {p['number_of_students']} student(s) · "
                 f"{p['intent']} · {p.get('assigned_instructor') or 'unassigned'} · {p['status']}{flag}")
        key = f"{i}_{p['source_id']}"

        with st.expander(title):
            if p.get("missing_fields"):
                st.warning("Missing: " + ", ".join(p["missing_fields"]))
            if no_instructor:
                st.error("No instructor assigned: manual review required")

            st.write(f"**Requested instructor:** {p.get('requested_instructor')}")
            st.write(f"**Assigned instructor:** {p.get('assigned_instructor')}")
            st.write(f"**Assignment reason:** {p.get('assignment_reason')}")
            st.write(f"**Calendar:** {p.get('calendar_start')} → {p.get('calendar_end')}")
            with st.expander("Raw email"):
                st.text(p.get("raw_text", ""))

            c1, c2 = st.columns([3, 1])
            choice = c1.selectbox("Assign instructor", INSTRUCTORS, key=f"ins_{key}")
            if c2.button("Assign", key=f"as_{key}"):
                p["assigned_instructor"] = choice
                p["assignment_reason"] = "manual assignment"
                write(REQUESTS, items)
                st.rerun()

            can_approve = (p["intent"] == "new_booking" and p.get("assigned_instructor")
                           and p.get("calendar_start") and p.get("calendar_end"))

            b1, b2, b3 = st.columns(3)
            if b1.button("Approve + Create Calendar Event", key=f"ap_{key}", disabled=not can_approve):
                decide(items, i, "approved", create_calendar_event(p))
            if b2.button("Reject", key=f"rj_{key}"):
                decide(items, i, "rejected")
            if b3.button("Needs Manual Review", key=f"mr_{key}"):
                p["status"] = "needs_manual_review"
                write(REQUESTS, items)
                st.rerun()


def form_page():
    items = read(REQUESTS)
    options = ["New booking"] + [f"{i}: {p['source_id']} · {p.get('student_name')}" for i, p in enumerate(items)]
    sel = st.selectbox("Create or edit", options)
    idx = None if sel == "New booking" else int(sel.split(":")[0])
    p = items[idx] if idx is not None else {}

    with st.form(f"form_{sel}"):
        name = st.text_input("Student name", p.get("student_name") or "")
        lesson = st.selectbox("Lesson type", LESSONS,
                              index=LESSONS.index(p.get("lesson_type", "unknown")))
        date = st.date_input("Date", datetime.strptime(p["date"], "%Y-%m-%d").date()
                             if p.get("date") else None)
        time = st.time_input("Time", datetime.strptime(p["time"], "%H:%M").time()
                             if p.get("time") else None)
        n = st.number_input("Number of students", 1, 50, int(p.get("number_of_students", 1)))
        req = st.text_input("Requested instructor", p.get("requested_instructor") or "")
        opts = [""] + INSTRUCTORS
        cur = p.get("assigned_instructor") or ""
        instructor = st.selectbox("Assigned instructor", opts, index=opts.index(cur) if cur in opts else 0)

        if st.form_submit_button("Save"):
            rec = {
                "source": p.get("source", "manual"),
                "source_id": p.get("source_id", f"manual_{len(items) + 1:03d}"),
                "intent": p.get("intent", "new_booking"),
                "student_name": name or None,
                "lesson_type": lesson,
                "date": str(date) if date else None,
                "time": time.strftime("%H:%M") if time else None,
                "number_of_students": int(n),
                "requested_instructor": req or None,
                "assigned_instructor": instructor or None,
                "assignment_reason": "manual assignment" if instructor else p.get("assignment_reason", "manual entry"),
                "raw_text": p.get("raw_text", ""),
            }
            rec["missing_fields"] = missing_of(rec)
            rec["calendar_start"], rec["calendar_end"] = (
                build_calendar(rec["date"], rec["time"]) if rec["date"] and rec["time"] else (None, None))
            rec["status"] = "pending" if instructor and not rec["missing_fields"] else "needs_manual_review"
            if idx is None:
                items.append(rec)
            else:
                items[idx] = rec
            write(REQUESTS, items)
            st.success("Saved.")


st.title("Surf School AI Scheduler")
page = st.sidebar.radio("Page", ["Requests", "Create / Edit Booking"])
requests_page() if page == "Requests" else form_page()