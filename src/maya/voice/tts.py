"""Text-to-Speech — edge-tts (default, free) with ElevenLabs as premium option."""

import asyncio
import io
import logging
import os
import shutil
import tempfile
from typing import Any
import httpx

logger = logging.getLogger(__name__)

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    edge_tts = None
    EDGE_TTS_AVAILABLE = False


class TTS:
    """Text-to-Speech synthesis and audio playback engine."""

    def __init__(
        self,
        provider: str = "edge",
        voice: str = "en-GB-SoniaNeural",
        rate: str = "+5%",
        elevenlabs_api_key: str = "",
        elevenlabs_voice_id: str = "",
    ) -> None:
        """Initialize TTS engine.

        Args:
            provider: 'edge' (default) or 'elevenlabs'.
            voice: Voice identifier for edge-tts (e.g. 'en-GB-SoniaNeural').
            rate: Speech rate adjustment string for edge-tts (e.g. '+5%').
            elevenlabs_api_key: Optional API key for ElevenLabs.
            elevenlabs_voice_id: Optional ElevenLabs voice ID.
        """
        self.provider = provider.lower() if provider else "edge"
        self.voice = voice or "en-GB-SoniaNeural"
        self.rate = rate or "+5%"
        self.elevenlabs_api_key = elevenlabs_api_key or ""
        self.elevenlabs_voice_id = elevenlabs_voice_id or ""

    async def _synthesise_edge(self, text: str) -> bytes:
        """Synthesize text using Microsoft Edge TTS."""
        if not EDGE_TTS_AVAILABLE:
            raise ImportError(
                "edge-tts is not installed. Please install it with 'pip install edge-tts'."
            )

        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        audio_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        return b"".join(audio_chunks)

    async def _synthesise_elevenlabs(self, text: str) -> bytes:
        """Synthesize text using ElevenLabs REST API."""
        if not self.elevenlabs_api_key:
            raise ValueError("ElevenLabs API key is not configured.")

        voice_id = self.elevenlabs_voice_id or "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": self.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.30,
                "similarity_boost": 0.75,
                "style": 0.50,
                "speed": 1.15,
                "use_speaker_boost": True,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.content

    async def synthesise(self, text: str) -> bytes:
        """Synthesize text into MP3 audio bytes.

        Uses edge-tts by default. If ElevenLabs is configured, attempts ElevenLabs first
        and falls back to edge-tts on failure.

        Args:
            text: Text to synthesize.

        Returns:
            MP3 audio bytes.
        """
        cleaned_text = text.strip()
        if not cleaned_text:
            return b""

        if self.provider == "elevenlabs" and self.elevenlabs_api_key:
            try:
                logger.debug("Synthesizing speech via ElevenLabs...")
                return await self._synthesise_elevenlabs(cleaned_text)
            except Exception as e:
                logger.warning(
                    "ElevenLabs TTS failed (%s). Falling back to edge-tts...",
                    e,
                )

        logger.debug("Synthesizing speech via edge-tts (voice: %s)...", self.voice)
        return await self._synthesise_edge(cleaned_text)

    async def play(self, audio_bytes: bytes) -> None:
        """Play MP3 audio bytes through system audio output.

        Writes audio to a temporary file, then executes player commands:
        1. ffplay
        2. mpg123
        3. afplay (macOS)
        Fallback: pydub + sounddevice if available.

        Args:
            audio_bytes: MP3 audio bytes.
        """
        if not audio_bytes:
            return

        temp_mp3 = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        temp_path = temp_mp3.name
        temp_mp3.write(audio_bytes)
        temp_mp3.flush()
        temp_mp3.close()

        player_commands = [
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", temp_path],
            ["mpg123", "-q", temp_path],
            ["afplay", temp_path],
        ]

        played = False
        try:
            for cmd in player_commands:
                binary = cmd[0]
                if shutil.which(binary):
                    try:
                        logger.debug("Playing audio via command: %s", binary)
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        await proc.wait()
                        played = True
                        break
                    except Exception as e:
                        logger.debug("Playback with %s failed: %s", binary, e)

            if not played:
                # Python-level fallback using pydub + sounddevice if available
                try:
                    from pydub import AudioSegment
                    import sounddevice as sd
                    import numpy as np

                    seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                    samples = np.array(seg.get_array_of_samples())
                    if seg.channels == 2:
                        samples = samples.reshape((-1, 2))
                    sd.play(samples, samplerate=seg.frame_rate)
                    sd.wait()
                    played = True
                except Exception as e:
                    logger.warning(
                        "No audio player available (ffplay, mpg123, afplay, or pydub/sounddevice): %s",
                        e,
                    )
        finally:
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    async def speak(self, text: str) -> None:
        """Synthesize text and play it immediately.

        Args:
            text: Text to speak out loud.
        """
        audio_bytes = await self.synthesise(text)
        if audio_bytes:
            await self.play(audio_bytes)


_tts_instance: TTS | None = None


def get_tts() -> TTS:
    """Return the singleton TTS instance configured from application settings."""
    global _tts_instance
    if _tts_instance is None:
        try:
            from maya.core.config import get_config
            config = get_config()
            provider = getattr(config, "tts_provider", "edge")
            voice = getattr(config, "tts_voice", "en-GB-SoniaNeural")
            elevenlabs_api_key = getattr(config, "elevenlabs_api_key", "")
            elevenlabs_voice_id = getattr(config, "elevenlabs_voice_id", "")
        except Exception as e:
            logger.warning("Could not load TTS config: %s. Using defaults.", e)
            provider = "edge"
            voice = "en-GB-SoniaNeural"
            elevenlabs_api_key = ""
            elevenlabs_voice_id = ""

        _tts_instance = TTS(
            provider=provider,
            voice=voice,
            rate="+5%",
            elevenlabs_api_key=elevenlabs_api_key,
            elevenlabs_voice_id=elevenlabs_voice_id,
        )
    return _tts_instance
