"""Voice pipeline: mic → VAD → STT → Agent → TTS → speaker."""

import asyncio
import logging
from typing import Any, Callable, Coroutine
import numpy as np

from maya.voice.stt import STT, get_stt
from maya.voice.tts import TTS, get_tts

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    SOUNDDEVICE_AVAILABLE = False


class VoicePipeline:
    """End-to-end voice loop: Microphone → Silence Detection → STT → Agent → TTS → Playback."""

    def __init__(
        self,
        stt: STT,
        tts: TTS,
        agent_fn: Callable[[str, str], Coroutine[Any, Any, str]],
    ) -> None:
        """Initialize the voice pipeline.

        Args:
            stt: STT instance.
            tts: TTS instance.
            agent_fn: Async callable taking (text: str, session_id: str) -> response: str.
        """
        self.stt = stt
        self.tts = tts
        self.agent_fn = agent_fn
        self._running = False

    async def record_until_silence(
        self,
        sample_rate: int = 16000,
        silence_threshold: float = 0.01,
        max_duration: float = 30.0,
        min_duration: float = 0.5,
    ) -> np.ndarray:
        """Record audio from the microphone until silence is detected.

        Uses sounddevice to record in chunks. Continuously calculates the RMS
        of each chunk. Stops recording once 1.5 seconds of silence are detected
        after at least min_duration of recording, or when max_duration is reached.

        Args:
            sample_rate: Recording sampling rate in Hz (default 16000).
            silence_threshold: RMS amplitude below which audio is considered silence.
            max_duration: Maximum allowed recording duration in seconds.
            min_duration: Minimum duration to record before evaluating silence cutoff.

        Returns:
            1D numpy array of float32 audio samples.
        """
        if not SOUNDDEVICE_AVAILABLE:
            logger.error("sounddevice is not installed. Microphone recording unavailable.")
            return np.array([], dtype=np.float32)

        loop = asyncio.get_running_loop()
        audio_queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        chunk_size = int(sample_rate * 0.1)  # 100ms chunks

        def audio_callback(
            indata: np.ndarray,
            frames: int,
            time_info: Any,
            status: Any,
        ) -> None:
            if status:
                logger.debug("SoundDevice stream status: %s", status)
            # Copy data into queue
            chunk = indata.copy().flatten().astype(np.float32)
            loop.call_soon_threadsafe(audio_queue.put_nowait, chunk)

        recorded_chunks: list[np.ndarray] = []
        total_duration = 0.0
        silence_duration = 0.0
        speech_detected = False

        try:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=chunk_size,
                callback=audio_callback,
            ):
                logger.info("Listening for voice input...")
                while total_duration < max_duration:
                    try:
                        chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue

                    recorded_chunks.append(chunk)
                    chunk_duration = len(chunk) / sample_rate
                    total_duration += chunk_duration

                    # Calculate Root Mean Square (RMS) energy
                    rms = float(np.sqrt(np.mean(chunk**2))) if len(chunk) > 0 else 0.0

                    if rms >= silence_threshold:
                        speech_detected = True
                        silence_duration = 0.0
                    else:
                        if speech_detected:
                            silence_duration += chunk_duration

                    # Stop if speech was detected, minimum duration passed, and 1.5s of silence occurred
                    if speech_detected and total_duration >= min_duration and silence_duration >= 1.5:
                        logger.debug(
                            "Silence threshold reached (duration: %.2fs, silence: %.2fs). Stopping recording.",
                            total_duration,
                            silence_duration,
                        )
                        break

        except Exception as e:
            logger.error("Error during microphone recording: %s", e)
            return np.array([], dtype=np.float32)

        if not recorded_chunks:
            return np.array([], dtype=np.float32)

        full_audio = np.concatenate(recorded_chunks, axis=0)
        logger.info("Recorded %.2f seconds of audio.", len(full_audio) / sample_rate)
        return full_audio

    async def listen_and_respond(self, session_id: str = "default") -> str | None:
        """Execute a single voice turn: record, transcribe, pass to agent, and speak response.

        Args:
            session_id: Session identifier for context tracking.

        Returns:
            The agent's text response, or None if no speech was detected.
        """
        logger.info("Starting voice turn for session '%s'...", session_id)
        audio = await self.record_until_silence()
        if len(audio) == 0:
            logger.info("No audio recorded.")
            return None

        # Step 1: Transcribe audio to text
        user_text = await self.stt.transcribe(audio)
        user_text = user_text.strip()
        if not user_text:
            logger.info("No speech detected in transcription.")
            return None

        logger.info("User said: '%s'", user_text)

        # Step 2: Send transcription to agent
        response_text = await self.agent_fn(user_text, session_id)
        if not response_text:
            return None

        logger.info("Maya responded: '%s'", response_text)

        # Step 3: Speak agent response
        await self.tts.speak(response_text)
        return response_text

    async def run_loop(self, session_id: str = "default") -> None:
        """Run continuous voice loop until KeyboardInterrupt or cancellation.

        Args:
            session_id: Session identifier.
        """
        self._running = True
        logger.info("Maya Voice Pipeline started. Listening continuously...")
        try:
            while self._running:
                try:
                    await self.listen_and_respond(session_id=session_id)
                    await asyncio.sleep(0.2)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    raise
                except Exception as e:
                    logger.error("Error in voice loop turn: %s", e)
                    await asyncio.sleep(1.0)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Voice loop stopped by user interrupt.")
        finally:
            self._running = False

    def stop(self) -> None:
        """Signal the voice loop to stop."""
        self._running = False


def get_voice_pipeline(
    agent_fn: Callable[[str, str], Coroutine[Any, Any, str]] | None = None,
) -> VoicePipeline:
    """Create and return a configured VoicePipeline instance.

    Args:
        agent_fn: Optional custom agent callable. If not provided,
                  lazily wraps the MayaAgent singleton.

    Returns:
        VoicePipeline instance.
    """
    stt = get_stt()
    tts = get_tts()

    if agent_fn is None:
        async def default_agent_fn(text: str, session_id: str) -> str:
            from maya.agent.agent import get_agent
            agent = get_agent()
            return await agent.chat(text, session_id=session_id, voice_mode=True)

        agent_fn = default_agent_fn

    return VoicePipeline(stt=stt, tts=tts, agent_fn=agent_fn)
