from ai.parser import parse_email
from integrations.email_reader import get_new_emails
from integrations.calendar import create_calendar_event
import json
from pathlib import Path

def main():
    
    emails = get_new_emails()

    if not emails:
        return "Namak chka"
    res = []
    for email in emails:
        print(f"Processing: {email['source_id']}")
        raw_text = email["raw_text"]
        parser = parse_email(raw_text,email['source_id'])
        res.append(parser)
    output_path = Path(__file__).resolve().parent / "project" / "data" / "parsed_results.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(res, file, ensure_ascii=False, indent=4)

    print(f"Saved {len(res)} parsed emails to {output_path}")
    
    with output_path.open("r", encoding="utf-8") as file:
        results = json.load(file)

    print(type(results))
    print(len(results))

    # for res in result:
    #     ...
    result = results[0]
    
    create_calendar_event (
    calendar_id="2015ed68f464fa5dc7f8972eca8ed985530e04a5327c888cde52c542984f7435@group.calendar.google.com",
    summary=f"Surf Lesson - {result['student_name']}",
    start_time=result["calendar_start"],
    end_time=result["calendar_end"],
    description=result["raw_text"]
    )
    
#def parse_email(raw_email: str, source_id: str = "unknown") -> dict:
#def create_calendar_event(calendar_id: str, summary: str, start_time: str, end_time: str, description: str = ""):


if __name__ == "__main__":
    main()