"""Google Tasks integration for Maya (read/write task management)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
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
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/tasks",
]
TIMEZONE = ZoneInfo(os.getenv("MAYA_TIMEZONE", "Asia/Kolkata"))


@lru_cache(maxsize=1)
def get_tasks_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if not creds.has_scopes(SCOPES):
            logger.warning("Cached Google token lacks required scopes; reauthorization required.")
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
    return build("tasks", "v1", credentials=creds, cache_discovery=False)


def list_task_lists() -> list[dict]:
    service, results, token = get_tasks_service(), [], None
    while True:
        response = service.tasklists().list(maxResults=100, pageToken=token).execute()
        results.extend(response.get("items", []))
        token = response.get("nextPageToken")
        if not token:
            return results


def _task_lists_by_id() -> dict[str, dict]:
    return {item["id"]: item for item in list_task_lists()}


def _normalise_task(task: dict, task_list: dict) -> dict:
    return {
        "id": task.get("id"), "title": task.get("title", "Untitled task"),
        "notes": task.get("notes", ""), "due": task.get("due", "")[:10] or None,
        "task_list": task_list.get("title", "Untitled list"), "task_list_id": task_list["id"],
        "status": task.get("status", "needsAction"), "updated": task.get("updated"),
        "link": task.get("webViewLink"),
    }


def get_all_open_tasks() -> list[dict]:
    service, results = get_tasks_service(), []
    for task_list in list_task_lists():
        token = None
        while True:
            response = service.tasks().list(tasklist=task_list["id"], maxResults=100, pageToken=token,
                                            showCompleted=False, showDeleted=False, showHidden=False).execute()
            results.extend(_normalise_task(task, task_list) for task in response.get("items", [])
                           if task.get("status") != "completed")
            token = response.get("nextPageToken")
            if not token:
                break
    return sorted(results, key=lambda t: (t["due"] is None, t["due"] or "9999-12-31", t["title"].casefold()))


def get_open_tasks(days: int = 7, include_no_due_date: bool = True) -> list[dict]:
    if not 0 <= days <= 3650:
        raise ValueError("days must be between 0 and 3650")
    today, deadline = datetime.now(TIMEZONE).date(), datetime.now(TIMEZONE).date() + timedelta(days=days)
    results = []
    for task in get_all_open_tasks():
        if task["due"]:
            due = date.fromisoformat(task["due"])
            if today <= due <= deadline:
                results.append(task)
        elif include_no_due_date:
            results.append(task)
    return results


def create_task(title: str, due: str = "", notes: str = "", task_list_id: str = "") -> dict:
    """Create a Google Task. due accepts YYYY-MM-DD; empty means no due date."""
    if not title.strip():
        raise ValueError("Task title cannot be empty")
    lists = list_task_lists()
    target = next((x for x in lists if x["id"] == task_list_id), None) if task_list_id else next(
        (x for x in lists if x.get("title", "").strip().casefold() == "tasks"), None
    )
    if not target and lists:
        target = lists[0]
    if not target:
        raise RuntimeError("No Google Task lists are available.")
    body = {"title": title.strip(), "notes": notes or ""}
    if due:
        due_date = date.fromisoformat(due[:10])
        # Google Tasks API accepts due as RFC3339 timestamp; date-only due is represented at midnight UTC.
        body["due"] = f"{due_date.isoformat()}T00:00:00.000Z"
    task = get_tasks_service().tasks().insert(tasklist=target["id"], body=body).execute()
    return _normalise_task(task, target)


def update_task(task_list_id: str, task_id: str, title: str = "", due: str = "KEEP", notes: str = "") -> dict:
    """Update a task by exact IDs. Empty due clears its deadline; use due='KEEP' to retain it."""
    lists = _task_lists_by_id()
    if task_list_id not in lists:
        raise ValueError("Unknown task list ID")
    service = get_tasks_service()
    current = service.tasks().get(tasklist=task_list_id, task=task_id).execute()
    body = {}
    if title.strip():
        body["title"] = title.strip()
    if notes:
        body["notes"] = notes
    if due != "KEEP":
        if due:
            due_date = date.fromisoformat(due[:10])
            body["due"] = f"{due_date.isoformat()}T00:00:00.000Z"
        else:
            body["due"] = None
    updated = service.tasks().patch(tasklist=task_list_id, task=task_id, body=body).execute()
    return _normalise_task(updated, lists[task_list_id])


def complete_task(task_list_id: str, task_id: str) -> dict:
    """Mark a specific task completed by exact task-list and task IDs."""
    lists = _task_lists_by_id()
    if task_list_id not in lists:
        raise ValueError("Unknown task list ID")
    service = get_tasks_service()
    task = service.tasks().get(tasklist=task_list_id, task=task_id).execute()
    if task.get("status") == "completed":
        return {**_normalise_task(task, lists[task_list_id]), "already_completed": True}
    task["status"] = "completed"
    task["completed"] = datetime.now(TIMEZONE).isoformat()
    updated = service.tasks().update(tasklist=task_list_id, task=task_id, body=task).execute()
    return _normalise_task(updated, lists[task_list_id])


def find_task_candidates(query: str, limit: int = 10) -> list[dict]:
    """Find open tasks whose titles/notes overlap the user's reference."""
    words = {w.casefold().strip(".,!?;:'\"()[]{}") for w in query.split()}
    words = {w for w in words if len(w) > 2}
    scored = []
    for task in get_all_open_tasks():
        title_words = {w.casefold().strip(".,!?;:'\"()[]{}") for w in task["title"].split()}
        note_words = {w.casefold().strip(".,!?;:'\"()[]{}") for w in task["notes"].split()}
        overlap = len(words & (title_words | note_words))
        if query.casefold().strip() in task["title"].casefold():
            overlap += 3
        if overlap:
            scored.append((overlap, task))
    scored.sort(key=lambda item: (-item[0], item[1]["due"] or "9999-12-31", item[1]["title"].casefold()))
    return [task for _, task in scored[:limit]]
