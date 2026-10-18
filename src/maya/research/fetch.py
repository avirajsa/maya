"""Firecrawl page extraction for Maya."""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"


def _validate_public_http_url(url: str) -> str:
    """Reject non-web URLs and obvious private/local destinations before scraping."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only absolute http:// and https:// URLs can be scraped.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Local and internal URLs cannot be scraped.")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(info[4][0])
                for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            }
        except socket.gaierror:
            # Let Firecrawl return the canonical DNS error for unresolved public hosts.
            addresses = set()
    if any(
        not address.is_global
        for address in addresses
    ):
        raise ValueError("Private, loopback, and reserved network addresses are blocked.")
    return url.strip()


async def firecrawl_scrape(url: str) -> dict[str, Any]:
    """Scrape one public page and return readable Markdown plus source metadata.

    Requires FIRECRAWL_API_KEY. This sends the URL to Firecrawl's hosted service.
    """
    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "FIRECRAWL_API_KEY is missing. Add a Firecrawl key to .env, or use the HTTP fallback."
        )
    safe_url = _validate_public_http_url(url)
    payload = {
        "url": safe_url,
        "formats": ["markdown"],
        "onlyMainContent": True,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
        response = await client.post(
            FIRECRAWL_SCRAPE_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code == 401:
            raise RuntimeError("Firecrawl rejected the API key. Check FIRECRAWL_API_KEY.")
        if response.status_code == 429:
            raise RuntimeError("Firecrawl rate limit or credit allowance reached.")
        response.raise_for_status()
        payload = response.json()

    if payload.get("success") is False:
        raise RuntimeError(f"Firecrawl could not scrape this page: {payload.get('error', 'unknown error')}")

    page = payload.get("data") or {}
    metadata = page.get("metadata") or {}
    markdown = page.get("markdown") or ""
    # Avoid returning arbitrarily large pages into the LLM context window.
    max_chars = int(os.getenv("MAYA_RESEARCH_MAX_PAGE_CHARS", "18000"))
    markdown = markdown[: max(1000, min(max_chars, 40000))]
    return {
        "url": metadata.get("sourceURL") or safe_url,
        "title": metadata.get("title") or safe_url,
        "description": metadata.get("description") or "",
        "published_date": metadata.get("publishedTime") or metadata.get("og:published_time"),
        "content": markdown,
    }
