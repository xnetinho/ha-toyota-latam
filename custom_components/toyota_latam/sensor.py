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
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ToyotaConfigEntry
from .const import CONF_RESOLVE_ADDRESS, DEFAULT_RESOLVE_ADDRESS
from .coordinator import VehicleData
from .entity import ToyotaEntity, add_dynamic


@dataclass(frozen=True, kw_only=True)
class ToyotaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[VehicleData], Any]
    attrs_fn: Callable[[VehicleData], dict[str, Any]] | None = None
    dynamic: bool = False


def _tele(attr: str):
    return lambda d: getattr(d.telemetry, attr) if d.telemetry else None


def _trip(attr: str):
    return lambda d: getattr(d.last_trip, attr) if d.last_trip else None


def _ev(attr: str):
    return lambda d: getattr(d.event, attr) or None


def _alert(fn):
    return lambda d: fn(d.alerts) if d.alerts else None


def _active_geofences(d: VehicleData) -> int | None:
    return sum(g.active for g in d.geofences.fences) if d.geofences.fences or d.geofences.breaks else None


def _unread_breaks(d: VehicleData) -> int:
    return sum(b.unread for b in d.geofences.breaks)


def _latest_break(d: VehicleData):
    return max(d.geofences.breaks, key=lambda b: b.at.timestamp() if b.at else 0, default=None)


