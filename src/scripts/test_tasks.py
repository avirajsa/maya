
from maya.integrations.google_tasks import (
    get_all_open_tasks,
    get_open_tasks,
    list_task_lists,
)

print("\n=== GOOGLE TASK LISTS ===")
for task_list in list_task_lists():
    print(f"- {task_list.get('title')} | ID: {task_list.get('id')}")

print("\n=== TASKS DUE IN THE NEXT 7 DAYS ===")
for task in get_open_tasks(days=7):
    due = task["due"] or "No due date"
    print(f"- {task['title']} | Due: {due} | List: {task['task_list']}")

print("\n=== ALL INCOMPLETE TASKS ===")
for task in get_all_open_tasks():
    due = task["due"] or "No due date"
    print(f"- {task['title']} | Due: {due} | List: {task['task_list']}")

