"""Web search tool using DuckDuckGo (no API key required)."""

import html as html_lib
import logging
import re
import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS = None
    DDGS_AVAILABLE = False


@tool
def search_web(query: str, max_results: int = 5) -> str:
    """Search the web for up-to-date information, news, articles, and facts using DuckDuckGo.

    Args:
        query: Search query or question to search the internet for.
        max_results: Maximum number of search results to retrieve (default 5).

    Returns:
        Formatted string containing search result titles, URLs, and text snippets.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return "Error: Empty search query provided."

    if not DDGS_AVAILABLE:
        return "Error: duckduckgo-search package is not installed."

    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(cleaned_query, max_results=max_results))

        if not raw_results:
            return f"No web search results found for query: '{cleaned_query}'."

        formatted_results: list[str] = []
        for i, item in enumerate(raw_results, 1):
            title = item.get("title", "No Title").strip()
            url = item.get("href") or item.get("url", "")
            snippet = item.get("body") or item.get("snippet", "").strip()
            formatted_results.append(
                f"{i}. **{title}**\n   URL: {url}\n   Summary: {snippet}"
            )

        return "\n\n".join(formatted_results)
    except Exception as e:
        logger.error("DuckDuckGo search error for query '%s': %s", cleaned_query, e)
        return f"Error performing web search: {str(e)}"


@tool
def get_webpage_content(url: str) -> str:
    """Fetch and extract clean readable text content from a web page URL.

    Useful for reading article bodies, documentation pages, or details from search results.

    Args:
        url: Full web URL to fetch (e.g. 'https://en.wikipedia.org/wiki/Artificial_intelligence').

    Returns:
        First 3000 characters of clean text extracted from the webpage.
    """
    target_url = url.strip()
    if not target_url.startswith(("http://", "https://")):
        return f"Error: Invalid URL '{target_url}'. Must begin with http:// or https://"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 MayaAssistant/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(
            timeout=10.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = client.get(target_url)
            response.raise_for_status()
            raw_html = response.text

        # 1. Remove script, style, and noscript elements
        clean_text = re.sub(
            r"<(script|style|noscript|header|footer|nav)[^>]*>.*?</(script|style|noscript|header|footer|nav)>",
            "",
            raw_html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # 2. Strip HTML comments
        clean_text = re.sub(r"<!--.*?-->", "", clean_text, flags=re.DOTALL)
        # 3. Strip all HTML tags
        clean_text = re.sub(r"<[^>]+>", " ", clean_text)
        # 4. Decode HTML entities
        clean_text = html_lib.unescape(clean_text)
        # 5. Normalize whitespace and newlines
        clean_text = re.sub(r"[ \t]+", " ", clean_text)
        clean_text = re.sub(r"\n\s*\n+", "\n\n", clean_text).strip()

        if not clean_text:
            return f"No readable text content found at {target_url}."

        truncated = clean_text[:3000]
        if len(clean_text) > 3000:
            truncated += "\n\n... [Content truncated at 3,000 characters]"

        return truncated

    except httpx.TimeoutException:
        return f"Error: Request timed out while attempting to load {target_url} (10s limit)."
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} received when fetching {target_url}."
    except Exception as e:
        logger.error("Error fetching URL '%s': %s", target_url, e)
        return f"Error fetching webpage content: {str(e)}"
