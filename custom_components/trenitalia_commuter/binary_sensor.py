"""Binary sensor platform for Trenitalia Commuter."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TrenitaliaConfigEntry
from .const import CONF_DEST_LF_NAME, CONF_ORIGIN_LF_NAME, DOMAIN
from .coordinator import TrenitaliaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrenitaliaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Trenitalia Commuter binary sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities([TrenitaliaDisruptionSensor(coordinator, entry)])


class TrenitaliaDisruptionSensor(
    CoordinatorEntity[TrenitaliaCoordinator], BinarySensorEntity
):
    """Binary sensor indicating delays or cancellations on the route."""

    _attr_has_entity_name = True
    _attr_translation_key = "disruption"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: TrenitaliaCoordinator,
        entry: TrenitaliaConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_disruption"
        origin = entry.data.get(CONF_ORIGIN_LF_NAME, "")
        dest = entry.data.get(CONF_DEST_LF_NAME, "")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Trenitalia",
            model=f"{origin} -> {dest}",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if a delay or cancellation affects the upcoming train."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.snapshot.disruption

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return disruption details."""
        if self.coordinator.data is None:
            return None
        snap = self.coordinator.data.snapshot
        return {
            "reason": snap.disruption_reason,
            "affected_trains": snap.affected_trains,
            "cancelled_count": snap.cancelled_count,
        }