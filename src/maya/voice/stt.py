"""Speech-to-Text using faster-whisper (local, fast, no API key needed)."""

import asyncio
import logging
import os
import tempfile
import wave
from typing import Any
import numpy as np

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None
    FASTER_WHISPER_AVAILABLE = False

logger = logging.getLogger(__name__)


class STT:
    """Speech-to-Text engine powered by faster-whisper."""

    def __init__(self, model_size: str = "base", device: str = "cpu") -> None:
        """Initialize STT with model size and device, lazy-loading the model.

        Args:
            model_size: Size of Whisper model ('tiny', 'base', 'small', 'medium', 'large-v3').
            device: Computation device ('cpu' or 'cuda').
        """
        self.model_size = model_size
        self.device = device
        self._model: Any = None
        self._lock = asyncio.Lock()

    def _load_model(self) -> None:
        """Load the faster-whisper model into memory with int8 quantization."""
        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError(
                "faster-whisper is not installed. Please install it using 'pip install faster-whisper'."
            )

        if self._model is None:
            logger.info(
                "Loading faster-whisper model '%s' on %s (compute_type='int8')...",
                self.model_size,
                self.device,
            )
            try:
                self._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type="int8",
                )
            except Exception as e:
                logger.warning(
                    "Failed to initialize WhisperModel with compute_type='int8' (%s), trying 'auto'...",
                    e,
                )
                self._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type="auto",
                )
            logger.info("faster-whisper model '%s' loaded successfully.", self.model_size)

    def _transcribe_file_sync(self, path: str, language: str | None = None) -> str:
        """Synchronously transcribe an audio file using faster-whisper."""
        self._load_model()
        segments, info = self._model.transcribe(
            path,
            beam_size=5,
            language=language,
        )
        text_segments = [segment.text for segment in segments]
        cleaned_text = " ".join(text_segments).strip()
        logger.debug(
            "Transcribed '%s' (language: %s, prob: %.2f): %s",
            path,
            getattr(info, "language", "unknown"),
            getattr(info, "language_probability", 0.0),
            cleaned_text,
        )
        return cleaned_text

    def transcribe_file(self, path: str, language: str | None = None) -> str:
        """Transcribe an audio file synchronously. Useful for testing and CLI scripts.

        Args:
            path: Path to the audio file (.wav, .mp3, etc.).
            language: Optional language code (e.g., 'en').

        Returns:
            Cleaned transcript string.
        """
        return self._transcribe_file_sync(path, language=language)

    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> str:
        """Transcribe a numpy audio array asynchronously.

        Converts float32 audio to int16, writes to a temporary WAV file,
        and transcribes with beam_size=5.

        Args:
            audio: 1D numpy array of audio samples (float32 [-1.0, 1.0] or int16).
            sample_rate: Sampling rate in Hz (default 16000).
            language: Optional language code.

        Returns:
            Cleaned transcript string.
        """
        if audio is None or len(audio) == 0:
            return ""

        # Convert float32 [-1.0, 1.0] to int16 PCM
        if audio.dtype in (np.float32, np.float64):
            audio_clipped = np.clip(audio, -1.0, 1.0)
            audio_int16 = (audio_clipped * 32767.0).astype(np.int16)
        elif audio.dtype == np.int16:
            audio_int16 = audio
        else:
            audio_int16 = audio.astype(np.int16)

        # Write to temporary WAV file
        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_path = temp_wav.name
        temp_wav.close()

        try:
            with wave.open(temp_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit PCM
                wf.setframerate(sample_rate)
                wf.writeframes(audio_int16.tobytes())

            async with self._lock:
                text = await asyncio.to_thread(
                    self._transcribe_file_sync,
                    temp_path,
                    language,
                )
            return text
        finally:
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


_stt_instance: STT | None = None


def get_stt() -> STT:
    """Return the singleton STT instance configured from application settings."""
    global _stt_instance
    if _stt_instance is None:
        try:
            from maya.core.config import get_config
            config = get_config()
            model_size = getattr(config, "whisper_model", "base")
            device = getattr(config, "whisper_device", "cpu")
        except Exception as e:
            logger.warning("Could not read STT config: %s. Using defaults.", e)
            model_size = "base"
            device = "cpu"

        _stt_instance = STT(model_size=model_size, device=device)
    return _stt_instance
