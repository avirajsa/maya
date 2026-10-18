"""Authorization wrappers for Maya's LangChain tools."""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool

# Available to everyone, including unauthenticated local voice sessions.
PUBLIC_TOOLS = frozenset({
    "calculate",
    "summarise_text",
    "get_current_datetime",
    "web_search",
    "scrape_webpage",
    "research_web",
})


def _denial(tool_name: str, config: RunnableConfig | None) -> str | None:
    """Return a denial message when the current identity lacks permission."""

    configurable = (config or {}).get("configurable", {})
    user = configurable.get("maya_user")

    # Local terminal/voice/Chainlit sessions have no verified API identity.
    # They can use public tools, but cannot execute privileged actions.
    if not isinstance(user, dict):
        return (
            None if tool_name in PUBLIC_TOOLS
            else f"Permission denied: '{tool_name}' requires an authenticated account."
        )

    role = user.get("role")
    if role == "owner":
        return None

    permissions = user.get("permissions", [])
    if tool_name in PUBLIC_TOOLS or (
        isinstance(permissions, (list, tuple, set, frozenset))
        and tool_name in permissions
    ):
        return None

    return f"Permission denied: you are not authorized to use '{tool_name}'."


def protect_tool(tool: BaseTool) -> BaseTool:
    """Wrap a tool without changing the schema presented to the model."""

    async def protected_async(
        config: RunnableConfig,
        **kwargs: Any,
    ) -> Any:
        denial = _denial(tool.name, config)
        if denial:
            return denial
        return await tool.ainvoke(kwargs, config=config)

    def protected_sync(
        config: RunnableConfig,
        **kwargs: Any,
    ) -> Any:
        denial = _denial(tool.name, config)
        if denial:
            return denial
        return tool.invoke(kwargs, config=config)

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        func=protected_sync,
        coroutine=protected_async,
        return_direct=tool.return_direct,
    )
