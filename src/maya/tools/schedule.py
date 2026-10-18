"""Calendar, task, planning, and reminder tools exposed to Maya's LangGraph agent."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from langchain_core.tools import tool

from maya.integrations.google_calendar import (
    TIMEZONE, create_calendar_event, delete_calendar_event, get_today_events,
    get_upcoming_birthdays, get_upcoming_events, search_calendar_events,
    update_calendar_event,
)
from maya.integrations.google_tasks import (
    complete_task, create_task, find_task_candidates, get_all_open_tasks,
    get_open_tasks, update_task,
)
from maya.core.reminders import (
    cancel_reminder as _cancel_reminder,
    create_reminder as _create_reminder,
    list_reminders as _list_reminders,
    snooze_reminder as _snooze_reminder,
)


def _fmt_time(value: str, all_day: bool = False) -> str:
    if not value:
        return "time unspecified"
    if all_day:
        try:
            return date.fromisoformat(value[:10]).strftime("%A, %d %B (all day)")
        except ValueError:
            return value
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TIMEZONE)
        return dt.astimezone(TIMEZONE).strftime("%a %d %b, %-I:%M %p")
    except ValueError:
        return value


@tool
def get_today_schedule() -> str:
    """Read today's Google Calendar events, Google Tasks deadlines, and birthdays.
    Use when the user asks what's on today or asks Maya to read today's schedule."""
    now = datetime.now(TIMEZONE)
    events = get_today_events()
    tasks = get_open_tasks(days=0, include_no_due_date=False)
    birthdays = get_upcoming_birthdays(days=1)
    lines = [f"Today's agenda — {now.strftime('%A, %d %B')}."]
    if events:
        lines.append("Calendar:")
        lines.extend(f"- {_fmt_time(e.get('start', ''), e.get('all_day', False))}: {e.get('title', 'Untitled event')}"
                     for e in events)
    else:
        lines.append("No calendar events found today.")
    if tasks:
        lines.append("Tasks due today:")
        lines.extend(f"- {t['title']}" for t in tasks)
    else:
        lines.append("No open Google Tasks with a due date today.")
    birthday_titles = [b.get("title", "Birthday") for b in birthdays
                       if (b.get("start") or "")[:10] == now.date().isoformat()]
    if birthday_titles:
        lines.append("Birthdays: " + ", ".join(birthday_titles))
    return "\n".join(lines)


@tool
def get_birthday_reminders(days: int = 30) -> str:
    """Find upcoming birthdays. Use for questions about whose birthday is coming up."""
    birthdays = get_upcoming_birthdays(days)
    if not birthdays:
        return f"No birthday events were found in the next {days} days."
    today = datetime.now(TIMEZONE).date()
    lines = [f"Birthdays in the next {days} days:"]
    for event in birthdays:
        raw = (event.get("start") or "")[:10]
        try:
            birthday = date.fromisoformat(raw)
            if birthday == today:
                relative = "today"
            elif birthday == today + timedelta(days=1):
                relative = "tomorrow"
            else:
                relative = birthday.strftime("%d %b")
        except ValueError:
            relative = raw or "date unknown"
        lines.append(f"- {event.get('title', 'Birthday')}: {relative}")
    return "\n".join(lines)


@tool
def get_upcoming_schedule(days: int = 7) -> str:
    """Read upcoming calendar events and task deadlines. days must be 1-90."""
    if not 1 <= days <= 90:
        return "Choose a range from 1 to 90 days."
    events = get_upcoming_events(days)
    tasks = get_open_tasks(days=days, include_no_due_date=False)
    lines = [f"Agenda for the next {days} days:"]
    if events:
        lines.append("Calendar events:")
        lines.extend(f"- {_fmt_time(e.get('start', ''), e.get('all_day', False))}: {e.get('title', 'Untitled event')} "
                     f"[{e.get('calendar', 'Calendar')}]"
                     for e in events)
    if tasks:
        lines.append("Task deadlines:")
        lines.extend(f"- {t['title']} — due {t['due']}" for t in tasks)
    if not events and not tasks:
        lines.append("No events or dated open tasks were found in that range.")
    return "\n".join(lines)


@tool
def find_calendar_events(query: str, days: int = 90) -> str:
    """Find calendar events by keywords before changing or cancelling an existing event."""
    matches = search_calendar_events(query, days)
    if not matches:
        return f"No upcoming calendar events matched {query!r}."
    return "\n".join(
        f"- ID={e['id']} | {e['title']} | {_fmt_time(e.get('start', ''), e.get('all_day', False))} "
        f"| calendar={e.get('calendar')}"
        for e in matches[:10]
    )


@tool
def create_event(title: str, start: str, end: str, description: str = "", location: str = "") -> str:
    """Create a Google Calendar event. start/end must be ISO-8601 datetime strings with timezone when possible."""
    event = create_calendar_event(title, start, end, description, location)
    return f"Created '{event['title']}' from {event['start']} to {event['end']} (event ID {event['id']})."


@tool
def update_event(event_id: str, title: str = "", start: str = "", end: str = "",
                 description: str = "", location: str = "") -> str:
    """Update an existing event by exact ID. First use find_calendar_events; if multiple matches, ask the user."""
    event = update_calendar_event(event_id, title, start, end, description, location)
    return f"Updated '{event['title']}' to start {event['start']} and end {event['end']}."


@tool
def cancel_event(event_id: str) -> str:
    """Cancel/delete an existing event by exact ID. Find and confirm the intended event first."""
    result = delete_calendar_event(event_id)
    return f"Cancelled '{result['title']}'."


@tool
def add_task(title: str, due: str = "", notes: str = "") -> str:
    """Create a Google Task. due is YYYY-MM-DD; omit it if no deadline was specified."""
    task = create_task(title, due, notes)
    return f"Created task '{task['title']}'" + (f", due {task['due']}." if task.get("due") else " with no due date.")


@tool
def find_open_tasks(query: str = "") -> str:
    """Find incomplete tasks. Use this to resolve references like 'that assignment' before completion."""
    tasks = find_task_candidates(query) if query.strip() else get_all_open_tasks()[:20]
    if not tasks:
        return "No matching open tasks found."
    return "\n".join(
        f"- ID={t['id']} | LIST_ID={t['task_list_id']} | {t['title']} | due={t['due'] or 'none'} | notes={t['notes'][:160]}"
        for t in tasks[:10]
    )


@tool
def mark_task_complete(task_list_id: str, task_id: str) -> str:
    """Mark a task complete using exact IDs from find_open_tasks. If the user's reference is ambiguous, ask first."""
    task = complete_task(task_list_id, task_id)
    return f"Marked '{task['title']}' complete."


