import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'credentials.json'

def get_calendar_service():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=creds)
    return service

def create_calendar_event(summary: str, start_time: str, end_time: str, description: str = "", calendar_id: str = "primary"):
    try:
        service = get_calendar_service()
        
        event = {
            'summary': summary,
            'description': description or "",
            'start': {
                'dateTime': start_time,
                'timeZone': 'Asia/Yerevan',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Asia/Yerevan',
            },
        }
        
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"Sucsessful Operation. {created_event.get('htmlLink')}")
        return created_event
        
    except Exception as e:
        raise Exception(f"Failed to create Google Calendar event: {str(e)}")