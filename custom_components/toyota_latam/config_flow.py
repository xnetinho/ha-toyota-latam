"""Config flow: user, reauth, options."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import ToyotaAuthError, ToyotaError, ToyotaLatamClient
from .const import (
    CONF_ACTIVE_INTERVAL,
    CONF_PARKED_INTERVAL,
    CONF_RESOLVE_ADDRESS,
    DEFAULT_ACTIVE_INTERVAL,
    DEFAULT_PARKED_INTERVAL,
    DEFAULT_RESOLVE_ADDRESS,
    DOMAIN,
    MAX_INTERVAL,
    MIN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class ToyotaLatamConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, username: str, password: str) -> str | None:
        client = ToyotaLatamClient(async_create_clientsession(self.hass), username, password)
        try:
            await client.login()
            vehicles = await client.get_vehicles()
        except ToyotaAuthError:
            return "invalid_auth"
        except ToyotaError as err:
            _LOGGER.debug("Validation failed: %s", err)
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating Toyota LATAM account")
            return "unknown"
        return None if vehicles else "no_vehicles"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip().lower()
            await self.async_set_unique_id(username)
            self._abort_if_unique_id_configured()
            if err := await self._validate(username, user_input[CONF_PASSWORD]):
                errors["base"] = err
            else:
                return self.async_create_entry(
                    title=username, data={CONF_USERNAME: username, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        schema = vol.Schema({vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if err := await self._validate(entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]):
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ToyotaOptionsFlow()


class ToyotaOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = self.config_entry.options
        interval = vol.All(vol.Coerce(int), vol.Range(min=MIN_INTERVAL, max=MAX_INTERVAL))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ACTIVE_INTERVAL, default=o.get(CONF_ACTIVE_INTERVAL, DEFAULT_ACTIVE_INTERVAL)
                    ): interval,
                    vol.Required(
                        CONF_PARKED_INTERVAL, default=o.get(CONF_PARKED_INTERVAL, DEFAULT_PARKED_INTERVAL)
                    ): interval,
                    vol.Required(
                        CONF_RESOLVE_ADDRESS, default=o.get(CONF_RESOLVE_ADDRESS, DEFAULT_RESOLVE_ADDRESS)
                    ): bool,
                }
            ),
        )
