"""Maya router — routes messages between voice, chat, and tool-only interfaces."""

import logging
from typing import Any
import numpy as np

from maya.agent.agent import MayaAgent, get_agent
from maya.core.state import MayaStatus, get_state
from maya.voice.stt import get_stt
from maya.voice.tts import get_tts

logger = logging.getLogger(__name__)


class MayaRouter:
    """Routes incoming interaction requests across text, voice, and system command interfaces."""

    def __init__(self, agent: MayaAgent) -> None:
        self.agent = agent

    async def handle_text(self, text: str, session_id: str = "default") -> str:
        """Route text input to the agent and return response."""
        state = get_state()
        state.set_status(MayaStatus.THINKING)
        try:
            response = await self.agent.chat(
                user_input=text, session_id=session_id, voice_mode=False
            )
            return response
        finally:
            state.set_status(MayaStatus.IDLE)

    async def handle_voice(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        session_id: str = "default",
    ) -> tuple[str, bytes]:
        """Transcribe audio, query agent in voice mode, and synthesize spoken audio response.

        Args:
            audio: 1D numpy array of audio samples.
            sample_rate: Sampling rate in Hz.
            session_id: Session identifier.

        Returns:
            Tuple of (response_text, audio_bytes).
        """
        state = get_state()
        stt = get_stt()
        tts = get_tts()

        state.set_status(MayaStatus.THINKING)
        try:
            transcription = await stt.transcribe(audio=audio, sample_rate=sample_rate)
            if not transcription.strip():
                return ("(No speech detected)", b"")

            response_text = await self.agent.chat(
                user_input=transcription,
                session_id=session_id,
                voice_mode=True,
            )

            state.set_status(MayaStatus.SPEAKING)
            audio_bytes = await tts.synthesise(response_text)
            return (response_text, audio_bytes)
        except Exception as e:
            logger.error("Error handling voice request: %s", e, exc_info=True)
            err_msg = f"Sorry, I had trouble processing your voice request: {str(e)}"
            try:
                audio_bytes = await tts.synthesise(err_msg)
            except Exception:
                audio_bytes = b""
            return (err_msg, audio_bytes)
        finally:
            state.set_status(MayaStatus.IDLE)

    async def handle_command(self, command: str, session_id: str = "default") -> str:
        """Handle system or slash commands directly without LLM if applicable."""
        cmd = command.strip().lower()
        if cmd in ("clear", "/clear", "reset"):
            self.agent.memory_manager.short_term.clear_session(session_id)
            return "Session conversation history has been cleared."
        elif cmd in ("status", "/status"):
            state = get_state()
            return f"Maya Status: {state.status.value}\nActive Session: {session_id}"
        elif cmd in ("help", "/help"):
            return (
                "Available commands:\n"
                "- /clear: Reset current session memory\n"
                "- /status: Show system status\n"
                "- /help: Show this help message\n"
                "Or simply type any message to converse with Maya."
            )
        else:
            return await self.handle_text(command, session_id=session_id)


_router_singleton: MayaRouter | None = None


def get_router() -> MayaRouter:
    """Return the singleton MayaRouter instance."""
    global _router_singleton
    if _router_singleton is None:
        agent = get_agent()
        _router_singleton = MayaRouter(agent=agent)
    return _router_singleton
