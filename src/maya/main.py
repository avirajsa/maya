"""Maya entry point — starts the CLI, event bus, and persistent reminder worker."""

import asyncio
import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from maya.agent.agent import get_agent
from maya.core.config import get_config, setup_logging
from maya.core.events import MayaEvents, get_event_bus
from maya.core.reminders import run_reminder_worker

logger = logging.getLogger(__name__)
console = Console()

BANNER = r"""
   __  __
  |  \/  |
  | \  / | __ _ _   _  __ _
  | |\/| |/ _` | | | |/ _` |
  | |  | | (_| | |_| | (_| |
  |_|  |_|\__,_|\__,_|\__,_|
                 __/ |
                |___/
"""


async def _deliver_due_reminder(reminder: dict) -> None:
    """Publish a due reminder to Maya's event bus.

    The event is the stable seam for the UI/voice adapter to speak the reminder.
    The CLI also prints it so reminders are observable when running in terminal.
    """
    message = f"Reminder: {reminder['message']}"
    console.print(f"\n[bold yellow]Maya reminder:[/bold yellow] {message}\n")
    await get_event_bus().publish(
        MayaEvents.REMINDER_DUE,
        {
            "id": reminder["id"],
            "message": message,
            "scheduled_at": reminder["scheduled_at"],
            "recurrence": reminder["recurrence"],
        },
    )


async def cli_loop() -> None:
    """Run interactive async CLI chat session."""
    config = get_config()
    agent = get_agent()
    session_id = "cli_session"
    console.print(f"[bold green]Ready.[/bold green] Type your message or [bold cyan]'quit'[/bold cyan] to exit.\n")
    loop = asyncio.get_running_loop()

    while True:
        try:
            user_input = await loop.run_in_executor(None, input, "You: ")
            cleaned = user_input.strip()
            if not cleaned:
                continue
            if cleaned.lower() in ("quit", "exit", "bye", "q"):
                console.print(f"\n[bold magenta]{config.maya_name}:[/bold magenta] Goodbye! Have a wonderful day.\n")
                break
            console.print(f"[bold magenta]{config.maya_name}:[/bold magenta] ", end="")
            async for token in agent.stream_chat(cleaned, session_id=session_id):
                console.print(token, end="")
            console.print("\n")
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n\n[bold magenta]{config.maya_name}:[/bold magenta] Goodbye!\n")
            break
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}\n")


async def _run_application() -> None:
    """Run the event bus and persistent reminder scheduler alongside the CLI."""
    event_bus = get_event_bus()
    event_bus_task = asyncio.create_task(event_bus.run(), name="maya-event-bus")
    reminder_task = asyncio.create_task(
        run_reminder_worker(_deliver_due_reminder), name="maya-reminder-worker"
    )
    try:
        await cli_loop()
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass
        event_bus.stop()
        try:
            await event_bus_task
        except asyncio.CancelledError:
            pass


def print_startup_banner() -> None:
    """Display stylized ASCII banner with version and model diagnostics."""
    config = get_config()
    banner_text = Text(BANNER, style="bold magenta")
    details = (
        f"\n[bold cyan]• Assistant Name :[/bold cyan] {config.maya_name}\n"
        f"[bold cyan]• Primary LLM    :[/bold cyan] {config.llm_primary}\n"
        f"[bold cyan]• Fallback 1     :[/bold cyan] {config.llm_fallback_1}\n"
        f"[bold cyan]• Fallback 2     :[/bold cyan] {config.llm_fallback_2}\n"
        f"[bold cyan]• Voice (TTS)    :[/bold cyan] {config.tts_voice} ({config.tts_provider})\n"
        f"[bold cyan]• Whisper STT    :[/bold cyan] {config.whisper_model} ({config.whisper_device})\n"
    )
    console.print(Panel(Text.assemble(banner_text, Text.from_markup(details)), title="Maya AI Assistant", border_style="magenta"))


def main() -> None:
    """Application entrypoint."""
    setup_logging()
    print_startup_banner()
    try:
        asyncio.run(_run_application())
    except KeyboardInterrupt:
        console.print("\nExiting Maya. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
