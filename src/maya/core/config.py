"""Configuration management for Maya AI Assistant."""

from functools import lru_cache
import logging
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.logging import RichHandler


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── LLM / OpenRouter ────────────────────────────────────────────────────
    openrouter_api_key: str = Field(
        default="",
        alias="OPENROUTER_API_KEY",
        description="API key for OpenRouter",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
        description="Base URL for OpenRouter API",
    )
    llm_primary: str = Field(
        default="anthropic/claude-sonnet-4-5",
        alias="LLM_PRIMARY",
        description="Primary LLM model",
    )
    llm_fallback_1: str = Field(
        default="openai/gpt-4o-mini",
        alias="LLM_FALLBACK_1",
        description="First fallback LLM model",
    )
    llm_fallback_2: str = Field(
        default="meta-llama/llama-3.3-70b-instruct:free",
        alias="LLM_FALLBACK_2",
        description="Second fallback LLM model",
    )
    llm_temperature: float = Field(
        default=0.7,
        alias="LLM_TEMPERATURE",
        description="Sampling temperature for LLM",
    )

    # ─── Voice ───────────────────────────────────────────────────────────────
    whisper_model: str = Field(
        default="base",
        alias="WHISPER_MODEL",
        description="faster-whisper model size (tiny, base, small, medium, large)",
    )
    whisper_device: str = Field(
        default="cpu",
        alias="WHISPER_DEVICE",
        description="Device for faster-whisper (cpu or cuda)",
    )
    tts_voice: str = Field(
        default="en-GB-SoniaNeural",
        alias="TTS_VOICE",
        description="Voice ID for text-to-speech",
    )
    tts_provider: str = Field(
        default="edge",
        alias="TTS_PROVIDER",
        description="TTS provider ('edge' or 'elevenlabs')",
    )
    elevenlabs_api_key: str = Field(
        default="",
        alias="ELEVENLABS_API_KEY",
        description="API key for ElevenLabs TTS",
    )
    elevenlabs_voice_id: str = Field(
        default="",
        alias="ELEVENLABS_VOICE_ID",
        description="Voice ID for ElevenLabs TTS",
    )

    # ─── Home Assistant ──────────────────────────────────────────────────────
    home_assistant_url: str = Field(
        default="http://localhost:8123",
        alias="HOME_ASSISTANT_URL",
        description="Base URL for Home Assistant instance",
    )
    home_assistant_token: str = Field(
        default="",
        alias="HOME_ASSISTANT_TOKEN",
        description="Long-lived access token for Home Assistant",
    )

    # ─── Memory ──────────────────────────────────────────────────────────────
    memory_db_path: str = Field(
        default=".maya/memory.db",
        alias="MEMORY_DB_PATH",
        description="Path to SQLite checkpointer database",
    )
    chroma_persist_path: str = Field(
        default=".maya/chroma",
        alias="CHROMA_PERSIST_PATH",
        description="Path to persistent ChromaDB storage",
    )

    # ─── App ─────────────────────────────────────────────────────────────────
    maya_name: str = Field(
        default="Maya",
        alias="MAYA_NAME",
        description="Name of the assistant",
    )
    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    @property
    def OPENROUTER_API_KEY(self) -> str:
        """Uppercase alias for OpenRouter API key."""
        return self.openrouter_api_key

    def ensure_directories(self) -> None:
        """Ensure necessary data directories exist."""
        db_path = Path(self.memory_db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        chroma_path = Path(self.chroma_persist_path).resolve()
        chroma_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_config() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()


# Alias for compatibility
MayaConfig = Settings



def setup_logging(level: str | None = None) -> None:
    """Configure structured rich logging for Maya."""
    config = get_config()
    target_level = level or config.log_level
    numeric_level = getattr(logging, target_level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                tracebacks_show_locals=False,
                show_time=True,
                show_path=False,
            )
        ],
        force=True,
    )
