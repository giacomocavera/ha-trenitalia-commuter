"""The Trenitalia Commuter integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .coordinator import TrenitaliaCoordinator

    type TrenitaliaConfigEntry = ConfigEntry[TrenitaliaCoordinator]
else:
    type TrenitaliaConfigEntry = object


async def async_setup_entry(
    hass: HomeAssistant, entry: TrenitaliaConfigEntry
) -> bool:
    """Set up Trenitalia Commuter from a config entry."""
    from homeassistant.const import Platform
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .coordinator import TrenitaliaCoordinator

    platforms: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

    session = async_get_clientsession(hass)
    coordinator = TrenitaliaCoordinator(hass, entry, session)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: TrenitaliaConfigEntry
) -> bool:
    """Unload a config entry."""
    from homeassistant.const import Platform

    platforms: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]
    return await hass.config_entries.async_unload_platforms(entry, platforms)


async def _async_update_listener(
    hass: HomeAssistant, entry: TrenitaliaConfigEntry
) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)