"""Sensors."""

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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ToyotaConfigEntry
from .const import CONF_RESOLVE_ADDRESS, DEFAULT_RESOLVE_ADDRESS
from .coordinator import VehicleData
from .entity import ToyotaEntity


@dataclass(frozen=True, kw_only=True)
class ToyotaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[VehicleData], Any]
    attrs_fn: Callable[[VehicleData], dict[str, Any]] | None = None


def _tele(attr: str):
    return lambda d: getattr(d.telemetry, attr) if d.telemetry else None


def _trip(attr: str):
    return lambda d: getattr(d.last_trip, attr) if d.last_trip else None


def _active_geofences(d: VehicleData) -> int | None:
    return sum(g.active for g in d.geofences) if d.geofences else None


SENSORS: tuple[ToyotaSensorDescription, ...] = (
    ToyotaSensorDescription(
        key="address",
        translation_key="address",
        icon="mdi:map-marker",
        value_fn=lambda d: d.address[:255] if d.address else None,
        attrs_fn=lambda d: {"full_address": d.address} if d.address and len(d.address) > 255 else {},
    ),
    ToyotaSensorDescription(
        key="maps_key",
        translation_key="maps_key",
        icon="mdi:key",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.location.maps_key if d.location else None,
    ),
    ToyotaSensorDescription(
        key="fuel_level",
        translation_key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-station",
        value_fn=_tele("fuel_percent"),
    ),
    ToyotaSensorDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_tele("odometer"),
    ),
    ToyotaSensorDescription(
        key="last_report",
        translation_key="last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_tele("reported_at"),
    ),
    ToyotaSensorDescription(
        key="last_ignition_on",
        translation_key="last_ignition_on",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_tele("ignition_on_at"),
    ),
    ToyotaSensorDescription(
        key="last_trip_distance",
        translation_key="last_trip_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=_trip("distance"),
        attrs_fn=lambda d: (
            {
                "start": d.last_trip.start,
                "end": d.last_trip.end,
                "fuel_start": d.last_trip.fuel_start,
                "fuel_end": d.last_trip.fuel_end,
                "start_latitude": d.last_trip.start_lat,
                "start_longitude": d.last_trip.start_lon,
                "end_latitude": d.last_trip.end_lat,
                "end_longitude": d.last_trip.end_lon,
            }
            if d.last_trip
            else {}
        ),
    ),
    ToyotaSensorDescription(
        key="last_trip_end",
        translation_key="last_trip_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_trip("end"),
    ),
    ToyotaSensorDescription(
        key="active_geofences",
        translation_key="active_geofences",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:map-marker-radius",
        value_fn=_active_geofences,
        attrs_fn=lambda d: {
            "geofences": [
                {
                    "name": g.name,
                    "active": g.active,
                    "latitude": g.latitude,
                    "longitude": g.longitude,
                    "radius_m": g.radius,
                    "direction": g.direction,
                }
                for g in d.geofences
            ]
        },
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ToyotaConfigEntry, add: AddEntitiesCallback) -> None:
    co = entry.runtime_data
    resolve = entry.options.get(CONF_RESOLVE_ADDRESS, DEFAULT_RESOLVE_ADDRESS)
    add(
        ToyotaSensor(co, d.vehicle, desc)
        for d in co.data.values()
        for desc in SENSORS
        if resolve or desc.key != "address"
    )


class ToyotaSensor(ToyotaEntity, SensorEntity):
    entity_description: ToyotaSensorDescription

    def __init__(self, coordinator, vehicle, description: ToyotaSensorDescription) -> None:
        super().__init__(coordinator, vehicle, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        d = self.vehicle_data
        return self.entity_description.value_fn(d) if d else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self.vehicle_data
        fn = self.entity_description.attrs_fn
        if not d or not fn:
            return None
        return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in fn(d).items()}
