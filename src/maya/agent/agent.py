"""Maya's LangGraph ReAct agent with checkpointed context and semantic recall."""
from collections.abc import AsyncIterator
from datetime import datetime
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, RemoveMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from maya.agent.memory import MemoryManager, get_memory_manager
from maya.agent.prompts import MAYA_VOICE_SUFFIX, get_system_prompt
from maya.core.config import MayaConfig, get_config
from maya.tools import ALL_TOOLS
from maya.agent.authorized_tools import protect_tool

logger = logging.getLogger(__name__)

def _make_llm(model: str, config: MayaConfig) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        openai_api_key=config.openrouter_api_key or "sk-or-placeholder",
        openai_api_base=config.openrouter_base_url,
        temperature=config.llm_temperature,
        default_headers={"HTTP-Referer": "https://github.com/tauai/maya", "X-Title": "Maya AI Assistant"},
        streaming=True,
    )

class MayaAgent:
    """Agent orchestration, recent conversation history, and long-term recall."""
    def __init__(self, config: MayaConfig, memory_manager: MemoryManager) -> None:
        self.config, self.memory_manager = config, memory_manager
        primary = _make_llm(config.llm_primary, config)
        fallbacks = [_make_llm(m, config) for m in (config.llm_fallback_1, config.llm_fallback_2) if m]
        self.llm = primary.with_fallbacks(fallbacks) if fallbacks else primary
        protected_tools = [protect_tool(tool) for tool in ALL_TOOLS]
        self.agent_graph = create_react_agent(
                model=self.llm,
                tools=protected_tools,
                checkpointer=memory_manager.get_checkpointer(),
                )

    async def _payload(
            self,
            user_input: str,
            session_id: str,
            voice_mode: bool,
            user_context: dict[str, Any] | None = None,
            ) -> tuple[dict[str, Any], dict[str, Any]]:
            
        """Keep only the current system prompt; don't append a new one forever."""
        thread_config = {
                "fonfigureable": {
                    "thread_id": session_id,
                    "maya_user": user_context,
                    }
                }
        removals = []
        try:
            state = await self.agent_graph.aget_state(thread_config)
            for msg in (state.values or {}).get("messages", []):
                if isinstance(msg, SystemMessage) and getattr(msg, "id", None):
                    removals.append(RemoveMessage(id=msg.id))
        except Exception:
            logger.debug("Unable to inspect prior graph state before turn", exc_info=True)
        now = datetime.now().astimezone().strftime("%A, %B %d, %Y, %I:%M %p %Z")
        prompt = get_system_prompt(now)
        memory_user_id = str(user_context["id"]) if user_context else "local"
        memory = await self.memory_manager.enrich_with_memories(
                user_input,
                user_id=memory_user_id,
                )
        if memory:
            prompt += "\n\n" + memory
        if voice_mode:
            prompt += "\n\n" + MAYA_VOICE_SUFFIX
        return {"messages": [*removals, SystemMessage(content=prompt), HumanMessage(content=user_input)]}, thread_config

    @staticmethod
    def _final_text(result: dict[str, Any]) -> str:
        for msg in reversed(result.get("messages", [])):
            if getattr(msg, "type", "") != "ai" or getattr(msg, "tool_calls", None):
                continue
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(p if isinstance(p, str) else p.get("text", "") for p in content if isinstance(p, (str, dict))).strip()
        return "I'm here, but I couldn't generate a response. How can I help?"

    async def _archive_turn(
            self,
            user_input: str,
            response: str,
            session_id: str,
            user_context: dict[str, Any] | None = None,
            ) -> None:
        memory_user_id = str(user_context["id"]) if user_context else "local"
        try:
            await self.memory_manager.remember_turn(
                    session_id,
                    user_input,
                    response,
                    user_id=memory_user_id,
                    )
        except Exception:
            logger.warning("Could not archive conversation turn", exc_info=True)
        # Conservative first-pass extraction: only save explicit, stable statements.
        patterns = [
            (r"\bmy name is ([^.!?\n]{1,80})", "name"),
            (r"\bcall me ([^.!?\n]{1,80})", "preferred_name"),
            (r"\bi prefer ([^.!?\n]{1,180})", "preference"),
            (r"\bremember that ([^.!?\n]{1,180})", "explicit_memory"),
            (r"\bmy goal is ([^.!?\n]{1,180})", "goal"),
            (r"\bi am working on ([^.!?\n]{1,180})", "active_project"),
        ]
        for pattern, key in patterns:
            match = re.search(pattern, user_input.strip(), re.IGNORECASE)
            if match and match.group(1).strip():
                try:
                    await self.memory_manager.long_term.remember_fact(
                            key,
                            match.group(1).strip().rstrip(" ,"),
                            user_id=user_id,
                            )
                except Exception:
                    logger.warning("Could not save explicit memory", exc_info=True)
                break

    async def chat(
            self,
            user_input: str,
            session_id: str = "defult",
            voice_mode: bool = False,
            user_context: dict[str, Any] | None = None,
            ) -> str:
        try:
            payload, cfg = await self._payload(
                    user_input, session_id, voice_mode, user_context
                    )
            result = await self.agent_graph.ainvoke(payload, config=cfg)
            response = self._final_text(result)
            await self._archive_turn(
                    user_input, response, session_id, user_context
                    )
            return response
        except Exception as exc:
            logger.error("Error during agent chat invocation: %s", exc, exc_info=True)
            return f"I apologize, I encountered an issue: {exc}"

    async def stream_chat(
            self,
            user_input: str,
            session_id: str = "default", 
            voice_mode: bool = False,
            user_context: dict[str, Any] | None = None,
            ) -> AsyncIterator[str]:
        try:
            payload, cfg = await self._payload(
                    user_input, session_id, voice_mode, user_context
                    )
            collected: list[str] = []
            async for event in self.agent_graph.astream_events(payload, config=cfg, version="v2"):
                if event.get("event") != "on_chat_model_stream":
                    continue
                chunk = event.get("data", {}).get("chunk")
                content = getattr(chunk, "content", None)
                parts = [content] if isinstance(content, str) else content if isinstance(content, list) else []
                for part in parts:
                    token = part if isinstance(part, str) else part.get("text", "") if isinstance(part, dict) else ""
                    if token:
                        collected.append(token)
                        yield token
            response = "".join(collected).strip()
            if response:
                await self._archive_turn(
                        user_input, response, session_id, user_context
                        )
            else:
                # Avoid silently returning no output for providers that don't stream events.
                response = await self.chat(
                        user_input, session_id, voice_mode, user_context
                        )
                if response:
                    yield response
        except Exception as exc:
            logger.error("Error during streaming chat: %s", exc, exc_info=True)
            yield f"I encountered an issue processing your request: {exc}"

    async def store_memory(
            self,
            fact: str,
            session_id: str = "default",
            user_id: str = "local",
            ) -> None:
        await self.memory_manager.long_term.store(
                session_id,
                fact,
                {"type": "explicit_memory"},
                user_id=user_id,
                )

_agent_singleton: MayaAgent | None = None
def get_agent() -> MayaAgent:
    global _agent_singleton
    if _agent_singleton is None:
        _agent_singleton = MayaAgent(get_config(), get_memory_manager())
    return _agent_singleton
