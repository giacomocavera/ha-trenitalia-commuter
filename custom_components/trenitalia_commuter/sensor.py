"""Sensor platform for Trenitalia Commuter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TrenitaliaConfigEntry
from .const import (
    CONF_DEST_LF_NAME,
    CONF_DEST_VT_ID,
    CONF_ORIGIN_LF_NAME,
    CONF_ORIGIN_VT_ID,
    DOMAIN,
)
from .coordinator import CoordinatorData, TrenitaliaCoordinator


@dataclass(frozen=True, kw_only=True)
class TrenitaliaSensorDescription(SensorEntityDescription):
    """Describe a Trenitalia Commuter sensor entity."""

    value_fn: Callable[[CoordinatorData], Any]
    attrs_fn: Callable[[CoordinatorData, TrenitaliaConfigEntry], dict[str, Any]] | None = None


def _next_train_attrs(
    data: CoordinatorData, _entry: TrenitaliaConfigEntry
) -> dict[str, Any]:
    snap = data.snapshot
    attrs: dict[str, Any] = {
        "trains": [t.to_dict() for t in snap.trains],
        "cancelled_count": snap.cancelled_count,
    }
    if snap.next_train is not None:
        nt = snap.next_train
        attrs.update(
            {
                "train_number": nt.train_number,
                "category": nt.category,
                "origin": nt.origin,
                "destination": nt.destination,
                "scheduled_departure": nt.scheduled_departure.isoformat(),
                "expected_departure": nt.expected_departure.isoformat(),
                "scheduled_arrival": nt.scheduled_arrival.isoformat(),
                "delay": nt.delay,
                "platform": nt.platform,
                "platform_confirmed": nt.platform_confirmed,
                "status": nt.status,
                "changes": nt.changes,
                "duration": nt.duration,
            }
        )
    return attrs


def _platform_attrs(
    data: CoordinatorData, _entry: TrenitaliaConfigEntry
) -> dict[str, Any]:
    nt = data.snapshot.next_train
    if nt is None:
        return {}
    return {
        "scheduled_platform": nt.scheduled_platform,
        "actual_platform": nt.actual_platform,
        "confirmed": nt.platform_confirmed,
    }


def _next_train_status_value(data: CoordinatorData) -> str:
    nt = data.snapshot.next_train
    if nt is None:
        return "No trains"
    dep = nt.scheduled_departure.strftime("%H:%M")
    delay_part = f" (+{nt.delay}m)" if nt.delay > 0 else ""
    plat_part = f" • P.{nt.platform}" if nt.platform else ""
    return f"{nt.category} {nt.train_number} • {dep}{delay_part}{plat_part}"


def _last_sync_attrs(
    data: CoordinatorData, entry: TrenitaliaConfigEntry
) -> dict[str, Any]:
    return {
        "lefrecce_last_sync": data.lefrecce_last_sync.isoformat(),
        "vt_last_sync": data.vt_last_sync.isoformat(),
        "origin_vt_id": entry.data.get(CONF_ORIGIN_VT_ID),
        "dest_vt_id": entry.data.get(CONF_DEST_VT_ID),
        "cached_solutions_count": data.cached_solutions_count,
        "fallback_calls": data.snapshot.fallback_calls,
        "last_error": data.last_error,
    }


SENSORS: tuple[TrenitaliaSensorDescription, ...] = (
    TrenitaliaSensorDescription(
        key="next_train",
        translation_key="next_train",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:train",
        value_fn=lambda d: (
            d.snapshot.next_train.expected_departure
            if d.snapshot.next_train
            else None
        ),
        attrs_fn=_next_train_attrs,
    ),
    TrenitaliaSensorDescription(
        key="delay",
        translation_key="delay",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:clock-alert-outline",
        value_fn=lambda d: (
            d.snapshot.next_train.delay if d.snapshot.next_train else None
        ),
    ),
    TrenitaliaSensorDescription(
        key="platform",
        translation_key="platform",
        icon="mdi:sign-direction",
        value_fn=lambda d: (
            (d.snapshot.next_train.platform or "--")
            if d.snapshot.next_train
            else None
        ),
        attrs_fn=_platform_attrs,
    ),
    TrenitaliaSensorDescription(
        key="next_train_status",
        translation_key="next_train_status",
        icon="mdi:train-variant",
        value_fn=_next_train_status_value,
    ),
    TrenitaliaSensorDescription(
        key="last_sync",
        translation_key="last_sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:sync",
        value_fn=lambda d: d.vt_last_sync,
        attrs_fn=_last_sync_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrenitaliaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Trenitalia Commuter sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        TrenitaliaSensor(coordinator, entry, desc) for desc in SENSORS
    )


class TrenitaliaSensor(CoordinatorEntity[TrenitaliaCoordinator], SensorEntity):
    """Sensor entity for a Trenitalia Commuter route."""

    entity_description: TrenitaliaSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TrenitaliaCoordinator,
        entry: TrenitaliaConfigEntry,
        description: TrenitaliaSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
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
    def native_value(self) -> Any:
        """Return current sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if (
            self.coordinator.data is None
            or self.entity_description.attrs_fn is None
        ):
            return None
        return self.entity_description.attrs_fn(
            self.coordinator.data, self._entry
        )