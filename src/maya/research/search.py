"""Tavily-backed web search for Maya."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Resolve the project root: maya/src/maya/research/search.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

import os
from typing import Any

import httpx

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def tavily_search(
    query: str,
    *,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    time_range: str | None = None,
) -> list[dict[str, Any]]:
    """Search the public web with Tavily and return normalized results.

    Requires TAVILY_API_KEY. `search_depth` can be `basic` or `advanced`;
    advanced search may consume more credits depending on the account plan.
    """
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "TAVILY_API_KEY is missing. Add your no-credit-card Tavily key to .env."
        )
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty.")
    if search_depth not in {"basic", "advanced"}:
        raise ValueError("search_depth must be 'basic' or 'advanced'.")
    if topic not in {"general", "news", "finance"}:
        raise ValueError("topic must be 'general', 'news', or 'finance'.")

    payload: dict[str, Any] = {
        "query": query,
        "topic": topic,
        "search_depth": search_depth,
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": False,
        "include_raw_content": False,
    }
    if time_range:
        payload["time_range"] = time_range

    async with httpx.AsyncClient(timeout=httpx.Timeout(25.0)) as client:
        response = await client.post(
            TAVILY_SEARCH_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code == 401:
            raise RuntimeError("Tavily rejected the API key. Check TAVILY_API_KEY.")
        if response.status_code == 429:
            raise RuntimeError("Tavily rate limit or credit allowance reached.")
        response.raise_for_status()
        data = response.json()

    normalized: list[dict[str, Any]] = []
    for item in data.get("results", []):
        url = item.get("url")
        if not url:
            continue
        normalized.append(
            {
                "title": item.get("title") or url,
                "url": url,
                "snippet": item.get("content") or "",
                "score": item.get("score"),
                "published_date": item.get("published_date"),
            }
        )
    return normalized
