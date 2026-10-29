import json
from pathlib import Path
from integrations.email_reader import get_new_emails
from ai.parser import parse_email
from ai.assigner import assign_instructor

REQUESTS_PATH = Path("frontend/data/requests.json")

def main():
    emails = get_new_emails("project/data/raw_emails")
    if not emails:
        print("📭 No new emails in project/data/raw_emails")
        return

    if REQUESTS_PATH.exists():
        requests = json.loads(REQUESTS_PATH.read_text(encoding="utf-8"))
    else:
        requests = []

    existing_ids = {r["source_id"] for r in requests}
    processed_count = 0

    for email in emails:
        if email["source_id"] in existing_ids:
            continue
        
        print(f"⚙️ Processing {email['source_id']}...")
        
        parsed = parse_email(email["raw_text"], source_id=email["source_id"])
        final = assign_instructor(parsed)
        
        requests.append(final)
        existing_ids.add(final["source_id"])
        processed_count += 1

    REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    REQUESTS_PATH.write_text(json.dumps(requests, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"✅ Done! Processed {processed_count} emails. Total requests in UI: {len(requests)}")

if __name__ == "__main__":
    main()