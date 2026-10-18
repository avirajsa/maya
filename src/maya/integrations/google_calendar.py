"""Google Calendar integration for Maya (read/write events, read birthdays).

Google Tasks are NOT Google Calendar events; use maya.integrations.google_tasks.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SECRETS_DIR = PROJECT_ROOT / "secrets"
CREDENTIALS_FILE = Path(os.getenv("GOOGLE_CALENDAR_CREDENTIALS", str(SECRETS_DIR / "google_calendar_credentials.json")))
TOKEN_FILE = Path(os.getenv("GOOGLE_CALENDAR_TOKEN", str(SECRETS_DIR / "google_calendar_token.json")))

# Both integrations share this combined scope set and token file.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/tasks",
]
TIMEZONE = ZoneInfo(os.getenv("MAYA_TIMEZONE", "Asia/Kolkata"))


@lru_cache(maxsize=1)
def get_calendar_service():
    """Build a cached Calendar API client; reauthorize if token lacks required scopes."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if not creds.has_scopes(SCOPES):
            logger.warning("Cached Google token lacks Maya's required scopes; reauthorization required.")
            creds = None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(f"Google OAuth credentials not found: {CREDENTIALS_FILE}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_calendars() -> list[dict]:
    service = get_calendar_service()
    results, token = [], None
    while True:
        response = service.calendarList().list(maxResults=250, pageToken=token).execute()
        results.extend({
            "id": item["id"], "name": item.get("summary", "Untitled calendar"),
            "primary": item.get("primary", False), "access_role": item.get("accessRole")
        } for item in response.get("items", []))
        token = response.get("nextPageToken")
        if not token:
            return results


def _primary_calendar() -> dict:
    calendars = list_calendars()
    return next((c for c in calendars if c["primary"]), {"id": "primary", "name": "Primary calendar", "primary": True})


def _parse_event(item: dict, calendar_name: str) -> dict:
    start, end = item.get("start", {}), item.get("end", {})
    return {
        "id": item.get("id"), "title": item.get("summary", "Untitled event"),
        "start": start.get("dateTime", start.get("date")),
        "end": end.get("dateTime", end.get("date")),
        "all_day": "date" in start, "calendar": calendar_name,
        "event_type": item.get("eventType", "default"), "status": item.get("status", "confirmed"),
        "description": item.get("description", ""), "location": item.get("location", ""),
        "html_link": item.get("htmlLink", ""),
    }


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    return (datetime.combine(day, time.min, tzinfo=TIMEZONE),
            datetime.combine(day + timedelta(days=1), time.min, tzinfo=TIMEZONE))


def _list_events(calendar_id: str, calendar_name: str, start: datetime, end: datetime,
                 birthday_only: bool = False) -> list[dict]:
    service, results, token = get_calendar_service(), [], None
    while True:
        params = dict(calendarId=calendar_id, timeMin=start.isoformat(), timeMax=end.isoformat(),
                      singleEvents=True, orderBy="startTime", showDeleted=False,
                      maxResults=250, pageToken=token)
        if birthday_only:
            params["eventTypes"] = ["birthday"]
        response = service.events().list(**params).execute()
        results.extend(_parse_event(item, calendar_name) for item in response.get("items", [])
                       if item.get("status") != "cancelled")
        token = response.get("nextPageToken")
        if not token:
            return results


def get_today_events() -> list[dict]:
    today = datetime.now(TIMEZONE).date()
    start, end = _day_bounds(today)
    primary = _primary_calendar()
    return _list_events(primary["id"], primary["name"], start, end)


def get_upcoming_events(days: int = 7) -> list[dict]:
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    today = datetime.now(TIMEZONE).date()
    start, _ = _day_bounds(today)
    end, _ = _day_bounds(today + timedelta(days=days))
    calendars = list_calendars()
    events = []
    # Read visible calendars, not just the primary calendar. Google Tasks itself
    # is intentionally excluded here; it is read through the Tasks API.
    for cal in calendars:
        try:
            events.extend(_list_events(cal["id"], cal["name"], start, end))
        except Exception:
            logger.debug("Could not read events from calendar %s", cal["name"], exc_info=True)
    # Some Google birthday calendars expose birthday events through eventTypes.
    seen = {(e["calendar"], e["id"]) for e in events}
    for cal in calendars:
        try:
            for event in _list_events(cal["id"], cal["name"], start, end, birthday_only=True):
                key = (event["calendar"], event["id"])
                if key not in seen:
                    events.append(event)
                    seen.add(key)
        except Exception:
            logger.debug("Birthday query unavailable for calendar %s", cal["name"], exc_info=True)
    return sorted(events, key=lambda e: (e.get("start") or "", e.get("title", "").casefold()))


def get_upcoming_birthdays(days: int = 30) -> list[dict]:
    if not 1 <= days <= 365:
        raise ValueError("days must be between 1 and 365")
    today = datetime.now(TIMEZONE).date()
    start, _ = _day_bounds(today)
    end, _ = _day_bounds(today + timedelta(days=days))
    results = []
    for cal in list_calendars():
        try:
            results.extend(_list_events(cal["id"], cal["name"], start, end, birthday_only=True))
        except Exception:
            logger.debug("Birthday query unavailable for calendar %s", cal["name"], exc_info=True)
    unique = {(e["calendar"], e["id"]): e for e in results}
    return sorted(unique.values(), key=lambda e: (e.get("start") or "", e.get("title", "").casefold()))


def _event_body(title: str, start: str, end: str, description: str = "", location: str = "") -> dict:
    if not title.strip():
        raise ValueError("Event title cannot be empty")
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=TIMEZONE)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=TIMEZONE)
    if end_dt <= start_dt:
        raise ValueError("Event end must be after its start")
    return {
        "summary": title.strip(), "description": description or "", "location": location or "",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": str(TIMEZONE)},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": str(TIMEZONE)},
    }


