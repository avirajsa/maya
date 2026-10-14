"""Home Assistant REST API async client integration for Maya."""

import logging
from typing import Any
import httpx

from maya.core.config import get_config

logger = logging.getLogger(__name__)


class HAError(Exception):
    """Base exception for Home Assistant integration errors."""

    pass


class HAClient:
    """Async client for interacting with Home Assistant via REST API."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        config = get_config()
        self.url = (url or config.home_assistant_url).rstrip("/")
        self.token = token or config.home_assistant_token
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        """Return authorization and content headers."""
        headers = {
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily initialize and return the async httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "HAClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def is_available(self) -> bool:
        """Check if Home Assistant instance is reachable and healthy."""
        try:
            client = await self._get_client()
            response = await client.get("/api/")
            return response.status_code == 200
        except Exception as e:
            logger.debug("Home Assistant health check failed: %s", e)
            return False

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """Retrieve state and attributes for a specific entity."""
        client = await self._get_client()
        try:
            response = await client.get(f"/api/states/{entity_id}")
            if response.status_code == 404:
                raise HAError(f"Entity '{entity_id}' not found in Home Assistant.")
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
        except httpx.HTTPStatusError as e:
            raise HAError(f"HTTP error fetching state for '{entity_id}': {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            raise HAError(f"Network error communicating with Home Assistant: {e}") from e

    async def get_all_states(self) -> list[dict[str, Any]]:
        """Retrieve states for all entities."""
        client = await self._get_client()
        try:
            response = await client.get("/api/states")
            response.raise_for_status()
            data: list[dict[str, Any]] = response.json()
            return data
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            raise HAError(f"Failed to fetch entities from Home Assistant: {e}") from e

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Call a Home Assistant service."""
        client = await self._get_client()
        payload: dict[str, Any] = dict(kwargs)
        if entity_id:
            payload["entity_id"] = entity_id

        try:
            response = await client.post(f"/api/services/{domain}/{service}", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HAError(f"Service call {domain}.{service} failed: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            raise HAError(f"Network error calling service {domain}.{service}: {e}") from e

    async def turn_on(self, entity_id: str, **kwargs: Any) -> Any:
        """Turn on a light, switch, fan, or any device."""
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "homeassistant"
        return await self.call_service(domain, "turn_on", entity_id=entity_id, **kwargs)

    async def turn_off(self, entity_id: str, **kwargs: Any) -> Any:
        """Turn off a light, switch, fan, or any device."""
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "homeassistant"
        return await self.call_service(domain, "turn_off", entity_id=entity_id, **kwargs)

    async def toggle(self, entity_id: str, **kwargs: Any) -> Any:
        """Toggle state of a light, switch, fan, or any device."""
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "homeassistant"
        return await self.call_service(domain, "toggle", entity_id=entity_id, **kwargs)


_ha_client_instance: HAClient | None = None


def get_ha_client() -> HAClient:
    """Return the singleton HAClient instance."""
    global _ha_client_instance
    if _ha_client_instance is None:
        _ha_client_instance = HAClient()
    return _ha_client_instance
