"""Async event bus for internal decoupled communication in Maya."""

import asyncio
from collections import defaultdict
import inspect
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class MayaEvents:
    """Well-known event name constants across Maya."""

    # Voice pipeline events
    WAKE_WORD_DETECTED = "wake_word_detected"
    RECORDING_STARTED = "recording_started"
    RECORDING_STOPPED = "recording_stopped"
    STT_RESULT = "stt_result"
    TTS_STARTED = "tts_started"
    TTS_FINISHED = "tts_finished"
    REMINDER_DUE = "reminder_due"

    # Agent conversation events
    USER_MESSAGE = "user_message"
    AGENT_RESPONSE = "agent_response"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"

    # Lifecycle events
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    ERROR = "error"

    # Integration events
    HA_COMMAND = "ha_command"
    HA_STATE_CHANGED = "ha_state_changed"


class EventBus:
    """Asynchronous Queue-based Publish/Subscribe Event Bus."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[tuple[str | None, Any]] = asyncio.Queue(maxsize=maxsize)
        self._subscribers: dict[str, list[Callable[..., Any]]] = defaultdict(list)
        self._running = False

    def subscribe(self, event: str, handler: Callable[..., Any]) -> None:
        """Subscribe a sync or async handler to an event."""
        if handler not in self._subscribers[event]:
            self._subscribers[event].append(handler)
            logger.debug("Subscribed %s to event '%s'", getattr(handler, "__name__", handler), event)

    def unsubscribe(self, event: str, handler: Callable[..., Any]) -> None:
        """Unsubscribe a handler from an event."""
        if event in self._subscribers and handler in self._subscribers[event]:
            self._subscribers[event].remove(handler)
            logger.debug("Unsubscribed %s from event '%s'", getattr(handler, "__name__", handler), event)

    async def publish(self, event: str, data: Any = None) -> None:
        """Publish an event asynchronously."""
        await self._queue.put((event, data))

    def publish_sync(self, event: str, data: Any = None) -> None:
        """Publish without blocking; intended for use from sync callbacks."""
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self._queue.put_nowait, (event, data))
        except RuntimeError:
            self._queue.put_nowait((event, data))
        except asyncio.QueueFull:
            logger.error("EventBus queue full; dropped event '%s'", event)

    async def run(self) -> None:
        """Dispatch queued events to subscribers."""
        self._running = True
        logger.info("EventBus started")
        while self._running:
            try:
                event, data = await self._queue.get()
                if event is None and data is None:
                    self._queue.task_done()
                    break
                handlers = list(self._subscribers.get(event, []))
                handlers.extend(self._subscribers.get("*", []))
                for handler in handlers:
                    try:
                        if inspect.iscoroutinefunction(handler):
                            await handler(data)
                        else:
                            result = handler(data)
                            if inspect.isawaitable(result):
                                await result
                    except Exception:
                        logger.exception("Event handler %r failed for event %r", handler, event)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in EventBus dispatch loop")
        self._running = False
        logger.info("EventBus stopped")

    def stop(self) -> None:
        """Signal the event bus loop to stop."""
        self._running = False
        try:
            self._queue.put_nowait((None, None))
        except Exception:
            pass


_default_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the global singleton EventBus instance."""
    global _default_event_bus
    if _default_event_bus is None:
        _default_event_bus = EventBus()
    return _default_event_bus
