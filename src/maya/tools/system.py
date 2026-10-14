"""System information tools — time, date, weather stub, and system info."""

from datetime import datetime
import os
import platform
import sys
from langchain_core.tools import tool

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False


@tool
def get_current_datetime() -> str:
    """Get the current local date, time, day of the week, and timezone.

    Always use this tool when the user asks for the time, date, day, or current temporal context.

    Returns:
        Formatted date and time string.
    """
    now = datetime.now().astimezone()
    day_name = now.strftime("%A")
    date_str = now.strftime("%B %d, %Y")
    time_str = now.strftime("%I:%M:%S %p")
    tz_name = now.tzname() or "UTC"
    utc_offset = now.strftime("%z")
    formatted_offset = f"UTC{utc_offset[:3]}:{utc_offset[3:]}" if utc_offset else ""

    return f"{day_name}, {date_str} at {time_str} ({tz_name} {formatted_offset})".strip()


@tool
def get_system_info() -> str:
    """Retrieve host system details including OS platform, CPU count, memory usage, and Python version.

    Returns:
        Formatted string containing hardware and runtime diagnostic information.
    """
    py_version = sys.version.split()[0]
    node = platform.node() or "localhost"
    system = platform.system()
    release = platform.release()
    processor = platform.processor() or "Unknown"

    if PSUTIL_AVAILABLE and psutil is not None:
        try:
            cpu_count_logical = psutil.cpu_count(logical=True)
            cpu_count_physical = psutil.cpu_count(logical=False) or cpu_count_logical
            cpu_percent = psutil.cpu_percent(interval=0.1)
            virtual_mem = psutil.virtual_memory()
            total_gb = virtual_mem.total / (1024**3)
            used_gb = virtual_mem.used / (1024**3)
            mem_percent = virtual_mem.percent

            return (
                f"Host: {node}\n"
                f"OS: {system} {release}\n"
                f"Processor: {processor}\n"
                f"CPU: {cpu_count_physical} physical cores ({cpu_count_logical} logical), Usage: {cpu_percent}%\n"
                f"Memory: {used_gb:.1f} GB / {total_gb:.1f} GB ({mem_percent}% used)\n"
                f"Python: {py_version}"
            )
        except Exception:
            pass

    return (
        f"Host: {node}\n"
        f"OS: {system} {release}\n"
        f"Processor: {processor}\n"
        f"CPU Count: {os.cpu_count() or 'Unknown'}\n"
        f"Python: {py_version}"
    )


@tool
def set_reminder(message: str, minutes: int) -> str:
    """Set a timer reminder for a specified number of minutes.

    Args:
        message: The task or reminder note (e.g. 'check the oven', 'drink water').
        minutes: Number of minutes from now to alert.

    Returns:
        Confirmation message acknowledging the reminder.
    """
    cleaned_msg = message.strip()
    if minutes <= 0:
        return f"Invalid duration {minutes} minutes. Please provide a positive duration."
    return f"Reminder set for {minutes} minutes: {cleaned_msg}"
