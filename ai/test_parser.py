import os
import json
from ai.parser import parse_email

EMAIL_DIR = 'project/data/sample_emails' 

def run_tests():
    results = []
    files = sorted([f for f in os.listdir(EMAIL_DIR) if f.endswith('.txt')])
    
    for filename in files:
        with open(os.path.join(EMAIL_DIR, filename), 'r', encoding='utf-8') as f:
            raw_text = f.read()
            
        source_id = filename.replace('.txt', '')
        parsed = parse_email(raw_text, source_id)
        results.append(parsed)
        
        print(f"--- {source_id} ---")
        print(json.dumps(parsed, indent=2))
        print("\n")
    output_path = 'project/data/parsed_results.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
        
    print(f"✅ Parsed {len(results)} emails. Saved to {output_path}")

if __name__ == "__main__":
    run_tests()