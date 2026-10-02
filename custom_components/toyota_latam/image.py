"""Vehicle picture."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import ToyotaConfigEntry
from .entity import ToyotaEntity


async def async_setup_entry(hass: HomeAssistant, entry: ToyotaConfigEntry, add: AddEntitiesCallback) -> None:
    co = entry.runtime_data
    add(ToyotaImage(co, d.vehicle, hass) for d in co.data.values() if d.vehicle.image)


class ToyotaImage(ToyotaEntity, ImageEntity):
    _attr_translation_key = "picture"
    _attr_content_type = "image/png"

    def __init__(self, coordinator, vehicle, hass: HomeAssistant) -> None:
        ToyotaEntity.__init__(self, coordinator, vehicle, "picture")
        ImageEntity.__init__(self, hass)
        self._attr_image_last_updated: datetime = dt_util.utcnow()

    async def async_image(self) -> bytes | None:
        d = self.vehicle_data
        return d.vehicle.image if d else None
