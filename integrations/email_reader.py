import os
import shutil

def get_new_emails(raw_dir: str = "data/raw_emails") -> list[dict]:
    """
    Returns [{"source_id": "email_01", "raw_text": "..."}]
    Reads .txt / .eml files from raw_dir.
    """
    processed_dir = os.path.join("data", "processed_emails")
    os.makedirs(processed_dir, exist_ok=True)
    
    emails = []
    if not os.path.exists(raw_dir):
        return emails

    for filename in os.listdir(raw_dir):
        if filename.endswith(".txt") or filename.endswith(".eml"):
            file_path = os.path.join(raw_dir, filename)
            
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            source_id = os.path.splitext(filename)[0]
            emails.append({
                "source_id": source_id,
                "raw_text": content
            })
            
            # Ֆայլը տեղափոխում ենք processed_emails թղթապանակ
            destination_path = os.path.join(processed_dir, filename)
            shutil.move(file_path, destination_path)
            
    return emails