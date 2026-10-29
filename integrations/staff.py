import csv
import os

def get_available_staff(date_str: str = None, time_str: str = None) -> list[dict]:
    """
    Reads project/data/staff_availability.csv.
    Returns one dict per CSV row, keeping the original column names:
    instructor, date, start_time, end_time, available, skill_level
    """
    csv_path = os.path.join("data", "staff_availability.csv")
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