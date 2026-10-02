"""Device tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ToyotaConfigEntry
from .const import DOMAIN
from .entity import ToyotaEntity


async def async_setup_entry(hass: HomeAssistant, entry: ToyotaConfigEntry, add: AddEntitiesCallback) -> None:
    co = entry.runtime_data
    add(ToyotaTracker(co, d.vehicle, "location") for d in co.data.values())


class ToyotaTracker(ToyotaEntity, TrackerEntity):
    _attr_translation_key = "location"
    _attr_name = None
    _attr_source_type = SourceType.GPS

    @property
    def available(self) -> bool:
        d = self.vehicle_data
        return super().available and d.location is not None and d.location.latitude is not None

    @property
    def entity_picture(self) -> str | None:
        d = self.vehicle_data
        if not d or not d.vehicle.image:
            return None
        return f"/api/image_proxy/{self._image_entity_id}" if self._image_entity_id else None

    @property
    def _image_entity_id(self) -> str | None:
        from homeassistant.helpers import entity_registry as er

        return er.async_get(self.hass).async_get_entity_id("image", DOMAIN, f"{self.vin}_picture")

    @property
    def latitude(self) -> float | None:
        d = self.vehicle_data
        return d.location.latitude if d and d.location else None

    @property
    def longitude(self) -> float | None:
        d = self.vehicle_data
        return d.location.longitude if d and d.location else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.vehicle_data
        if not d or not d.location:
            return {}
        attrs: dict[str, Any] = {"event_type": d.location.event_type, "stale": d.stale}
        if d.address:
            attrs["address"] = d.address
        return attrs