def _ticket_attrs(tickets) -> dict[str, Any]:
    return {
        "tickets": [
            {
                "id": t.ticket_id,
                "category": t.category,
                "type": t.service_type,
                "service_status": t.service_status,
                "ticket_status": t.ticket_status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in tickets
        ]
    }


def _score(attr: str):
    return lambda d: getattr(d.score, attr) if d.score else None


SENSORS: tuple[ToyotaSensorDescription, ...] = (
    ToyotaSensorDescription(
        key="color",
        translation_key="color",
        icon="mdi:palette",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.vehicle.color,
    ),
    ToyotaSensorDescription(
        key="plate",
        translation_key="plate",
        icon="mdi:car-esp",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.vehicle.plate,
    ),
    ToyotaSensorDescription(
        key="driving_score",
        translation_key="driving_score",
        icon="mdi:speedometer",
        native_unit_of_measurement="pts",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_score("points"),
        attrs_fn=lambda d: (
            {
                "level": d.score.level,
                "level_points": d.score.level_points,
                "level_min_points": d.score.level_min_points,
                "level_max_points": d.score.level_max_points,
                "speed_badges": d.score.speed_badges,
                "acceleration_badges": d.score.acceleration_badges,
                "rpm_badges": d.score.rpm_badges,
            }
            if d.score
            else {}
        ),
    ),
    ToyotaSensorDescription(
        key="driving_level",
        translation_key="driving_level",
        icon="mdi:stairs-up",
        value_fn=_score("level"),
    ),
    ToyotaSensorDescription(
        key="available_services",
        translation_key="available_services",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:cloud-check",
        value_fn=lambda d: sum(d.services.flags.values()) if d.services else None,
        attrs_fn=lambda d: dict(sorted(d.services.flags.items())) if d.services else {},
    ),
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
                for g in d.geofences.fences
            ]
        },
    ),
    ToyotaSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        dynamic=True,
        value_fn=_ev("vehicle_speed"),
        attrs_fn=lambda d: {"samples": d.event.speed_samples},
    ),
    ToyotaSensorDescription(
        key="engine_speed",
        translation_key="engine_speed",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:engine",
        dynamic=True,
        value_fn=_ev("engine_speed"),
    ),
    ToyotaSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        dynamic=True,
        value_fn=_ev("battery_voltage"),
    ),
    ToyotaSensorDescription(
        key="battery_status",
        translation_key="battery_status",
        icon="mdi:car-battery",
        dynamic=True,
        value_fn=_ev("battery_status"),
    ),
    ToyotaSensorDescription(
        key="fuel_remaining",
        translation_key="fuel_remaining",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        dynamic=True,
        value_fn=_ev("fuel_remaining"),
    ),
    ToyotaSensorDescription(
        key="mileage",
        translation_key="mileage",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        dynamic=True,
        value_fn=_ev("mileage"),
    ),
    ToyotaSensorDescription(
        key="vehicle_status",
        translation_key="vehicle_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:car-info",
        dynamic=True,
        value_fn=_ev("status"),
        attrs_fn=lambda d: {"record_type": d.event.record_type},
    ),
    ToyotaSensorDescription(
        key="heading",
        translation_key="heading",
        icon="mdi:compass",
        dynamic=True,
        value_fn=_ev("heading"),
    ),
    ToyotaSensorDescription(
        key="dtc_codes",
        translation_key="dtc_codes",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:alert-circle-outline",
        dynamic=True,
        value_fn=lambda d: len(d.event.dtc) or None,
        attrs_fn=lambda d: {"codes": list(d.event.dtc)},
    ),
    ToyotaSensorDescription(
        key="last_trip_speed_limit",
        translation_key="last_trip_speed_limit",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        dynamic=True,
        value_fn=lambda d: (d.last_trip.speed_limit or None) if d.last_trip else None,
        attrs_fn=lambda d: {"status": d.last_trip.speed_alert_status} if d.last_trip else {},
    ),
    ToyotaSensorDescription(
        key="speed_alert_limit",
        translation_key="speed_alert_limit",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        dynamic=True,
        value_fn=_alert(lambda a: (a.speed_alert.limit or None) if a.speed_alert else None),
        attrs_fn=lambda d: (
            {
                "name": d.alerts.speed_alert.name,
                "frequency": d.alerts.speed_alert.frequency,
                "status": d.alerts.speed_alert.status,
            }
            if d.alerts and d.alerts.speed_alert
            else {}
        ),
    ),
    ToyotaSensorDescription(
        key="tracking_tickets",
        translation_key="tracking_tickets",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:shield-car",
        dynamic=True,
        value_fn=_alert(lambda a: len(a.tracking_tickets) or None),
        attrs_fn=lambda d: _ticket_attrs(d.alerts.tracking_tickets) if d.alerts else {},
    ),
    ToyotaSensorDescription(
        key="assistance_tickets",
        translation_key="assistance_tickets",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:car-emergency",
        dynamic=True,
        value_fn=_alert(lambda a: len(a.assistance_tickets) or None),
        attrs_fn=lambda d: _ticket_attrs(d.alerts.assistance_tickets) if d.alerts else {},
    ),
    ToyotaSensorDescription(
        key="ecall_tickets",
        translation_key="ecall_tickets",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:phone-alert",
        dynamic=True,
        value_fn=_alert(lambda a: len(a.ecall_tickets) or None),
        attrs_fn=lambda d: _ticket_attrs(d.alerts.ecall_tickets) if d.alerts else {},
    ),
    ToyotaSensorDescription(
        key="alarm_status",
        translation_key="alarm_status",
        icon="mdi:alarm-light",
        dynamic=True,
        value_fn=_alert(lambda a: a.alarm.status if a.alarm else None),
        attrs_fn=lambda d: (
            {
                "notified": d.alerts.alarm.notified,
                "start": d.alerts.alarm.start.isoformat() if d.alerts.alarm.start else None,
                "end": d.alerts.alarm.end.isoformat() if d.alerts.alarm.end else None,
                "latitude": d.alerts.alarm.latitude,
                "longitude": d.alerts.alarm.longitude,
            }
            if d.alerts and d.alerts.alarm
            else {}
        ),
    ),
    ToyotaSensorDescription(
        key="geofence_breaks",
        translation_key="geofence_breaks",
        icon="mdi:map-marker-alert",
        dynamic=True,
        value_fn=lambda d: _unread_breaks(d) if d.geofences.breaks else None,
        attrs_fn=lambda d: {
            "breaks": [
                {
                    "name": b.name,
                    "at": b.at.isoformat() if b.at else None,
                    "direction": b.direction,
                    "unread": b.unread,
                    "latitude": b.latitude,
                    "longitude": b.longitude,
                    "radius_m": b.radius,
                }
                for b in d.geofences.breaks
            ]
        },
    ),
    ToyotaSensorDescription(
        key="last_geofence_break",
        translation_key="last_geofence_break",
        device_class=SensorDeviceClass.TIMESTAMP,
        dynamic=True,
        value_fn=lambda d: b.at if (b := _latest_break(d)) else None,
        attrs_fn=lambda d: {"name": b.name, "direction": b.direction} if (b := _latest_break(d)) else {},
    ),
    ToyotaSensorDescription(
        key="registered_at",
        translation_key="registered_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.vehicle.registered_at,
    ),
)


def _present(entry: ToyotaConfigEntry):
    resolve = entry.options.get(CONF_RESOLVE_ADDRESS, DEFAULT_RESOLVE_ADDRESS)

    def present(d: VehicleData, desc: ToyotaSensorDescription) -> bool:
        if desc.key == "address" and not resolve:
            return False
        return not desc.dynamic or desc.value_fn(d) is not None

    return present


async def async_setup_entry(hass: HomeAssistant, entry: ToyotaConfigEntry, add: AddEntitiesCallback) -> None:
    co = entry.runtime_data
    add_dynamic(co, entry, add, SENSORS, lambda v, desc: ToyotaSensor(co, v, desc), _present(entry))


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
