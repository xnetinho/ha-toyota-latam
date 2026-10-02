"""Refresh button."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ToyotaConfigEntry
from .entity import ToyotaEntity


async def async_setup_entry(hass: HomeAssistant, entry: ToyotaConfigEntry, add: AddEntitiesCallback) -> None:
    co = entry.runtime_data
    add(ToyotaRefreshButton(co, d.vehicle, "refresh") for d in co.data.values())


class ToyotaRefreshButton(ToyotaEntity, ButtonEntity):
    _attr_translation_key = "refresh"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
