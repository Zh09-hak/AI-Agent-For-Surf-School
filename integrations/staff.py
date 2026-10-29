import csv
import os

def get_available_staff(date_str: str = None, time_str: str = None) -> list[dict]:
    csv_path = os.path.join("project", "data", "staff_availability.csv")
    results = []
    
    if not os.path.exists(csv_path):
        return results

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if date_str and row.get("date") != date_str:
                continue
            results.append(dict(row))
            
    return results