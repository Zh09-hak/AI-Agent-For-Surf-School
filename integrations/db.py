import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("DATABASE_PATH") or (ROOT / "project" / "data" / "surf_school.db"))

QUEUE_STATUSES = ("pending", "needs_manual_review")

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    TEXT UNIQUE,
    message_id   TEXT,
    from_addr    TEXT,
    subject      TEXT,
    received_at  TEXT,
    content_hash TEXT UNIQUE,
    raw_text     TEXT,
    status       TEXT DEFAULT 'new',
    error        TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS proposals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id           TEXT UNIQUE,
    email_id            INTEGER,
    intent              TEXT,
    student_name        TEXT,
    student_name_norm   TEXT,
    lesson_type         TEXT,
    date                TEXT,
    time                TEXT,
    number_of_students  INTEGER DEFAULT 1,
    requested_instructor TEXT,
    assigned_instructor TEXT,
    assignment_reason   TEXT,
    status              TEXT,
    safety_flags        TEXT,
    gate_reason         TEXT,
    calendar_start      TEXT,
    calendar_end        TEXT,
    calendar_event_id   TEXT,
    fingerprint         TEXT,
    missing_fields      TEXT,
    raw_text            TEXT,
    decided_by          TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    decided_at          TEXT,
    FOREIGN KEY (email_id) REFERENCES emails(id)
);

