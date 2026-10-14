"""Home Assistant fan/AC control tools."""

import asyncio
import concurrent.futures
import logging
from typing import Any
from langchain_core.tools import tool

from maya.integrations.homeassistant import HAError, get_ha_client

logger = logging.getLogger(__name__)

FAN_ENTITY_ID = "fan.bedroom_fan"
CLIMATE_ENTITY_ID = "climate.ac"

FAN_SPEED_PERCENTAGE_MAP = {
    "low": 33,
    "medium": 66,
    "high": 100,
}


def _run_coroutine_sync(coro: Any) -> Any:
    """Execute an async coroutine synchronously, safely handling running event loops."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _turn_on_fan_impl(speed: str = "medium") -> str:
    ha_client = get_ha_client()
    speed_normalized = speed.lower().strip()
    percentage = FAN_SPEED_PERCENTAGE_MAP.get(speed_normalized, 66)

    try:
        await ha_client.turn_on(FAN_ENTITY_ID, percentage=percentage)
        return (
            f"Successfully turned on bedroom fan at {speed_normalized} speed "
            f"({percentage}% power)."
        )
    except HAError as e:
        logger.warning("Home Assistant error turning on fan: %s", e)
        return f"Home Assistant error: {str(e)}"
    except Exception as e:
        logger.error("Failed to connect to Home Assistant to control fan: %s", e)
        return f"Home Assistant is not configured or reachable: {str(e)}"


@tool
async def turn_on_fan(speed: str = "medium") -> str:
    """Turn on the room fan at a designated speed.

    Args:
        speed: Fan speed level: 'low', 'medium', or 'high' (default 'medium').

    Returns:
        Confirmation message indicating whether the fan was turned on.
    """
    return await _turn_on_fan_impl(speed)


turn_on_fan.func = lambda speed="medium": _run_coroutine_sync(_turn_on_fan_impl(speed))


async def _turn_off_fan_impl() -> str:
    ha_client = get_ha_client()
    try:
        await ha_client.turn_off(FAN_ENTITY_ID)
        return "Successfully turned off the bedroom fan."
    except HAError as e:
        logger.warning("Home Assistant error turning off fan: %s", e)
        return f"Home Assistant error: {str(e)}"
    except Exception as e:
        logger.error("Failed to connect to Home Assistant to turn off fan: %s", e)
        return f"Home Assistant is not configured or reachable: {str(e)}"


@tool
async def turn_off_fan() -> str:
    """Turn off the room fan.

    Returns:
        Confirmation message indicating whether the fan was turned off.
    """
    return await _turn_off_fan_impl()


turn_off_fan.func = lambda: _run_coroutine_sync(_turn_off_fan_impl())


async def _turn_on_ac_impl(temperature: float = 24.0) -> str:
    ha_client = get_ha_client()
    temp_target = round(float(temperature), 1)

    try:
        # Set target temperature and enable cooling
        await ha_client.call_service(
            "climate",
            "set_temperature",
            entity_id=CLIMATE_ENTITY_ID,
            temperature=temp_target,
        )
        return f"Successfully set AC to {temp_target}°C."
    except HAError as e:
        logger.warning("Home Assistant error turning on AC: %s", e)
        return f"Home Assistant error: {str(e)}"
    except Exception as e:
        logger.error("Failed to connect to Home Assistant for AC: %s", e)
        return f"Home Assistant is not configured or reachable: {str(e)}"


@tool
async def turn_on_ac(temperature: float = 24.0) -> str:
    """Turn on the air conditioner and set the target temperature.

    Args:
        temperature: Target thermostat temperature in Celsius (default 24.0°C).

    Returns:
        Confirmation message with the new thermostat temperature.
    """
    return await _turn_on_ac_impl(temperature)


turn_on_ac.func = lambda temperature=24.0: _run_coroutine_sync(_turn_on_ac_impl(temperature))


async def _turn_off_ac_impl() -> str:
    ha_client = get_ha_client()
    try:
        await ha_client.call_service(
            "climate",
            "set_hvac_mode",
            entity_id=CLIMATE_ENTITY_ID,
            hvac_mode="off",
        )
        return "Successfully turned off the air conditioner."
    except HAError as e:
        logger.warning("Home Assistant error turning off AC: %s", e)
        return f"Home Assistant error: {str(e)}"
    except Exception as e:
        logger.error("Failed to connect to Home Assistant to turn off AC: %s", e)
        return f"Home Assistant is not configured or reachable: {str(e)}"


@tool
async def turn_off_ac() -> str:
    """Turn off the air conditioner.

    Returns:
        Confirmation message confirming that the AC has been powered down.
    """
    return await _turn_off_ac_impl()


turn_off_ac.func = lambda: _run_coroutine_sync(_turn_off_ac_impl())
