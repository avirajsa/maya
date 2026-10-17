
from maya.integrations.google_calendar import list_calendars

for calendar in list_calendars():
    print(
        f"Name: {calendar.get('name')!r}\n"
        f"ID: {calendar.get('id')}\n"
        f"Access: {calendar.get('access_role')}\n"
        f"Primary: {calendar.get('primary')}\n"
        f"{'-' * 50}"
    )

