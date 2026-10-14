"""Home Assistant lights control tools."""

import asyncio
import concurrent.futures
import logging
from typing import Any
from langchain_core.tools import tool

from maya.integrations.homeassistant import HAError, get_ha_client

logger = logging.getLogger(__name__)

# Standard room name mappings to Home Assistant entity IDs
ROOM_MAP: dict[str, str] = {
    "bedroom": "light.bedroom",
    "living": "light.living_room",
    "living room": "light.living_room",
    "living_room": "light.living_room",
    "kitchen": "light.kitchen",
    "hallway": "light.hallway",
    "office": "light.office",
    "desk": "light.desk_light",
    "desk light": "light.desk_light",
    "fairy": "light.fairy_lights",
    "fairy lights": "light.fairy_lights",
    "all": "light.all_lights",
}


def _resolve_entity_id(room: str) -> str:
    """Resolve a user-provided room name to a Home Assistant light entity ID."""
    key = room.lower().strip()
    if key in ROOM_MAP:
        return ROOM_MAP[key]
    if key.startswith("light."):
        return key
    return f"light.{key.replace(' ', '_')}"


def _run_coroutine_sync(coro: Any) -> Any:
    """Execute an async coroutine synchronously, safely handling running event loops."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _turn_on_lights_impl(room: str = "all") -> str:
    entity_id = _resolve_entity_id(room)
    ha_client = get_ha_client()

    try:
        await ha_client.turn_on(entity_id)
        return f"Successfully turned on lights for {room} ({entity_id})."
    except HAError as e:
        logger.warning("Home Assistant error turning on lights for %s: %s", room, e)
        return f"Home Assistant error: {str(e)}"
    except Exception as e:
        logger.error("Failed to communicate with Home Assistant: %s", e)
        return f"Home Assistant is not configured or reachable: {str(e)}"


@tool
async def turn_on_lights(room: str = "all") -> str:
    """Turn on the lights in a specific room or across the entire house.

    Args:
        room: Room or light identifier (e.g. 'bedroom', 'living', 'kitchen', 'fairy lights', 'all'). Defaults to 'all'.

    Returns:
        Result message describing whether the lights were turned on.
    """
    return await _turn_on_lights_impl(room)


turn_on_lights.func = lambda room="all": _run_coroutine_sync(_turn_on_lights_impl(room))


async def _turn_off_lights_impl(room: str = "all") -> str:
    entity_id = _resolve_entity_id(room)
    ha_client = get_ha_client()

    try:
        await ha_client.turn_off(entity_id)
        return f"Successfully turned off lights for {room} ({entity_id})."
    except HAError as e:
        logger.warning("Home Assistant error turning off lights for %s: %s", room, e)
        return f"Home Assistant error: {str(e)}"
    except Exception as e:
        logger.error("Failed to communicate with Home Assistant: %s", e)
        return f"Home Assistant is not configured or reachable: {str(e)}"


@tool
async def turn_off_lights(room: str = "all") -> str:
    """Turn off the lights in a specific room or across the entire house.

    Args:
        room: Room or light identifier (e.g. 'bedroom', 'living', 'kitchen', 'fairy lights', 'all'). Defaults to 'all'.

    Returns:
        Result message describing whether the lights were turned off.
    """
    return await _turn_off_lights_impl(room)


turn_off_lights.func = lambda room="all": _run_coroutine_sync(_turn_off_lights_impl(room))


async def _set_light_brightness_impl(room: str, brightness: int) -> str:
    entity_id = _resolve_entity_id(room)
    ha_client = get_ha_client()

    # Clamp brightness between 0 and 100
    brightness_clamped = max(0, min(100, brightness))

    try:
        if brightness_clamped == 0:
            await ha_client.turn_off(entity_id)
            return f"Brightness set to 0%; turned off lights for {room} ({entity_id})."

        await ha_client.turn_on(entity_id, brightness_pct=brightness_clamped)
        return f"Successfully set brightness for {room} ({entity_id}) to {brightness_clamped}%."
    except HAError as e:
        logger.warning("Home Assistant error setting brightness for %s: %s", room, e)
        return f"Home Assistant error: {str(e)}"
    except Exception as e:
        logger.error("Failed to communicate with Home Assistant: %s", e)
        return f"Home Assistant is not configured or reachable: {str(e)}"


@tool
async def set_light_brightness(room: str, brightness: int) -> str:
    """Adjust the brightness level of a specific room light.

    Args:
        room: Room or light identifier (e.g. 'bedroom', 'living', 'desk').
        brightness: Brightness percentage from 0 (off) to 100 (maximum brightness).

    Returns:
        Result message confirming brightness adjustment.
    """
    return await _set_light_brightness_impl(room, brightness)


set_light_brightness.func = lambda room, brightness: _run_coroutine_sync(
    _set_light_brightness_impl(room, brightness)
)
