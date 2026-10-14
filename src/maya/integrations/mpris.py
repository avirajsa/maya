"""MPRIS D-Bus Media Player integration for Maya.

Note:
    MPRIS (Media Player Remote Interfacing Specification) is a standard D-Bus interface
    for controlling media players on Linux (e.g. Spotify, VLC, Firefox, Chrome).
    
    This integration requires Linux with a running D-Bus session daemon and either
    dbus-python bindings or the 'playerctl' command-line utility.
    
    If D-Bus is unavailable or no supported media player is currently running,
    this client provides graceful fallback responses without raising fatal exceptions.
"""

import asyncio
import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)


class MPRISClient:
    """Client for controlling MPRIS2-compatible media players on Linux."""

    def __init__(self, preferred_player: str | None = None) -> None:
        self.preferred_player = preferred_player
        self._has_playerctl = shutil.which("playerctl") is not None
        self._dbus_available: bool | None = None

        if not self._has_playerctl:
            self._check_dbus_support()

    def _check_dbus_support(self) -> bool:
        """Check if native python D-Bus library is importable."""
        if self._dbus_available is not None:
            return self._dbus_available

        try:
            import dbus  # type: ignore[import-untyped]  # noqa: F401

            self._dbus_available = True
        except ImportError:
            self._dbus_available = False
            logger.debug(
                "Neither 'playerctl' nor 'dbus-python' is available. "
                "MPRIS controls will operate in fallback mode."
            )
        return self._dbus_available

    async def _run_playerctl_command(self, *args: str) -> tuple[int, str]:
        """Execute a playerctl command asynchronously."""
        if not self._has_playerctl:
            return 1, "playerctl not installed"

        cmd = ["playerctl"]
        if self.preferred_player:
            cmd.extend(["-p", self.preferred_player])
        cmd.extend(args)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode or 0, stdout.decode().strip()
        except Exception as e:
            logger.debug("Failed to run playerctl: %s", e)
            return 1, str(e)

    async def play(self) -> bool:
        """Resume or start media playback."""
        if self._has_playerctl:
            code, _ = await self._run_playerctl_command("play")
            return code == 0

        logger.info("MPRIS play called (stub/fallback mode)")
        return False

    async def pause(self) -> bool:
        """Pause media playback."""
        if self._has_playerctl:
            code, _ = await self._run_playerctl_command("pause")
            return code == 0

        logger.info("MPRIS pause called (stub/fallback mode)")
        return False

    async def play_pause(self) -> bool:
        """Toggle media playback."""
        if self._has_playerctl:
            code, _ = await self._run_playerctl_command("play-pause")
            return code == 0

        logger.info("MPRIS play_pause called (stub/fallback mode)")
        return False

    async def next_track(self) -> bool:
        """Skip to next media track."""
        if self._has_playerctl:
            code, _ = await self._run_playerctl_command("next")
            return code == 0

        logger.info("MPRIS next_track called (stub/fallback mode)")
        return False

    async def prev_track(self) -> bool:
        """Skip to previous media track."""
        if self._has_playerctl:
            code, _ = await self._run_playerctl_command("previous")
            return code == 0

        logger.info("MPRIS prev_track called (stub/fallback mode)")
        return False

    async def get_current_track(self) -> dict[str, Any] | None:
        """Retrieve metadata of the currently playing track.

        Returns:
            Dictionary with title, artist, album, status or None if unavailable.
        """
        if self._has_playerctl:
            status_code, status = await self._run_playerctl_command("status")
            if status_code != 0:
                return None

            _, title = await self._run_playerctl_command("metadata", "title")
            _, artist = await self._run_playerctl_command("metadata", "artist")
            _, album = await self._run_playerctl_command("metadata", "album")

            return {
                "title": title or "Unknown",
                "artist": artist or "Unknown",
                "album": album or "Unknown",
                "status": status.lower(),
            }

        logger.debug("MPRIS get_current_track called (stub/fallback mode)")
        return None


_default_mpris_client: MPRISClient | None = None


def get_mpris_client() -> MPRISClient:
    """Return the singleton MPRISClient instance."""
    global _default_mpris_client
    if _default_mpris_client is None:
        _default_mpris_client = MPRISClient()
    return _default_mpris_client