def create_calendar_event(title: str, start: str, end: str, description: str = "", location: str = "") -> dict:
    """Create a timed event on the primary calendar. start/end must be ISO datetimes."""
    primary = _primary_calendar()
    item = get_calendar_service().events().insert(
        calendarId=primary["id"], body=_event_body(title, start, end, description, location)
    ).execute()
    return _parse_event(item, primary["name"])


def search_calendar_events(query: str, days: int = 90) -> list[dict]:
    """Search upcoming events by title/description/location text."""
    if not query.strip():
        raise ValueError("Search query cannot be empty")
    needle = query.casefold()
    events = get_upcoming_events(days)
    return [e for e in events if needle in " ".join([
        e.get("title", ""), e.get("description", ""), e.get("location", "")
    ]).casefold()]


def _find_event_on_visible_calendars(event_id: str) -> tuple[dict, dict]:
    """Find an event by ID across visible calendars, returning (calendar, event)."""
    from googleapiclient.errors import HttpError

    service = get_calendar_service()
    for calendar in list_calendars():
        try:
            event = service.events().get(calendarId=calendar["id"], eventId=event_id).execute()
            return calendar, event
        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status in (403, 404):
                continue
            raise
    raise ValueError(f"Could not find event ID {event_id!r} in calendars you can access")


def update_calendar_event(event_id: str, title: str = "", start: str = "", end: str = "",
                          description: str = "", location: str = "") -> dict:
    """Update fields supplied for an event on any visible calendar."""
    service = get_calendar_service()
    calendar, current = _find_event_on_visible_calendars(event_id)
    body = {}
    if title:
        body["summary"] = title
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    def _datetime_field(value: str) -> dict:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TIMEZONE)
        return {"dateTime": dt.isoformat(), "timeZone": str(TIMEZONE)}
    if start:
        body["start"] = _datetime_field(start)
    if end:
        body["end"] = _datetime_field(end)
    if start and end:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=TIMEZONE)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=TIMEZONE)
        if end_dt <= start_dt:
            raise ValueError("Event end must be after its start")
    if start and not end:
        # Preserve the existing duration when only the start is changed.
        old_start = current.get("start", {}).get("dateTime")
        old_end = current.get("end", {}).get("dateTime")
        if old_start and old_end:
            old_start_dt = datetime.fromisoformat(old_start.replace("Z", "+00:00"))
            old_end_dt = datetime.fromisoformat(old_end.replace("Z", "+00:00"))
            new_start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if old_start_dt.tzinfo is None:
                old_start_dt = old_start_dt.replace(tzinfo=TIMEZONE)
            if old_end_dt.tzinfo is None:
                old_end_dt = old_end_dt.replace(tzinfo=TIMEZONE)
            if new_start_dt.tzinfo is None:
                new_start_dt = new_start_dt.replace(tzinfo=TIMEZONE)
            new_end_dt = new_start_dt + (old_end_dt - old_start_dt)
            body["end"] = {"dateTime": new_end_dt.isoformat(), "timeZone": str(TIMEZONE)}
    updated = service.events().patch(calendarId=calendar["id"], eventId=event_id, body=body).execute()
    return _parse_event(updated, calendar["name"])


def delete_calendar_event(event_id: str) -> dict:
    """Delete an event by ID from whichever visible calendar contains it."""
    service = get_calendar_service()
    calendar, existing = _find_event_on_visible_calendars(event_id)
    service.events().delete(calendarId=calendar["id"], eventId=event_id).execute()
    return {"id": event_id, "title": existing.get("summary", "Untitled event"), "calendar": calendar["name"]}