CREATE TABLE IF NOT EXISTS bookings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id        INTEGER,
    source_id          TEXT,
    instructor         TEXT NOT NULL,
    date               TEXT NOT NULL,
    start_time         TEXT NOT NULL,
    end_time           TEXT NOT NULL,
    student_name       TEXT,
    student_name_norm  TEXT,
    number_of_students INTEGER DEFAULT 1,
    lesson_type        TEXT,
    calendar_event_id  TEXT,
    status             TEXT DEFAULT 'confirmed',
    created_by         TEXT,
    created_at         TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (proposal_id) REFERENCES proposals(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_booking_slot
    ON bookings(instructor, date, start_time) WHERE status = 'confirmed';

CREATE INDEX IF NOT EXISTS ix_booking_instructor_date ON bookings(instructor, date);
CREATE INDEX IF NOT EXISTS ix_booking_student         ON bookings(student_name_norm, date);
CREATE INDEX IF NOT EXISTS ix_proposal_status         ON proposals(status);
CREATE INDEX IF NOT EXISTS ix_proposal_fp             ON proposals(fingerprint);
CREATE INDEX IF NOT EXISTS ix_emails_sender           ON emails(from_addr, created_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT DEFAULT (datetime('now')),
    actor       TEXT,
    action      TEXT,
    entity_type TEXT,
    entity_id   TEXT,
    details     TEXT
);

CREATE TRIGGER IF NOT EXISTS prevent_double_booking
BEFORE INSERT ON bookings
WHEN NEW.status = 'confirmed'
BEGIN
    SELECT CASE 
        WHEN EXISTS (
            SELECT 1 FROM bookings 
            WHERE instructor = NEW.instructor 
              AND date = NEW.date 
              AND start_time = NEW.start_time 
              AND status = 'confirmed'
              AND id != NEW.id
        ) THEN RAISE(ABORT, 'Double booking: instructor already booked at this time')
    END;
END;
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as c:
        c.executescript(SCHEMA)
    return DB_PATH

def audit(actor, action, entity_type=None, entity_id=None, details=None):
    with get_conn() as c:
        c.execute(
            "INSERT INTO audit_log (actor, action, entity_type, entity_id, details) VALUES (?,?,?,?,?)",
            (actor, action, entity_type, str(entity_id) if entity_id is not None else None,
             json.dumps(details, ensure_ascii=False, default=str) if details else None),
        )

def find_email_by_hash(content_hash):
    with get_conn() as c:
        r = c.execute("SELECT * FROM emails WHERE content_hash = ?", (content_hash,)).fetchone()
        return dict(r) if r else None


def find_email_by_message_id(message_id):
    if not message_id:
        return None
    with get_conn() as c:
        r = c.execute("SELECT * FROM emails WHERE message_id = ?", (message_id,)).fetchone()
        return dict(r) if r else None


def insert_email(source_id, content_hash, raw_text, from_addr=None,
                 subject=None, message_id=None, received_at=None):
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO emails
               (source_id, message_id, from_addr, subject, received_at, content_hash, raw_text, status)
               VALUES (?,?,?,?,?,?,?, 'processing')""",
            (source_id, message_id, from_addr, subject, received_at, content_hash, raw_text),
        )
        return cur.lastrowid


def set_email_status(email_id, status, error=None):
    with get_conn() as c:
        c.execute("UPDATE emails SET status = ?, error = ? WHERE id = ?", (status, error, email_id))


def count_sender_recent(from_addr, minutes=60):
    if not from_addr:
        return 0
    with get_conn() as c:
        r = c.execute(
            """SELECT COUNT(*) AS n FROM emails
               WHERE from_addr = ? AND created_at >= datetime('now', ?)""",
            (from_addr, f"-{int(minutes)} minutes"),
        ).fetchone()
        return r["n"] if r else 0

def proposal_exists(source_id):
    with get_conn() as c:
        return c.execute("SELECT 1 FROM proposals WHERE source_id = ?", (source_id,)).fetchone() is not None


def insert_proposal(p: dict, email_id=None):
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO proposals
               (source_id, email_id, intent, student_name, student_name_norm, lesson_type,
                date, time, number_of_students, requested_instructor, assigned_instructor,
                assignment_reason, status, safety_flags, gate_reason,
                calendar_start, calendar_end, fingerprint, missing_fields, raw_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                p.get("source_id"), email_id, p.get("intent"), p.get("student_name"),
                p.get("student_name_norm"), p.get("lesson_type"), p.get("date"), p.get("time"),
                int(p.get("number_of_students") or 1), p.get("requested_instructor"),
                p.get("assigned_instructor"), p.get("assignment_reason"), p.get("status"),
                json.dumps(p.get("safety_flags") or [], ensure_ascii=False),
                p.get("gate_reason"), p.get("calendar_start"), p.get("calendar_end"),
                p.get("fingerprint"), json.dumps(p.get("missing_fields") or [], ensure_ascii=False),
                p.get("raw_text"),
            ),
        )
        return cur.lastrowid


def row_to_proposal(r) -> dict:
    d = dict(r)
    for k in ("safety_flags", "missing_fields"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except (TypeError, ValueError):
            d[k] = []
    return d


def get_proposal(source_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM proposals WHERE source_id = ?", (source_id,)).fetchone()
        return row_to_proposal(r) if r else None


def get_queue(statuses=QUEUE_STATUSES):
    q = ",".join("?" * len(statuses))
    with get_conn() as c:
        rows = c.execute(
            f"SELECT * FROM proposals WHERE status IN ({q}) ORDER BY created_at DESC", statuses
        ).fetchall()
        return [row_to_proposal(r) for r in rows]


def update_proposal(source_id, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as c:
        c.execute(f"UPDATE proposals SET {cols} WHERE source_id = ?", (*fields.values(), source_id))


def fingerprint_exists(fp, exclude_source_id=None):
    if not fp:
        return False
    with get_conn() as c:
        if exclude_source_id:
            r = c.execute(
                """SELECT 1 FROM proposals
                   WHERE fingerprint = ? AND source_id != ?
                     AND status NOT IN ('rejected','cancelled') LIMIT 1""",
                (fp, exclude_source_id),
            ).fetchone()
        else:
            r = c.execute(
                "SELECT 1 FROM proposals WHERE fingerprint = ? AND status NOT IN ('rejected','cancelled') LIMIT 1",
                (fp,),
            ).fetchone()
        return r is not None

def get_active_bookings(instructor, date_str):
    with get_conn() as c:
        rows = c.execute(
            """SELECT * FROM bookings
               WHERE instructor = ? AND date = ? AND status = 'confirmed'""",
            (instructor, date_str),
        ).fetchall()
        return [dict(r) for r in rows]


def count_customer_active(name_norm, horizon_days=14):
    if not name_norm:
        return 0
    with get_conn() as c:
        r = c.execute(
            """SELECT COUNT(*) AS n FROM bookings
               WHERE student_name_norm = ? AND status = 'confirmed'
                 AND date >= date('now') AND date <= date('now', ?)""",
            (name_norm, f"+{int(horizon_days)} days"),
        ).fetchone()
        return r["n"] if r else 0


def count_customer_same_day(name_norm, date_str):
    if not name_norm or not date_str:
        return 0
    with get_conn() as c:
        r = c.execute(
            """SELECT COUNT(*) AS n FROM bookings
               WHERE student_name_norm = ? AND date = ? AND status = 'confirmed'""",
            (name_norm, date_str),
        ).fetchone()
        return r["n"] if r else 0


def insert_booking(p: dict, instructor, start_time, end_time, calendar_event_id, created_by):
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO bookings
               (proposal_id, source_id, instructor, date, start_time, end_time,
                student_name, student_name_norm, number_of_students, lesson_type,
                calendar_event_id, status, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                p.get("id"), p.get("source_id"), instructor, p.get("date"), start_time, end_time,
                p.get("student_name"), p.get("student_name_norm"),
                int(p.get("number_of_students") or 1), p.get("lesson_type"),
                calendar_event_id, "confirmed", created_by,
            ),
        )
        return cur.lastrowid


def confirm_booking(source_id, instructor, calendar_event_id=None, actor="human"):
    print(f"🔐 confirm_booking() called: source_id={source_id}, instructor={instructor}")
    
    p = get_proposal(source_id)
    if not p:
        print(f"❌ Proposal {source_id} not found in the database")
        raise ValueError(f"Proposal {source_id} not found")
    
    print(f"✅ Proposal found: {p.get('student_name')}, {p.get('date')} {p.get('time')}")
    
    if not p.get("date") or not p.get("time"):
        print(f"❌ Proposal {source_id} does not have date/time")
        raise ValueError(f"Proposal {source_id} has no date/time")

    end_time = p.get("calendar_end")
    if end_time:
        end_time = end_time[11:16]
    else:
        start = datetime.strptime(f"{p['date']} {p['time']}", "%Y-%m-%d %H:%M")
        end_time = (start + timedelta(minutes=60)).strftime("%H:%M")

    print(f"📅 Creating a booking: {p['date']} {p['time']}-{end_time}, instructor={instructor}")
    
    try:
        booking_id = insert_booking(p, instructor, p["time"], end_time, calendar_event_id, actor)
        print(f"✅ Booking created: booking_id={booking_id}")
    except Exception as e:
        print(f"❌ ERROR while creating a booking: {e}")
        raise

    with get_conn() as c:
        c.execute(
            """UPDATE proposals SET status='approved', assigned_instructor=?,
               calendar_event_id=?, decided_by=?, decided_at=datetime('now')
               WHERE source_id=?""",
            (instructor, calendar_event_id, actor, source_id),
        )
        print(f"✅ Proposal updated: status='approved'")
    
    audit(actor, "confirm_booking", "proposal", source_id,
          {"instructor": instructor, "booking_id": booking_id, "event": calendar_event_id})
    print(f"✅ Audit log recorded")
    
    return booking_id


def reject_proposal(source_id, actor="human", reason=None):
    with get_conn() as c:
        c.execute(
            """UPDATE proposals SET status='rejected', decided_by=?, decided_at=datetime('now'),
               assignment_reason=COALESCE(?, assignment_reason) WHERE source_id=?""",
            (actor, reason, source_id),
        )
    audit(actor, "reject_proposal", "proposal", source_id, {"reason": reason})


def mark_manual_review(source_id, actor="human", reason=None):
    with get_conn() as c:
        c.execute(
            """UPDATE proposals SET status='needs_manual_review', decided_by=?,
               decided_at=datetime('now'), assignment_reason=COALESCE(?, assignment_reason)
               WHERE source_id=?""",
            (actor, reason, source_id),
        )
    audit(actor, "mark_manual_review", "proposal", source_id, {"reason": reason})


def stats():
    with get_conn() as c:
        rows = c.execute("SELECT status, COUNT(*) AS n FROM proposals GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}