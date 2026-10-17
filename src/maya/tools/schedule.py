
"""Scheduling tools available to Maya's LangGraph agent."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from maya.integrations.google_calendar import (
    TIMEZONE,
    get_today_events,
    get_upcoming_birthdays,
    get_upcoming_events,
)


def _format_event(event: dict) -> str:
    start = event.get("start", "")
    title = event.get("title", "Untitled event")
    calendar = event.get("calendar", "Calendar")

    if event.get("all_day"):
        when = f"all day ({start})"
    else:
        try:
            parsed = datetime.fromisoformat(start)
            when = parsed.astimezone(TIMEZONE).strftime(
                "%I:%M %p"
            ).lstrip("0")
        except (ValueError, TypeError):
            when = start or "time not specified"

    return f"- {when}: {title} [{calendar}]"


@tool
def get_today_schedule() -> str:
    """Get today's calendar events, scheduled tasks and birthdays.
    Use when the user asks what's on today, their schedule, or today's plan.
    """
    events = get_today_events()

    if not events:
        return "No events were found for today in the calendars Maya checked."

    now = datetime.now(TIMEZONE)
    lines = [
        f"Today's schedule ({now.strftime('%A, %d %B')}):"
    ]

    for event in events:
        lines.append(_format_event(event))

    return "\n".join(lines)


@tool
def get_upcoming_schedule(days: int = 7) -> str:
    """Get events, scheduled tasks and birthdays over the next 1-90 days."""
    events = get_upcoming_events(days)

    if not events:
        return f"No events found in the next {days} days."

    lines = [f"Upcoming schedule ({days} days):"]
    for event in events:
        lines.append(
            f"- {event.get('start', '')}: "
            f"{event.get('title', 'Untitled')} "
            f"[{event.get('calendar', 'Calendar')}]"
        )

    return "\n".join(lines)


@tool
def get_birthday_reminders(days: int = 30) -> str:
    """Find upcoming birthdays. Use for questions about whose birthday
    is coming up, today's birthdays, or birthday reminders.
    """
    birthdays = get_upcoming_birthdays(days)

    if not birthdays:
        return (
            f"No birthday events were found in the next {days} days. "
            "This does not prove that no birthdays exist if the birthday "
            "calendar was inaccessible."
        )

    today = datetime.now(TIMEZONE).date()
    lines = [f"Birthdays in the next {days} days:"]

    for event in birthdays:
        start = event.get("start", "")
        try:
            birthday_date = date.fromisoformat(start[:10])
            if birthday_date == today:
                relative = "today"
            elif birthday_date == today + timedelta(days=1):
                relative = "tomorrow"
            else:
                relative = birthday_date.strftime("%d %b")
        except (ValueError, TypeError):
            relative = start

        lines.append(
            f"- {event.get('title', 'Birthday')}: {relative}"
        )

    return "\n".join(lines)


@tool
def plan_next_action(available_minutes: int = 60) -> str:
    """Help the user decide what to do now based on their schedule.
    Use when asked what to do next, what to do now, or what fits in a
    free time window. Does not claim tasks are unfinished.
    """
    if not 5 <= available_minutes <= 720:
        return "Choose an available time between 5 and 720 minutes."

    now = datetime.now(TIMEZONE)
    events = get_upcoming_events(7)

    upcoming = []
    tasks = []

    for event in events:
        start_text = event.get("start", "")
        if event.get("all_day"):
            continue

        try:
            start = datetime.fromisoformat(start_text)
            if start.tzinfo is None:
                start = start.replace(tzinfo=TIMEZONE)
            start = start.astimezone(TIMEZONE)
        except (ValueError, TypeError):
            continue

        if start < now:
            continue

        if event.get("calendar", "").strip().casefold() == "tasks":
            tasks.append((start, event))
        elif event.get("event_type") != "birthday":
            upcoming.append((start, event))

    next_commitment = upcoming[0] if upcoming else None
    next_task = tasks[0] if tasks else None

    lines = [
        f"Current time: {now.strftime('%A, %d %B, %I:%M %p')}.",
        f"Requested work window: {available_minutes} minutes.",
    ]

    if next_commitment:
        minutes_until = int(
            (next_commitment[0] - now).total_seconds() // 60
        )
        lines.append(
            f"Next timed commitment: {next_commitment[1]['title']} "
            f"at {next_commitment[0].strftime('%I:%M %p')} "
            f"(in about {minutes_until} minutes)."
        )
    else:
        minutes_until = None
        lines.append("No upcoming timed commitment was found in the next 7 days.")

    if next_task:
        lines.append(
            f"Next scheduled item on Tasks: {next_task[1]['title']} "
            f"at {next_task[0].strftime('%I:%M %p')}."
        )
    else:
        lines.append(
            "No future timed items were found on the Tasks calendar."
        )

    if minutes_until is not None and minutes_until <= available_minutes:
        lines.append(
            "The requested work window overlaps the next commitment. "
            "Recommend only a shorter activity if appropriate."
        )
    else:
        lines.append(
            "Use the available time for a focused task that fits the "
            "window. Do not assume a calendar item is incomplete."
        )

    return "\n".join(lines)

