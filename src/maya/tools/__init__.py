"""Maya tool registry — all tools available to the agent."""

from maya.tools.calculator import calculate
from maya.tools.fan import turn_off_ac, turn_off_fan, turn_on_ac, turn_on_fan
from maya.tools.lights import set_light_brightness, turn_off_lights, turn_on_lights
from maya.tools.summarise import summarise_text
from maya.tools.system import get_current_datetime, get_system_info, set_reminder
from maya.tools.schedule import (
    ALL_SCHEDULING_TOOLS,
    get_today_schedule,
    get_upcoming_schedule,
    get_birthday_reminders,
    plan_next_action,
)

from maya.tools.web_research import (
    web_search,
    scrape_webpage,
    research_web,
)

# Keep the existing tools and order, then append the scheduling tools not already
# registered. This avoids duplicate names while preserving the current registry.
ALL_TOOLS: list = [
    calculate,
    summarise_text,
    get_current_datetime,
    get_system_info,
    set_reminder,
    turn_on_lights,
    turn_off_lights,
    set_light_brightness,
    turn_on_fan,
    turn_off_fan,
    turn_on_ac,
    turn_off_ac,
    web_search,
    scrape_webpage,
    research_web,
]

_existing_names = {tool.name for tool in ALL_TOOLS}
ALL_TOOLS.extend(tool for tool in ALL_SCHEDULING_TOOLS if tool.name not in _existing_names)
TOOL_NAMES: list[str] = [tool.name for tool in ALL_TOOLS]

__all__ = [
    "ALL_TOOLS", "TOOL_NAMES", "ALL_SCHEDULING_TOOLS",
    "calculate", "search_web", "get_webpage_content", "summarise_text",
    "get_current_datetime", "get_system_info", "set_reminder",
    "turn_on_lights", "turn_off_lights", "set_light_brightness",
    "turn_on_fan", "turn_off_fan", "turn_on_ac", "turn_off_ac",
    "get_today_schedule", "get_upcoming_schedule", "get_birthday_reminders",
    "find_calendar_events", "create_event", "update_event", "cancel_event",
    "add_task", "find_open_tasks", "mark_task_complete", "change_task_deadline",
    "create_spoken_reminder", "list_spoken_reminders", "cancel_spoken_reminder",
    "snooze_spoken_reminder", "plan_next_action",
]

# Export scheduling tool objects for callers that import directly from maya.tools.
from maya.tools.schedule import (  # noqa: E402
    add_task, cancel_event, cancel_spoken_reminder, change_task_deadline,
    create_event, create_spoken_reminder, find_calendar_events, find_open_tasks,
    list_spoken_reminders, mark_task_complete, snooze_spoken_reminder, update_event,
)
