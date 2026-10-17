from maya.integrations.google_calendar import get_upcoming_events

for event in get_upcoming_events(days=1):
    print(event["start"], "-", event["title"])
