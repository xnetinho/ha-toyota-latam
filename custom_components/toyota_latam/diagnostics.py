"""Diagnostics (redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ToyotaConfigEntry

TO_REDACT = {
    "username", "password", "vin", "car_id", "plate", "latitude", "longitude", "maps_key", "address",
    "start_lat", "start_lon", "end_lat", "end_lon",
}  # fmt: skip


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ToyotaConfigEntry) -> dict[str, Any]:
    co = entry.runtime_data
    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "options": dict(entry.options)},
            "update_interval_s": co.update_interval.total_seconds() if co.update_interval else None,
            "last_update_success": co.last_update_success,
            "vehicles": [asdict(d) | {"trips": len(d.trips)} for d in co.data.values()],
        },
        TO_REDACT,
    )
