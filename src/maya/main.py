"""Maya entry point — starts the voice pipeline and/or the CLI interface."""

import asyncio
import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from maya.agent.agent import get_agent
from maya.core.config import get_config, setup_logging

logger = logging.getLogger(__name__)
console = Console()

BANNER = r"""
   __  __                   
  |  \/  |                  
  | \  / | __ _ _   _  __ _ 
  | |\/| |/ _` | | | |/ _` |
  | |  | | (_| | |_| | (_| |
  |_|  |_|\__,_|\__, |\__,_|
                 __/ |      
                |___/       
"""


async def cli_loop() -> None:
    """Run interactive async CLI chat session."""
    config = get_config()
    agent = get_agent()
    session_id = "cli_session"

    console.print(f"[bold green]Ready.[/bold green] Type your message or [bold cyan]'quit'[/bold cyan] to exit.\n")

    loop = asyncio.get_running_loop()

    while True:
        try:
            # Read input asynchronously without blocking loop
            user_input = await loop.run_in_executor(None, input, "You: ")
            cleaned = user_input.strip()

            if not cleaned:
                continue

            if cleaned.lower() in ("quit", "exit", "bye", "q"):
                console.print(f"\n[bold magenta]{config.maya_name}:[/bold magenta] Goodbye! Have a wonderful day.\n")
                break

            console.print(f"[bold magenta]{config.maya_name}:[/bold magenta] ", end="")
            full_response = ""
            async for token in agent.stream_chat(cleaned, session_id=session_id):
                console.print(token, end="")
                full_response += token
            console.print("\n")

        except (KeyboardInterrupt, EOFError):
            console.print(f"\n\n[bold magenta]{config.maya_name}:[/bold magenta] Goodbye!\n")
            break
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}\n")


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
        asyncio.run(cli_loop())
    except KeyboardInterrupt:
        console.print("\nExiting Maya. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
