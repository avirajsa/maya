"""Maya Chainlit UI — chat interface with voice testing support."""

import asyncio
import io
import logging
import numpy as np
import chainlit as cl
from chainlit.element import Audio

from maya.agent.agent import get_agent
from maya.agent.router import get_router
from maya.core.config import get_config
from maya.core.state import MayaStatus, get_state
from maya.voice.stt import get_stt
from maya.voice.tts import get_tts

logger = logging.getLogger(__name__)


@cl.on_chat_start
async def on_start() -> None:
    """Initialize user session, configure sidebar actions, and send welcome greetings."""
    session_id = cl.context.session.id
    cl.user_session.set("session_id", session_id)
    cl.user_session.set("audio_buffer", [])
    cl.user_session.set("audio_sample_rate", 16000)

    config = get_config()

    # Welcome message with capability overview
    welcome_text = (
        f"# 👋 Hello, I'm {config.maya_name}\n\n"
        f"I'm your personal AI assistant inspired by JARVIS, designed to help you throughout your day. "
        f"Here are a few things I can do for you right now:\n\n"
        f"- 🔢 **Calculations** — Complex math expressions, percentages, and scientific formulas\n"
        f"- 🔍 **Live Web Search** — Look up recent news, facts, and extract webpage articles\n"
        f"- 💡 **Smart Home Control** — Turn on/off lights, set brightness, control bedroom fans and AC\n"
        f"- 🧠 **Adaptive Memory** — I remember our discussion context and recall past preferences\n"
        f"- 🎤 **Voice Interaction** — Speak to me using the microphone button below\n\n"
        f"How may I assist you today?"
    )

    actions = [
        cl.Action(
            name="check_status",
            payload={"action": "status"},
            label="📊 System Status",
        ),
        cl.Action(
            name="clear_memory",
            payload={"action": "clear"},
            label="🧹 Clear History",
        ),
    ]

    await cl.Message(
        content=welcome_text,
        author=config.maya_name,
        actions=actions,
    ).send()


@cl.action_callback("check_status")
async def on_action_status(action: cl.Action) -> None:
    """Show system and session diagnostics."""
    config = get_config()
    state = get_state()
    session_id = cl.user_session.get("session_id", "unknown")
    status_msg = (
        f"### ⚙️ Maya System Diagnostics\n"
        f"- **Assistant Name**: {config.maya_name}\n"
        f"- **Primary LLM**: `{config.llm_primary}`\n"
        f"- **Fallback 1**: `{config.llm_fallback_1}`\n"
        f"- **Fallback 2**: `{config.llm_fallback_2}`\n"
        f"- **TTS Voice**: `{config.tts_voice}` ({config.tts_provider})\n"
        f"- **Current State**: `{state.status.value}`\n"
        f"- **Session ID**: `{session_id}`"
    )
    await cl.Message(content=status_msg, author=config.maya_name).send()


@cl.action_callback("clear_memory")
async def on_action_clear(action: cl.Action) -> None:
    """Clear conversation history for the current session."""
    session_id = cl.user_session.get("session_id", "default")
    config = get_config()
    agent = get_agent()
    agent.memory_manager.short_term.clear_session(session_id)
    await cl.Message(
        content="✨ Session conversation history has been cleared.",
        author=config.maya_name,
    ).send()




@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Handle text messages with streaming text and an automatic voice reply."""
    session_id = cl.user_session.get("session_id", "default")
    config = get_config()
    state = get_state()

    state.set_status(MayaStatus.THINKING)
    agent = get_agent()
    msg = cl.Message(content="", author=config.maya_name)
    await msg.send()

    try:
        full_response = ""

        async for token in agent.stream_chat(
            message.content,
            session_id=session_id,
        ):
            await msg.stream_token(token)
            full_response += token

        await msg.update()

        # Always synthesize a voice response, even for typed prompts.
        if full_response.strip():
            tts = get_tts()
            audio_bytes = await tts.synthesise(full_response)

            if audio_bytes:
                audio_element = cl.Audio(
                    name="maya_response.wav",
                    content=audio_bytes,
                    mime="audio/wav",
                    auto_play=True,
                )
                await cl.Message(
                    content="",
                    elements=[audio_element],
                    author=config.maya_name,
                ).send()

    except Exception as e:
        logger.error("Agent chat/TTS error: %s", e, exc_info=True)
        await cl.Message(
            content="I encountered an error while processing your message or generating speech.",
            author=config.maya_name,
        ).send()

    finally:
        state.set_status(MayaStatus.IDLE)

@cl.on_audio_start
async def on_audio_start() -> bool:
    """Allow Chainlit to start microphone audio streaming."""
    cl.user_session.set("audio_buffer", [])
    return True


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk) -> None:
    """Buffer real-time audio chunks from microphone stream."""
    audio_buffer: list[bytes] = cl.user_session.get("audio_buffer", [])

    if chunk.isStart:
        audio_buffer = []
        cl.user_session.set("audio_mime_type", chunk.mimeType)

    audio_buffer.append(chunk.data)
    cl.user_session.set("audio_buffer", audio_buffer)


@cl.on_audio_end
async def on_audio_end(elements: list | None = None) -> None:
    """Process finished audio stream: transcribe, query agent, and synthesize spoken reply."""
    session_id = cl.user_session.get("session_id", "default")
    audio_buffer: list = cl.user_session.get("audio_buffer", [])
    config = get_config()

    if not audio_buffer:
        return

    # Reset buffer
    cl.user_session.set("audio_buffer", [])

    try:
        # Combine audio chunks
        audio_data = b"".join(audio_buffer)

        # Convert 16-bit PCM buffer to float32 numpy array
        try:
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        except Exception:
            audio_np = np.frombuffer(audio_data, dtype=np.float32)

        stt = get_stt()
        transcription = await stt.transcribe(audio_np, sample_rate=16000)

        if not transcription.strip():
            await cl.Message(
                content="*(I couldn't hear clearly, please speak again)*",
                author=config.maya_name,
            ).send()
            return

        # Display what was heard
        await cl.Message(
            content=f"🎤 *You said: \"{transcription}\"*",
            author="You",
        ).send()

        # Generate agent response with voice formatting
        agent = get_agent()
        msg = cl.Message(content="", author=config.maya_name)
        await msg.send()

        full_response = ""
        async for token in agent.stream_chat(transcription, session_id=session_id, voice_mode=True):
            await msg.stream_token(token)
            full_response += token
        await msg.update()

        # Synthesize audio with TTS and stream back to browser
        if full_response.strip():
            tts = get_tts()
            audio_bytes = await tts.synthesise(full_response)
            if audio_bytes:
                output_audio_el = cl.Audio(
                    name="maya_response.wav",
                    content=audio_bytes,
                    mime="audio/wav",
                    auto_play=True,
                )
                await cl.Message(
                    content="",
                    elements=[output_audio_el],
                    author=config.maya_name,
                ).send()

    except Exception as e:
        logger.error("Voice processing error: %s", e, exc_info=True)
        await cl.Message(
            content=f"I had trouble processing your voice input: {str(e)}",
            author=config.maya_name,
        ).send()
