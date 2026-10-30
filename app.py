import json
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from ai import safety
from ai.parser import parse_email
from ai.assigner import assign_instructor
from integrations import db

MIRROR_PATH = ROOT / "frontend" / "data" / "requests.json"


def fetch_emails() -> list:
    source = (os.getenv("EMAIL_SOURCE") or "folder").lower()
    if source == "imap":
        from integrations.imap_reader import get_new_emails as imap_get
        return imap_get()
    from integrations.email_reader import get_new_emails as folder_get
    return folder_get(str(ROOT / "project" / "data" / "raw_emails"))


def process_email(msg: dict) -> dict:
    raw_text = msg.get("raw_text") or ""
    source_id = msg.get("source_id") or "unknown"
    from_addr = msg.get("from_addr")
    chash = safety.content_hash(raw_text)

    if msg.get("message_id") and db.find_email_by_message_id(msg["message_id"]):
        db.audit("system", "skip_duplicate_message_id", "email", source_id)
        return {"skipped": "duplicate_message_id", "source_id": source_id}

    dup = db.find_email_by_hash(chash)
    if dup:
        db.audit("system", "skip_duplicate_content", "email", source_id,
                 {"first_seen_as": dup.get("source_id")})
        return {"skipped": "duplicate_content", "source_id": source_id,
                "first_seen_as": dup.get("source_id")}

    if db.proposal_exists(source_id):
        db.audit("system", "skip_existing_proposal", "email", source_id)
        return {"skipped": "already_processed", "source_id": source_id}

    email_id = db.insert_email(
        source_id=source_id, content_hash=chash, raw_text=raw_text,
        from_addr=from_addr, subject=msg.get("subject"),
        message_id=msg.get("message_id"), received_at=msg.get("received_at"),
    )

    try:
        p = parse_email(raw_text, source_id=source_id)
        p["from_addr"] = from_addr
        p["student_name_norm"] = safety.normalize_name(p.get("student_name"))
        p["fingerprint"] = safety.fingerprint(
            p.get("student_name"), p.get("date"), p.get("time"), p.get("lesson_type")
        )
        flags = safety.check_time_sanity(p.get("date"), p.get("time"))
        if p.get("intent") == "new_booking" and not flags:
            flags += safety.check_customer_rules(
                p.get("student_name"), p.get("student_name_norm"),
                p.get("date"), p.get("fingerprint"), from_addr
            )
        p["safety_flags"] = sorted(set(flags))
        p = assign_instructor(p)
        if p.get("assigned_instructor") and p.get("date") and p.get("time"):
            conflict_flags = safety.check_instructor_availability(
                p["assigned_instructor"], p["date"], p["time"]
            )
            if conflict_flags:
                p["safety_flags"] = p.get("safety_flags", []) + conflict_flags
                p["assignment_reason"] = f"{p.get('assignment_reason')} | INSTRUCTOR TIME CONFLICT"
        can_auto, reason = safety.gate(p, p["safety_flags"])
        p["gate_reason"] = reason

        if can_auto:
            event_id = _create_calendar_event(p)
            p["calendar_event_id"] = event_id
            p["status"] = "auto_approved"
            p["assignment_reason"] = f"{p.get('assignment_reason')} | auto-approved: {reason}"
            db.insert_proposal(p, email_id=email_id)
            db.confirm_booking(source_id, p["assigned_instructor"], event_id, actor="ai")
            db.set_email_status(email_id, "auto_approved")
            db.audit("ai", "auto_approve", "proposal", source_id,
                     {"instructor": p["assigned_instructor"], "event": event_id})
        else:
            p["status"] = "needs_manual_review"
            if p.get("assignment_reason") and reason != "all_checks_passed":
                p["assignment_reason"] = f"{p['assignment_reason']} | gate: {reason}"
            db.insert_proposal(p, email_id=email_id)
            db.set_email_status(email_id, "queued_for_review")
            db.audit("ai", "queue_manual_review", "proposal", source_id,
                     {"gate_reason": reason, "flags": p["safety_flags"]})

        return p

    except Exception as e:
        db.set_email_status(email_id, "error", str(e))
        db.audit("system", "processing_error", "email", source_id, {"error": str(e)})
        raise


def _create_calendar_event(p: dict):
    from integrations.calendar import create_calendar_event
    ev = create_calendar_event(
        summary=f"{p['lesson_type']} lesson - {p.get('student_name', 'Unknown')}",
        start_time=p["calendar_start"],
        end_time=p["calendar_end"],
        description=(f"Instructor: {p.get('assigned_instructor')}\n"
                     f"Students: {p.get('number_of_students')}\n"
                     f"Auto-approved by AI\nSource: {p.get('source_id')}"),
        calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary"),
    )
    return ev["id"] if isinstance(ev, dict) else str(ev)


def sync_mirror():
    queue = db.get_queue()
    MIRROR_PATH.parent.mkdir(parents=True, exist_ok=True)
    MIRROR_PATH.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(queue)


def run_once(verbose=True) -> dict:
    db.init_db()
    emails = fetch_emails()
    result = {"new": len(emails), "auto": 0, "manual": 0, "skipped": 0, "errors": 0}

    for msg in emails:
        try:
            out = process_email(msg)
        except Exception as e:
            result["errors"] += 1
            if verbose:
                print(f"  ❌ {msg.get('source_id')}: {e}")
            continue

        if out.get("skipped"):
            result["skipped"] += 1
            if verbose:
                print(f"  ⏭  {out['source_id']}: skipped ({out['skipped']})")
        elif out.get("status") == "auto_approved":
            result["auto"] += 1
            if verbose:
                print(f"  🤖 {out['source_id']}: AUTO → {out['assigned_instructor']} "
                      f"{out['date']} {out['time']}")
        else:
            result["manual"] += 1
            if verbose:
                print(f"  👤 {out['source_id']}: MANUAL → {out.get('gate_reason')}")

    result["queue"] = sync_mirror()
    if verbose:
        print(f"✅ new={result['new']} auto={result['auto']} manual={result['manual']} "
              f"skipped={result['skipped']} errors={result['errors']} queue={result['queue']}")
    return result


def main():
    db.init_db()
    print(f"🗄  DB: {db.DB_PATH}")
    print(f"🔐 Auto-approve mode: {safety.AUTO_APPROVE_MODE}")
    run_once()


if __name__ == "__main__":
    main()