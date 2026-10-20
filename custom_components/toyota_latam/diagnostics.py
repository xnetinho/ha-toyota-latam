"""Diagnostics (redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ToyotaConfigEntry

TO_REDACT = {
    "username",
    "password",
    "vin",
    "car_id",
    "plate",
    "latitude",
    "longitude",
    "maps_key",
    "address",
    "start_lat",
    "start_lon",
    "end_lat",
    "end_lon",
    "place_id",
    "nickname",
    "name",
    "image",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ToyotaConfigEntry) -> dict[str, Any]:
    co = entry.runtime_data
    vehicles = []
    for d in co.data.values():
        v = asdict(d)
        if "vehicle" in v and isinstance(v["vehicle"], dict):
            v["vehicle"].pop("image", None)
        vehicles.append(v | {"trips": len(d.trips)})
    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "options": dict(entry.options)},
            "update_interval_s": co.update_interval.total_seconds() if co.update_interval else None,
            "last_update_success": co.last_update_success,
            "vehicles": vehicles,
        },
        TO_REDACT,
    )
