
"""Google Tasks integration for Maya — read-only task access."""

import logging
import os
from datetime import date, datetime, timedelta
from functools import lru_cache
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

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]

TIMEZONE = ZoneInfo(os.getenv("MAYA_TIMEZONE", "Asia/Kolkata"))


@lru_cache(maxsize=1)
def get_tasks_service():
    """Authenticate and return the Google Tasks API service."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), SCOPES
        )

    if creds and not creds.has_scopes(SCOPES):
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials not found: "
                    f"{CREDENTIALS_FILE}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json())
        TOKEN_FILE.chmod(0o600)

    return build("tasks", "v1", credentials=creds, cache_discovery=False)


def list_task_lists() -> list[dict]:
    """Return all Google Tasks lists visible to the user."""
    service = get_tasks_service()
    results = []
    page_token = None

    while True:
        response = service.tasklists().list(
            maxResults=100,
            pageToken=page_token,
        ).execute()

        results.extend(response.get("items", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return results


def get_open_tasks(
    days: int = 7,
    include_no_due_date: bool = True,
) -> list[dict]:
    """Return incomplete tasks due within the next N days.

    Tasks without due dates are included by default.
    Completed and deleted tasks are excluded.
    """
    if days < 0:
        raise ValueError("days must be zero or greater")

    service = get_tasks_service()
    task_lists = list_task_lists()

    now = datetime.now(TIMEZONE)
    today = now.date()
    deadline = today + timedelta(days=days)

    results = []

    for task_list in task_lists:
        list_id = task_list["id"]
        list_title = task_list.get("title", "Untitled list")
        page_token = None

        while True:
            response = service.tasks().list(
                tasklist=list_id,
                maxResults=100,
                pageToken=page_token,
                showCompleted=False,
                showDeleted=False,
                showHidden=False,
            ).execute()

            for task in response.get("items", []):
                if task.get("status") == "completed":
                    continue

                due_raw = task.get("due")
                due_date = None

                if due_raw:
                    due_date = date.fromisoformat(due_raw[:10])

                    if not today <= due_date <= deadline:
                        continue
                elif not include_no_due_date:
                    continue

                results.append(
                    {
                        "id": task.get("id"),
                        "title": task.get("title", "Untitled task"),
                        "notes": task.get("notes", ""),
                        "due": due_date.isoformat() if due_date else None,
                        "task_list": list_title,
                        "task_list_id": list_id,
                        "status": task.get("status", "needsAction"),
                        "updated": task.get("updated"),
                        "link": task.get("webViewLink"),
                    }
                )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    results.sort(
        key=lambda task: (
            task["due"] is None,
            task["due"] or "9999-12-31",
            task["title"].casefold(),
        )
    )

    return results


def get_all_open_tasks() -> list[dict]:
    """Return all incomplete tasks, including tasks without due dates."""
    service = get_tasks_service()
    results = []

    for task_list in list_task_lists():
        page_token = None

        while True:
            response = service.tasks().list(
                tasklist=task_list["id"],
                maxResults=100,
                pageToken=page_token,
                showCompleted=False,
                showDeleted=False,
                showHidden=False,
            ).execute()

            for task in response.get("items", []):
                if task.get("status") == "completed":
                    continue

                due_raw = task.get("due")

                results.append(
                    {
                        "id": task.get("id"),
                        "title": task.get("title", "Untitled task"),
                        "notes": task.get("notes", ""),
                        "due": due_raw[:10] if due_raw else None,
                        "task_list": task_list.get(
                            "title", "Untitled list"
                        ),
                        "task_list_id": task_list["id"],
                        "status": task.get("status", "needsAction"),
                        "updated": task.get("updated"),
                        "link": task.get("webViewLink"),
                    }
                )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    results.sort(
        key=lambda task: (
            task["due"] is None,
            task["due"] or "9999-12-31",
            task["title"].casefold(),
        )
    )

    return results

