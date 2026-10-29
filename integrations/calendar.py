import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# API-ի թույլտվությունների շրջանակը
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'credentials.json'

def get_calendar_service():
    """Ստեղծում և վերադարձնում է Google Calendar API-ի ծառայությունը"""
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=creds)
    return service

def create_calendar_event(summary: str, start_time: str, end_time: str, description: str = "", calendar_id: str = "primary"):
    """
    Ստեղծում է նոր իրադարձություն (դաս) Google Calendar-ում:
    start_time/end_time ձևաչափը՝ '2026-11-01T14:00:00+04:00'
    """
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
        print(f"Դասը հաջողությամբ ավելացվեց օրացույց. {created_event.get('htmlLink')}")
        return created_event
        
    except Exception as e:
        raise Exception(f"Failed to create Google Calendar event: {str(e)}")