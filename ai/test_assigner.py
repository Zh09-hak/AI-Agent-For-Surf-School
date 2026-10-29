import json
from ai.parser import parse_email
from ai.assigner import assign_instructor

with open("project/data/parsed_results.json", "r", encoding="utf-8") as f:
    parsed_emails = json.load(f)

for email_data in parsed_emails:
    final_proposal = assign_instructor(email_data)
    print(f"=== {final_proposal['source_id']} ===")
    print(f"Student: {final_proposal.get('student_name')}")
    print(f"Assigned: {final_proposal.get('assigned_instructor')}")
    print(f"Reason: {final_proposal.get('assignment_reason')}")
    print(f"Status: {final_proposal.get('status')}")
    print()