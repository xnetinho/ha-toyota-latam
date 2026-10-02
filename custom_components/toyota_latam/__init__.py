"""Toyota LATAM Connected Services."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import ToyotaLatamClient
from .coordinator import ToyotaCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.DEVICE_TRACKER, Platform.IMAGE, Platform.SENSOR]
IMAGE_FIRST = [Platform.IMAGE]
REST = [p for p in PLATFORMS if p not in IMAGE_FIRST]

type ToyotaConfigEntry = ConfigEntry[ToyotaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ToyotaConfigEntry) -> bool:
    client = ToyotaLatamClient(async_create_clientsession(hass), entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = ToyotaCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, IMAGE_FIRST)
    await hass.config_entries.async_forward_entry_setups(entry, REST)
    return True


async def _reload(hass: HomeAssistant, entry: ToyotaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ToyotaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
