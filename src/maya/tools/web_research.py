"""LangChain tools that expose Tavily search and Firecrawl extraction to Maya."""

from __future__ import annotations

import asyncio
from maya.research.ddg_search import search_web as ddgs_search
import json
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import tool

from maya.research.fetch import firecrawl_scrape
from maya.research.search import tavily_search


def _format_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No web results were returned. Try a more specific query."
    return "\n\n".join(
        f"[{index}] {item.get('title', 'Untitled')}\n"
        f"URL: {item.get('url', '')}\n"
        f"Snippet: {item.get('snippet', '')}\n"
        f"Published: {item.get('published_date') or 'date not provided'}"
        for index, item in enumerate(results, start=1)
    )


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the public web with Tavily. Use for current facts, news, and research leads. Cite returned URLs in your answer."""
    try:
        results = await tavily_search(query, max_results=max_results)
        return _format_results(results)
    except Exception as exc:
        return f"Web search failed: {type(exc).__name__}: {exc}"


@tool
async def scrape_webpage(url: str) -> str:
    """Read a public webpage using Firecrawl and return its title, URL, and main text. Use URLs from web search when possible."""
    try:
        page = await firecrawl_scrape(url)
        return (
            f"Title: {page['title']}\n"
            f"URL: {page['url']}\n"
            f"Published: {page.get('published_date') or 'date not provided'}\n\n"
            f"CONTENT (may be truncated):\n{page['content']}"
        )
    except Exception as exc:
        return f"Page extraction failed: {type(exc).__name__}: {exc}"


async def _search_with_fallback(
    query: str,
    max_results: int,
) -> list[dict]:
    """Try Tavily first, then DDGS if Tavily fails."""
    try:
        results = await tavily_search(
            query,
            max_results=max_results,
        )
        if results:
            return results
    except Exception:
        pass

    return await asyncio.to_thread(
        ddgs_search,
        query,
        max_results,
    )

@tool
async def research_web(query: str, max_pages: int = 3) -> str:
    """Run a small web research pass: search with Tavily, scrape up to three relevant pages, and return source-labelled evidence. For comprehensive research, continue with follow-up searches and cross-check claims."""
    try:
        results = await _search_with_fallback(
        query,
        max_results=max_pages,
        )
    except Exception as exc:
        return f"Research search failed: {type(exc).__name__}: {exc}"

    # Keep the tool bounded to control latency, context size, and free-tier usage.
    limit = max(1, min(int(max_pages), 3))
    selected = results[:limit]
    if not selected:
        return "No search results were found. Try another query."

    pages = await asyncio.gather(
        *(firecrawl_scrape(item["url"]) for item in selected),
        return_exceptions=True,
    )
    sections: list[str] = []
    for index, (result, page) in enumerate(zip(selected, pages), start=1):
        if isinstance(page, Exception):
            sections.append(
                f"SOURCE {index}: {result.get('title', 'Untitled')}\n"
                f"URL: {result['url']}\n"
                f"Search snippet only; page extraction failed: {page}"
            )
        else:
            sections.append(
                f"SOURCE {index}: {page['title']}\n"
                f"URL: {page['url']}\n"
                f"Published: {page.get('published_date') or result.get('published_date') or 'date not provided'}\n"
                f"CONTENT:\n{page['content']}"
            )
    return "\n\n---\n\n".join(sections)
