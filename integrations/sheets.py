import os
import gspread
from dotenv import load_dotenv

load_dotenv()

def get_sheets_client():
    """Ստեղծում և վերադարձնում է gspread հաճախորդը service_account-ի միջոցով"""
    creds_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")
    gc = gspread.service_account(filename=creds_file)
    return gc

def get_proposals_sheet():
    """Բացում և վերադարձնում է proposals աղյուսակը (worksheet)"""
    sheet_url = os.getenv("GOOGLE_SHEET_URL")
    if not sheet_url:
        raise Exception("GOOGLE_SHEET_URL environment variable is missing.")
    
    gc = get_sheets_client()
    spreadsheet = gc.open_by_url(sheet_url)
    
    # Փորձում ենք վերցնել 'proposals' անունով թերթը (tab), կամ վերցնում ենք առաջինը
    try:
        worksheet = spreadsheet.worksheet("proposals")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.get_worksheet(0)
        
    return worksheet

def save_proposal(proposal_data: dict):
    """
    Պահպանում է նոր հայտը Google Sheets-ում:
    proposal_data-ն կարող է պարունակել՝ client_name, date, time, instructor, status և այլն:
    """
    try:
        worksheet = get_proposals_sheet()
        
        # Օրինակելի սյունակների հերթականություն (կարող եք հարմարեցնել ըստ ձեր աղյուսակի)
        row_values = [
            proposal_data.get("source_id", ""),
            proposal_data.get("client_name", ""),
            proposal_data.get("date", ""),
            proposal_data.get("time", ""),
            proposal_data.get("instructor", ""),
            proposal_data.get("status", "pending"),
            proposal_data.get("calendar_event_id", "")
        ]
        
        worksheet.append_row(row_values)
        print("Հայտը հաջողությամբ պահպանվեց Google Sheets-ում։")
        return True
    except Exception as e:
        raise Exception(f"Failed to save proposal to Google Sheets: {str(e)}")

def get_pending_proposals() -> list[dict]:
    """
    Կարդում է բոլոր 'pending' կարգավիճակ ունեցող հայտերը աղյուսակից:
    """
    try:
        worksheet = get_proposals_sheet()
        records = worksheet.get_all_records()
        
        pending_list = []
        for row in records:
            # Ստուգում ենք, արդյոք status-ը pending է (հաշվի առնելով մեծատառ/փոքրատառերը)
            status = str(row.get("status", "")).strip().lower()
            if status == "pending":
                pending_list.append(row)
                
        return pending_list
    except Exception as e:
        raise Exception(f"Failed to read pending proposals from Google Sheets: {str(e)}")

def update_proposal_status(source_id: str, new_status: str, calendar_event_id: str = ""):
    """
    Թարմացնում է հայտի կարգավիճակը աղյուսակում ըստ source_id-ի:
    """
    try:
        worksheet = get_proposals_sheet()
        
        # Գտնում ենք տողը ըստ source_id-ի (ենթադրենք առաջին սյունակն է)
        cell = worksheet.find(str(source_id))
        if cell:
            row_idx = cell.row
            # Ենթադրենք status-ը 6-րդ սյունակն է, իսկ calendar_event_id-ն՝ 7-րդ
            worksheet.update_cell(row_idx, 6, new_status)
            if calendar_event_id:
                worksheet.update_cell(row_idx, 7, calendar_event_id)
            print(f"Հայտ {source_id}-ի կարգավիճակը հաջողությամբ թարմացվեց՝ {new_status}:")
            return True
        else:
            raise Exception(f"Proposal with source_id {source_id} not found in sheet.")
            
    except Exception as e:
        raise Exception(f"Failed to update proposal status: {str(e)}")