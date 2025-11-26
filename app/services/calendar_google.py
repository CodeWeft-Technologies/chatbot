from typing import List, Optional
from app.core.config import settings


def create_event(
    calendar_id: str,
    summary: str,
    start_iso: str,
    end_iso: str,
    attendees: Optional[List[str]] = None,
    timezone: Optional[str] = None,
) -> Optional[str]:
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except Exception:
        return None

    sa_json = settings.GOOGLE_SERVICE_ACCOUNT_JSON
    if not sa_json:
        return None

    try:
        import json
        info = json.loads(sa_json)
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/calendar"])
        svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
        ev = {
            "summary": summary,
            "start": {"dateTime": start_iso, **({"timeZone": timezone} if timezone else {})},
            "end": {"dateTime": end_iso, **({"timeZone": timezone} if timezone else {})},
        }
        if attendees:
            ev["attendees"] = [{"email": a} for a in attendees]
        created = svc.events().insert(calendarId=calendar_id, body=ev).execute()
        return created.get("id")
    except Exception:
        return None

