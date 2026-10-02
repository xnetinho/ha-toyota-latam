from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.toyota_latam.api import ToyotaAuthError, ToyotaConnectionError
from custom_components.toyota_latam.const import DOMAIN

from .conftest import VEHICLE

CLIENT = "custom_components.toyota_latam.config_flow.ToyotaLatamClient"
INPUT = {"username": " A@B.c ", "password": "pw"}


async def _start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_user_ok(hass):
    r = await _start(hass)
    with (
        patch(CLIENT, autospec=True) as c,
        patch("custom_components.toyota_latam.async_setup_entry", return_value=True),
    ):
        c.return_value.login.return_value = None
        c.return_value.get_vehicles.return_value = [VEHICLE]
        r = await hass.config_entries.flow.async_configure(r["flow_id"], INPUT)
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"] == {"username": "a@b.c", "password": "pw"}


async def test_user_errors_then_recover(hass):
    r = await _start(hass)
    for exc, key in ((ToyotaAuthError("x"), "invalid_auth"), (ToyotaConnectionError("x"), "cannot_connect")):
        with patch(CLIENT, autospec=True) as c:
            c.return_value.login.side_effect = exc
            r = await hass.config_entries.flow.async_configure(r["flow_id"], INPUT)
        assert r["type"] is FlowResultType.FORM and r["errors"] == {"base": key}
    with patch(CLIENT, autospec=True) as c:
        c.return_value.get_vehicles.return_value = []
        r = await hass.config_entries.flow.async_configure(r["flow_id"], INPUT)
    assert r["errors"] == {"base": "no_vehicles"}


async def test_already_configured(hass, entry):
    entry.add_to_hass(hass)
    r = await _start(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"username": "a@b.c", "password": "pw"})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_reauth(hass, entry):
    entry.add_to_hass(hass)
    r = await entry.start_reauth_flow(hass)
    assert r["step_id"] == "reauth_confirm"
    with (
        patch(CLIENT, autospec=True) as c,
        patch("custom_components.toyota_latam.async_setup_entry", return_value=True),
    ):
        c.return_value.get_vehicles.return_value = [VEHICLE]
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"password": "new"})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"


async def test_options(hass, entry):
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {"active_interval": 20, "parked_interval": 600, "resolve_address": True}
    )
    assert r["type"] is FlowResultType.CREATE_ENTRY and entry.options["parked_interval"] == 600
