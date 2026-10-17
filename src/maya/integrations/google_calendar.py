
"""Read-only Google Calendar integration for Maya."""

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

CREDENTIALS_FILE = Path(
    os.getenv(
        "GOOGLE_CALENDAR_CREDENTIALS",
        str(SECRETS_DIR / "google_calendar_credentials.json"),
    )
)
TOKEN_FILE = Path(
    os.getenv(
        "GOOGLE_CALENDAR_TOKEN",
        str(SECRETS_DIR / "google_calendar_token.json"),
    )
)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TIMEZONE = ZoneInfo(os.getenv("MAYA_TIMEZONE", "Asia/Kolkata"))


@lru_cache(maxsize=1)
def get_calendar_service():
    """Build and cache an authenticated Calendar API client."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), SCOPES
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                f"Google OAuth credentials not found: {CREDENTIALS_FILE}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE), SCOPES
        )
        creds = flow.run_local_server(port=0)

    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    TOKEN_FILE.chmod(0o600)

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_calendars() -> list[dict]:
    """Return the calendars visible to the authenticated user."""
    service = get_calendar_service()
    calendars = []
    page_token = None

    while True:
        response = service.calendarList().list(
            pageToken=page_token,
            maxResults=250,
        ).execute()

        calendars.extend(
            {
                "id": item["id"],
                "name": item.get("summary", "Untitled calendar"),
                "primary": item.get("primary", False),
                "access_role": item.get("accessRole"),
            }
            for item in response.get("items", [])
        )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return calendars


def _find_tasks_calendar(calendars: list[dict]) -> dict:
    """Find the Tasks calendar without assuming its API ID."""
    matches = [
        c for c in calendars
        if c["name"].strip().casefold() == "tasks"
    ]

    if not matches:
        raise RuntimeError(
            "Couldn't find a calendar named 'Tasks'. "
            "Run the calendar diagnostic and check its exact name."
        )

    if len(matches) > 1:
        raise RuntimeError(
            "Multiple calendars are named 'Tasks'. "
            "Set an explicit calendar ID to disambiguate them."
        )

    return matches[0]


def _parse_event(item: dict, calendar_name: str) -> dict:
    """Normalize Google events, including all-day events."""
    start = item.get("start", {})
    end = item.get("end", {})

    return {
        "id": item.get("id"),
        "title": item.get("summary", "Untitled event"),
        "start": start.get("dateTime", start.get("date")),
        "end": end.get("dateTime", end.get("date")),
        "all_day": "date" in start,
        "calendar": calendar_name,
        "event_type": item.get("eventType", "default"),
        "status": item.get("status", "confirmed"),
        "description": item.get("description", ""),
        "html_link": item.get("htmlLink", ""),
    }


def _list_events(
    calendar_id: str,
    calendar_name: str,
    start: datetime,
    end: datetime,
    *,
    birthday_only: bool = False,
) -> list[dict]:
    """Fetch all matching events in a time range."""
    service = get_calendar_service()
    events = []
    page_token = None

    while True:
        params = {
            "calendarId": calendar_id,
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": True,
            "orderBy": "startTime",
            "showDeleted": False,
            "maxResults": 250,
            "pageToken": page_token,
        }

        if birthday_only:
            params["eventTypes"] = ["birthday"]

        response = service.events().list(**params).execute()

        events.extend(
            _parse_event(item, calendar_name)
            for item in response.get("items", [])
            if item.get("status") != "cancelled"
        )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return events


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=TIMEZONE)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=TIMEZONE)
    return start, end


def _collect_schedule(start: datetime, end: datetime) -> list[dict]:
    calendars = list_calendars()
    tasks_calendar = _find_tasks_calendar(calendars)

    primary = next(
        (c for c in calendars if c["primary"]),
        {"id": "primary", "name": "Primary calendar"},
    )

    events = _list_events(
        primary["id"], primary["name"], start, end
    )

    if tasks_calendar["id"] != primary["id"]:
        events.extend(
            _list_events(
                tasks_calendar["id"], tasks_calendar["name"], start, end
            )
        )

    # Birthdays may be exposed as eventType="birthday" on the primary
    # calendar or another listed calendar, not necessarily as a separate
    # calendar with a predictable ID.
    seen = {(e["calendar"], e["id"]) for e in events}

    for calendar in calendars:
        try:
            birthday_events = _list_events(
                calendar["id"],
                calendar["name"],
                start,
                end,
                birthday_only=True,
            )
        except Exception:
            logger.exception(
                "Could not read birthday events from %s", calendar["name"]
            )
            continue

        for event in birthday_events:
            key = (event["calendar"], event["id"])
            if key not in seen:
                events.append(event)
                seen.add(key)

    return sorted(
        events,
        key=lambda e: (e["start"] or "", e["title"].casefold()),
    )


def get_today_events() -> list[dict]:
    """Get primary-calendar events, Tasks events and birthdays for today."""
    start, end = _day_bounds(datetime.now(TIMEZONE).date())
    return _collect_schedule(start, end)


def get_upcoming_events(days: int = 7) -> list[dict]:
    """Get the next N days of events, including today."""
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")

    today = datetime.now(TIMEZONE).date()
    start, _ = _day_bounds(today)
    end, _ = _day_bounds(today + timedelta(days=days))
    return _collect_schedule(start, end)


def get_upcoming_birthdays(days: int = 30) -> list[dict]:
    """Get birthday events in the next N days."""
    if not 1 <= days <= 365:
        raise ValueError("days must be between 1 and 365")

    calendars = list_calendars()
    today = datetime.now(TIMEZONE).date()
    start, _ = _day_bounds(today)
    end, _ = _day_bounds(today + timedelta(days=days))

    results = []
    seen = set()

    for calendar in calendars:
        try:
            events = _list_events(
                calendar["id"],
                calendar["name"],
                start,
                end,
                birthday_only=True,
            )
        except Exception:
            logger.exception(
                "Could not read birthdays from %s", calendar["name"]
            )
            continue

        for event in events:
            key = (calendar["id"], event["id"])
            if key not in seen:
                results.append(event)
                seen.add(key)

    return sorted(results, key=lambda e: e["start"] or "")

