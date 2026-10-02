"""Binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ToyotaConfigEntry
from .coordinator import VehicleData
from .entity import ToyotaEntity, add_dynamic


@dataclass(frozen=True, kw_only=True)
class ToyotaBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[VehicleData], bool | None]
    attrs_fn: Callable[[VehicleData], dict] | None = None
    dynamic: bool = False


def _loc(fn: Callable[..., bool]):
    return lambda d: fn(d.location) if d.location and d.location.event_type else None


BINARY_SENSORS: tuple[ToyotaBinaryDescription, ...] = (
    ToyotaBinaryDescription(
        key="ignition",
        translation_key="ignition",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_loc(lambda x: x.event_type == "IG-ON"),
    ),
    ToyotaBinaryDescription(
        key="moving",
        translation_key="moving",
        device_class=BinarySensorDeviceClass.MOVING,
        value_fn=_loc(lambda x: x.is_active),
    ),
    ToyotaBinaryDescription(
        key="stolen_tracking",
        translation_key="stolen_tracking",
        device_class=BinarySensorDeviceClass.SAFETY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.location.svt_mode == "04" if d.location and d.location.svt_mode else None,
    ),
    ToyotaBinaryDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.diagnostics.problem_count > 0 if d.diagnostics else None,
        attrs_fn=lambda d: {"problems": list(d.diagnostics.problems)} if d.diagnostics else {},
    ),
    ToyotaBinaryDescription(
        key="speed_alert_enabled",
        translation_key="speed_alert_enabled",
        icon="mdi:speedometer-slow",
        dynamic=True,
        value_fn=lambda d: (
            d.alerts.speed_alert.status.lower() in ("on", "true", "1", "active")
            if d.alerts and d.alerts.speed_alert and d.alerts.speed_alert.status
            else None
        ),
    ),
    ToyotaBinaryDescription(
        key="geofence_break_unread",
        translation_key="geofence_break_unread",
        device_class=BinarySensorDeviceClass.SAFETY,
        dynamic=True,
        value_fn=lambda d: any(b.unread for b in d.geofences.breaks) if d.geofences.breaks else None,
    ),
    ToyotaBinaryDescription(
        key="connected_services",
        translation_key="connected_services",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.vehicle.connected,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ToyotaConfigEntry, add: AddEntitiesCallback) -> None:
    co = entry.runtime_data
    add_dynamic(
        co,
        entry,
        add,
        BINARY_SENSORS,
        lambda v, desc: ToyotaBinary(co, v, desc),
        lambda d, desc: not desc.dynamic or desc.value_fn(d) is not None,
    )


class ToyotaBinary(ToyotaEntity, BinarySensorEntity):
    entity_description: ToyotaBinaryDescription

    def __init__(self, coordinator, vehicle, description: ToyotaBinaryDescription) -> None:
        super().__init__(coordinator, vehicle, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        d = self.vehicle_data
        return self.entity_description.value_fn(d) if d else None

    @property
    def extra_state_attributes(self) -> dict | None:
        d = self.vehicle_data
        fn = self.entity_description.attrs_fn
        return fn(d) if d and fn else None
