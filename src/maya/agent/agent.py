"""Maya's brain — LangGraph ReAct agent powered by OpenRouter with fallbacks."""

from collections.abc import AsyncIterator
from datetime import datetime
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from maya.agent.memory import MemoryManager, get_memory_manager
from maya.agent.prompts import MAYA_VOICE_SUFFIX, get_system_prompt
from maya.core.config import MayaConfig, get_config
from maya.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


def _make_llm(model: str, config: MayaConfig) -> ChatOpenAI:
    """Create a streaming ChatOpenAI client directed to OpenRouter with app headers."""
    api_key = config.openrouter_api_key or "sk-or-placeholder"
    return ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=config.openrouter_base_url,
        temperature=config.llm_temperature,
        default_headers={
            "HTTP-Referer": "https://github.com/tauai/maya",
            "X-Title": "Maya AI Assistant",
        },
        streaming=True,
    )


class MayaAgent:
    """Core Maya ReAct agent managing LLM orchestration, tools, and memory."""

    def __init__(self, config: MayaConfig, memory_manager: MemoryManager) -> None:
        self.config = config
        self.memory_manager = memory_manager

        # Build primary model and fallbacks
        primary = _make_llm(self.config.llm_primary, self.config)
        fallbacks: list[ChatOpenAI] = []
        if self.config.llm_fallback_1:
            fallbacks.append(_make_llm(self.config.llm_fallback_1, self.config))
        if self.config.llm_fallback_2:
            fallbacks.append(_make_llm(self.config.llm_fallback_2, self.config))

        if fallbacks:
            self.llm = primary.with_fallbacks(fallbacks)
        else:
            self.llm = primary

        # Initialize LangGraph ReAct agent with tools and short-term checkpointer
        checkpointer = self.memory_manager.get_checkpointer()
        self.agent_graph = create_react_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            checkpointer=checkpointer,
        )

    async def chat(
        self,
        user_input: str,
        session_id: str = "default",
        voice_mode: bool = False,
    ) -> str:
        """Process user input through the agent and return the final text response.

        Args:
            user_input: Input text from user.
            session_id: Unique thread identifier for short-term checkpointing.
            voice_mode: When True, enforces concise spoken response guidelines.

        Returns:
            The agent's text response.
        """
        try:
            # Retrieve relevant long-term context
            memory_context = await self.memory_manager.enrich_with_memories(user_input)

            # Build system prompt with temporal anchor
            now_str = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
            system_prompt = get_system_prompt(now_str)
            if memory_context:
                system_prompt += f"\n\n{memory_context}"
            if voice_mode:
                system_prompt += f"\n\n{MAYA_VOICE_SUFFIX}"

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input),
            ]

            result = await self.agent_graph.ainvoke(
                {"messages": messages},
                config={"configurable": {"thread_id": session_id}},
            )

            res_messages = result.get("messages", [])
            if res_messages:
                last_msg = res_messages[-1]
                content = last_msg.content
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict) and "text" in part:
                            text_parts.append(part["text"])
                    return "\n".join(text_parts)
                return str(content)

            return "I am here, but I didn't generate a response. How can I help you?"
        except Exception as e:
            logger.error("Error during agent chat invocation: %s", e, exc_info=True)
            return f"I apologize, I encountered an issue: {str(e)}"

    async def stream_chat(
        self,
        user_input: str,
        session_id: str = "default",
        voice_mode: bool = False,
    ) -> AsyncIterator[str]:
        """Stream tokens from the agent response as they are generated.

        Args:
            user_input: Input text from user.
            session_id: Unique thread identifier.
            voice_mode: When True, optimizes for voice formatting.

        Yields:
            Token strings as they arrive.
        """
        try:
            memory_context = await self.memory_manager.enrich_with_memories(user_input)
            now_str = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
            system_prompt = get_system_prompt(now_str)
            if memory_context:
                system_prompt += f"\n\n{memory_context}"
            if voice_mode:
                system_prompt += f"\n\n{MAYA_VOICE_SUFFIX}"

            input_payload = {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_input),
                ]
            }
            thread_config = {"configurable": {"thread_id": session_id}}

            yielded_any = False
            async for event in self.agent_graph.astream_events(
                input_payload,
                config=thread_config,
                version="v2",
            ):
                if event.get("event") == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        token = chunk.content
                        if isinstance(token, str) and token:
                            yielded_any = True
                            yield token
                        elif isinstance(token, list):
                            for item in token:
                                if isinstance(item, dict) and "text" in item:
                                    yielded_any = True
                                    yield item["text"]
                                elif isinstance(item, str) and item:
                                    yielded_any = True
                                    yield item

            if not yielded_any:
                full_response = await self.chat(
                    user_input=user_input,
                    session_id=session_id,
                    voice_mode=voice_mode,
                )
                if full_response:
                    yield full_response

        except Exception as e:
            logger.error("Error during streaming chat: %s", e, exc_info=True)
            yield f"I encountered an issue processing your request: {str(e)}"

    async def store_memory(self, fact: str, session_id: str = "default") -> None:
        """Store a fact into long-term memory."""
        await self.memory_manager.long_term.store(session_id=session_id, content=fact)


_agent_singleton: MayaAgent | None = None


def get_agent() -> MayaAgent:
    """Return the singleton MayaAgent instance."""
    global _agent_singleton
    if _agent_singleton is None:
        config = get_config()
        memory_manager = get_memory_manager()
        _agent_singleton = MayaAgent(config=config, memory_manager=memory_manager)
    return _agent_singleton
