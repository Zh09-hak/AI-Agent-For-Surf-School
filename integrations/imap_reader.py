import email
import imaplib
import os
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _decode(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and \
               "attachment" not in str(part.get("Content-Disposition", "")).lower():
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                except Exception:
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "ignore")
    except Exception:
        return ""


def get_new_emails() -> list:
    host = os.getenv("IMAP_HOST", "imap.gmail.com")
    port = int(os.getenv("IMAP_PORT") or 993)
    user = os.getenv("IMAP_USER")
    password = os.getenv("IMAP_APP_PASSWORD")
    mailbox = os.getenv("IMAP_MAILBOX", "INBOX")
    only_unseen = (os.getenv("IMAP_ONLY_UNSEEN", "true").lower() in ("1", "true", "yes"))

    if not user or not password:
        print("⚠️ IMAP_USER / IMAP_APP_PASSWORD are not set — returning an empty list")
        return []

    results = []
    conn = None
    try:
        conn = imaplib.IMAP4_SSL(host, port)
        conn.login(user, password)
        conn.select(mailbox)

        criteria = "UNSEEN" if only_unseen else "ALL"
        _, data = conn.search(None, criteria)
        ids = (data[0] or b"").split()

        for num in ids:
            _, msg_data = conn.fetch(num, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])

            message_id = _decode(msg.get("Message-ID")).strip()
            from_addr = _decode(msg.get("From"))
            subject = _decode(msg.get("Subject"))
            body = _body(msg).strip()

            if not body:
                continue

            try:
                received = parsedate_to_datetime(msg.get("Date")).isoformat()
            except Exception:
                received = datetime.now().isoformat()

            safe_id = (message_id or f"imap_{num.decode()}").replace("<", "").replace(">", "")[:80]

            results.append({
                "source_id": safe_id,
                "raw_text": body,
                "from_addr": from_addr,
                "subject": subject,
                "message_id": message_id,
                "received_at": received,
            })

            if only_unseen:
                conn.store(num, "+FLAGS", "\\Seen")

    except imaplib.IMAP4.error as e:
        print(f"❌ IMAP auth error: {e}")
    except Exception as e:
        print(f"❌ IMAP error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            try:
                conn.logout()
            except Exception:
                pass

    return results