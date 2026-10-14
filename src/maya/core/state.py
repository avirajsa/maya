"""State management models for Maya AI Assistant."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any
import uuid

logger = logging.getLogger(__name__)


class MayaStatus(str, Enum):
    """Current operational state of Maya."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class SessionState:
    """State of an active interaction session."""

    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    turn_count: int = 0
    last_user_text: str = ""
    last_maya_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_turn(self, user_text: str, maya_text: str) -> None:
        """Record an interaction turn."""
        self.turn_count += 1
        self.last_user_text = user_text
        self.last_maya_text = maya_text


@dataclass
class MayaState:
    """Global runtime state of the Maya assistant."""

    status: MayaStatus = MayaStatus.IDLE
    current_session: SessionState | None = None
    startup_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    voice_active: bool = False

    def set_status(self, status: MayaStatus) -> None:
        """Update the assistant status."""
        logger.debug("State transition: %s -> %s", self.status.value, status.value)
        self.status = status

    def new_session(self, session_id: str | None = None) -> SessionState:
        """Create and set a new session."""
        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        session = SessionState(session_id=sid)
        self.current_session = session
        logger.info("Started new session: %s", sid)
        return session

    def end_session(self) -> None:
        """End the current session and revert status to IDLE."""
        if self.current_session:
            logger.info(
                "Ended session: %s (total turns: %d)",
                self.current_session.session_id,
                self.current_session.turn_count,
            )
        self.current_session = None
        self.set_status(MayaStatus.IDLE)


_global_state: MayaState | None = None


def get_state() -> MayaState:
    """Return the global singleton MayaState instance."""
    global _global_state
    if _global_state is None:
        _global_state = MayaState()
    return _global_state
