from typing import List, Optional
from app.config import settings


def create_event(
    calendar_id: str,
    summary: str,
    start_iso: str,
    end_iso: str,
    attendees: Optional[List[str]] = None,
    timezone: Optional[str] = None,
    description: Optional[str] = None,
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
        if description:
            ev["description"] = description
        if attendees:
            ev["attendees"] = [{"email": a} for a in attendees]
        created = svc.events().insert(calendarId=calendar_id, body=ev).execute()
        return created.get("id")
    except Exception:
        return None


def _fernet_key() -> Optional[bytes]:
    try:
        import base64, hashlib
        secret = getattr(settings, "JWT_SECRET", "dev-secret")
        h = hashlib.sha256(secret.encode()).digest()
        return base64.urlsafe_b64encode(h)
    except Exception:
        return None


def _encrypt(x: str) -> Optional[str]:
    try:
        from cryptography.fernet import Fernet
        k = _fernet_key()
        if not k:
            return None
        f = Fernet(k)
        return f.encrypt(x.encode()).decode()
    except Exception:
        return None


def _decrypt(x: str) -> Optional[str]:
    try:
        from cryptography.fernet import Fernet
        k = _fernet_key()
        if not k:
            return None
        f = Fernet(k)
        return f.decrypt(x.encode()).decode()
    except Exception:
        return None


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Refresh an expired access token using the refresh token"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except Exception:
        return None
    
    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        
        # Refresh the token
        creds.refresh(Request())
        
        # Return the new tokens
        return {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token, # Might be updated
            "expiry": creds.expiry
        }
    except Exception as e:
        print(f"Token refresh failed: {str(e)}")
        return None


def build_service_from_tokens(access_token: str, refresh_token: Optional[str], token_expiry: Optional[str]):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except Exception:
        return None
    scopes = ["https://www.googleapis.com/auth/calendar"]
    try:
        creds = Credentials(token=access_token, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token", client_id=settings.GOOGLE_CLIENT_ID, client_secret=settings.GOOGLE_CLIENT_SECRET, scopes=scopes)
        svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return svc
    except Exception:
        return None


def oauth_authorize_url(org_id: str, bot_id: str, redirect_uri: str) -> Optional[str]:
    try:
        from google_auth_oauthlib.flow import Flow
    except Exception:
        return None
    cid = settings.GOOGLE_CLIENT_ID
    cs = settings.GOOGLE_CLIENT_SECRET
    if not cid or not cs:
        return None
    try:
        conf = {
            "web": {
                "client_id": cid,
                "client_secret": cs,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = Flow.from_client_config(conf, scopes=["https://www.googleapis.com/auth/calendar"])
        flow.redirect_uri = redirect_uri
        import urllib.parse
        state = urllib.parse.urlencode({"org": org_id, "bot": bot_id})
        auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=state)
        return auth_url
    except Exception:
        return None


def exchange_code_for_tokens(code: str, redirect_uri: str):
    try:
        from google_auth_oauthlib.flow import Flow
    except Exception:
        return None
    cid = settings.GOOGLE_CLIENT_ID
    cs = settings.GOOGLE_CLIENT_SECRET
    if not cid or not cs:
        return None
    try:
        conf = {
            "web": {
                "client_id": cid,
                "client_secret": cs,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = Flow.from_client_config(conf, scopes=["https://www.googleapis.com/auth/calendar"])
        flow.redirect_uri = redirect_uri
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "access_token": getattr(creds, "token", None),
            "refresh_token": getattr(creds, "refresh_token", None),
            "expiry": getattr(creds, "expiry", None),
        }
    except Exception:
        return None


def list_events_oauth(svc, calendar_id: str, time_min_iso: str, time_max_iso: str):
    try:
        items = svc.events().list(calendarId=calendar_id, timeMin=time_min_iso, timeMax=time_max_iso, singleEvents=True, orderBy="startTime").execute().get("items", [])
        return items
    except Exception:
        return []


def create_event_oauth(svc, calendar_id: str, summary: str, start_iso: str, end_iso: str, attendees: Optional[List[str]] = None, timezone: Optional[str] = None, description: Optional[str] = None, event_id: Optional[str] = None) -> Optional[str]:
    try:
        print(f"🔧 create_event_oauth called with:")
        print(f"   - calendar_id: {calendar_id}")
        print(f"   - summary: {summary}")
        print(f"   - description length: {len(description) if description else 0} chars")
        if description:
            print(f"   - description preview: {description[:200]}...")
        
        ev = {
            "summary": summary,
            "start": {"dateTime": start_iso, **({"timeZone": timezone} if timezone else {})},
            "end": {"dateTime": end_iso, **({"timeZone": timezone} if timezone else {})},
        }
        if description:
            ev["description"] = description
            print(f"   ✓ Description added to event body")
        else:
            print(f"   ⚠ No description provided")
        if attendees:
            ev["attendees"] = [{"email": a} for a in attendees]
        if event_id:
            ev["id"] = event_id
            print(f"   ✓ Using provided event ID: {event_id}")
        
        last_error = None
        for attempt in range(3):
            try:
                # Add sendUpdates='all' to send email notifications to attendees
                created = svc.events().insert(calendarId=calendar_id, body=ev, sendUpdates='all').execute()
                return created.get("id")
            except Exception as e:
                # If the error is that the event already exists (409 Conflict), return the ID
                if "409" in str(e) and "already exists" in str(e).lower() and event_id:
                    print(f"   ✓ Event {event_id} already exists, returning ID")
                    return event_id
                    
                last_error = e
                print(f"   Attempt {attempt + 1}/3 failed: {str(e)}")
                continue
        
        if last_error:
            print(f"   All retry attempts failed. Last error: {str(last_error)}")
        return None
    except Exception as e:
        print(f"   Exception in create_event_oauth: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def update_event_oauth(svc, calendar_id: str, event_id: str, patch: dict) -> bool:
    try:
        for _ in range(3):
            try:
                svc.events().patch(calendarId=calendar_id, eventId=event_id, body=patch, sendUpdates='all').execute()
                return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def delete_event_oauth(svc, calendar_id: str, event_id: str) -> bool:
    try:
        for _ in range(3):
            try:
                svc.events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates='all').execute()
                return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def get_event_oauth(svc, calendar_id: str, event_id: str):
    """Retrieve a single event; returns None on error."""
    try:
        return svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
    except Exception:
        return None