@tool
def change_task_deadline(task_list_id: str, task_id: str, due: str = "KEEP",
                         title: str = "", notes: str = "") -> str:
    """Change an existing task's due date. due=YYYY-MM-DD sets it; due='' clears it; due='KEEP' leaves it unchanged."""
    task = update_task(task_list_id, task_id, title=title, due=due, notes=notes)
    return f"Updated task '{task['title']}', due {task['due'] or 'no deadline'}."


@tool
def create_spoken_reminder(message: str, scheduled_at: str, recurrence: str = "once") -> str:
    """Schedule a spoken reminder. scheduled_at is ISO-8601 with timezone; recurrence is once, daily, or weekly."""
    reminder = _create_reminder(message, scheduled_at, recurrence)
    return f"Reminder #{reminder['id']} saved for {reminder['scheduled_at']} ({recurrence})."


@tool
def list_spoken_reminders() -> str:
    """List upcoming pending spoken reminders."""
    reminders = _list_reminders()
    if not reminders:
        return "You have no pending spoken reminders."
    return "\n".join(f"- Reminder #{r['id']}: {r['message']} at {r['scheduled_at']} ({r['recurrence']})"
                     for r in reminders[:30])


@tool
def cancel_spoken_reminder(reminder_id: int) -> str:
    """Cancel a previously created spoken reminder by reminder ID."""
    result = _cancel_reminder(reminder_id)
    return f"Cancelled reminder #{reminder_id}." if result.get("cancelled") else f"Couldn't find reminder #{reminder_id}."


@tool
def snooze_spoken_reminder(reminder_id: int, minutes: int = 10) -> str:
    """Snooze a spoken reminder for 1-10080 minutes."""
    result = _snooze_reminder(reminder_id, minutes)
    return f"Snoozed reminder #{reminder_id} until {result['scheduled_at']}." if result.get("snoozed") else f"Couldn't snooze reminder #{reminder_id}."


@tool
def plan_next_action(available_minutes: int = 60) -> str:
    """Suggest what to do now using next calendar commitment and open task deadlines."""
    if not 5 <= available_minutes <= 720:
        return "Choose an available time between 5 and 720 minutes."
    now = datetime.now(TIMEZONE)
    events = get_upcoming_events(7)
    future = []
    for event in events:
        if event.get("all_day") or event.get("event_type") == "birthday":
            continue
        try:
            start = datetime.fromisoformat(event["start"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=TIMEZONE)
            start = start.astimezone(TIMEZONE)
            if start >= now:
                future.append((start, event))
        except (ValueError, TypeError, KeyError):
            continue
    future.sort(key=lambda pair: pair[0])
    tasks = get_open_tasks(days=30, include_no_due_date=True)
    lines = [f"It's {now.strftime('%A %d %B, %-I:%M %p')}; you have a requested work window of {available_minutes} minutes."]
    if future:
        start, event = future[0]
        mins = int((start - now).total_seconds() // 60)
        lines.append(f"Next calendar commitment: {event['title']} at {start.strftime('%-I:%M %p')} (in about {mins} minutes).")
        if mins <= available_minutes:
            lines.append("That commitment falls within the requested window; suggest a shorter task and leave a buffer.")
    else:
        mins = None
        lines.append("No upcoming timed commitment was found in the next seven days.")
    if tasks:
        today = now.date().isoformat()
        overdue = [t for t in tasks if t.get("due") and t["due"] < today]
        due_today = [t for t in tasks if t.get("due") == today]
        due_soon = [t for t in tasks if t.get("due") and today < t["due"]]
        if overdue:
            lines.append("Overdue tasks: " + "; ".join(t["title"] for t in overdue[:3]))
        if due_today:
            lines.append("Due today: " + "; ".join(t["title"] for t in due_today[:3]))
        if due_soon:
            lines.append("Upcoming deadlines: " + "; ".join(f"{t['title']} ({t['due']})" for t in due_soon[:3]))
        undated = [t for t in tasks if not t.get("due")]
        if undated:
            lines.append("Other open tasks include: " + "; ".join(t["title"] for t in undated[:3]))
        lines.append("Recommend one specific task that fits the remaining time; do not claim it is completed.")
    else:
        lines.append("No open tasks were found.")
    return "\n".join(lines)


ALL_SCHEDULING_TOOLS = [
    get_today_schedule, get_upcoming_schedule, get_birthday_reminders, find_calendar_events,
    create_event, update_event, cancel_event, add_task, find_open_tasks,
    mark_task_complete, change_task_deadline, create_spoken_reminder,
    list_spoken_reminders, cancel_spoken_reminder, snooze_spoken_reminder,
    plan_next_action,
]
