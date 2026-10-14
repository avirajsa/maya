"""Maya tool registry — all tools available to the agent."""

from maya.tools.calculator import calculate
from maya.tools.fan import turn_off_ac, turn_off_fan, turn_on_ac, turn_on_fan
from maya.tools.lights import (
    set_light_brightness,
    turn_off_lights,
    turn_on_lights,
)
from maya.tools.summarise import summarise_text
from maya.tools.system import (
    get_current_datetime,
    get_system_info,
    set_reminder,
)
from maya.tools.web_search import get_webpage_content, search_web

# Complete registry of all LangChain tools available to Maya
ALL_TOOLS: list = [
    calculate,
    search_web,
    get_webpage_content,
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
]

# List of tool names for quick inspection, filtering, and debugging
TOOL_NAMES: list[str] = [t.name for t in ALL_TOOLS]

__all__ = [
    "ALL_TOOLS",
    "TOOL_NAMES",
    "calculate",
    "search_web",
    "get_webpage_content",
    "summarise_text",
    "get_current_datetime",
    "get_system_info",
    "set_reminder",
    "turn_on_lights",
    "turn_off_lights",
    "set_light_brightness",
    "turn_on_fan",
    "turn_off_fan",
    "turn_on_ac",
    "turn_off_ac",
]
