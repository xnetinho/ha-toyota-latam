from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.toyota_latam.api import ToyotaAuthError, ToyotaConnectionError

from .conftest import LOC_MOVING, VEHICLE


async def setup(hass, entry):
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


async def test_parked_interval_and_data(hass, entry, mock_client):
    co = await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    d = co.data[VEHICLE.vin]
    assert d.telemetry.fuel_percent == 84 and d.last_trip.distance == 5.0 and d.geofences.fences[0].name == "Casa"
    assert co.update_interval == timedelta(seconds=300)


async def test_active_interval_and_trip_refetch_on_stop(hass, entry, mock_client):
    co = await setup(hass, entry)
    mock_client.get_location.return_value = LOC_MOVING
    await co.async_refresh()
    assert co.update_interval == timedelta(seconds=30)
    n = mock_client.get_trips.call_count
    mock_client.get_location.return_value = co.data[VEHICLE.vin].location.__class__(-23.0, -46.0, "IG-OFF", "02")
    await co.async_refresh()
    assert mock_client.get_trips.call_count == n + 1


async def test_stale_then_unavailable_with_backoff(hass, entry, mock_client):
    co = await setup(hass, entry)
    for m in (mock_client.get_location, mock_client.get_telemetry):
        m.side_effect = ToyotaConnectionError("down")
    await co.async_refresh()
    assert co.last_update_success and co.data[VEHICLE.vin].stale
    assert co.data[VEHICLE.vin].telemetry.fuel_percent == 84
    await co.async_refresh()
    assert co.last_update_success
    await co.async_refresh()
    assert not co.last_update_success
    assert co.update_interval == timedelta(seconds=900)
    for m in (mock_client.get_location, mock_client.get_telemetry):
        m.side_effect = None
    mock_client.get_location.return_value = LOC_MOVING
    mock_client.get_telemetry.return_value = co.data[VEHICLE.vin].telemetry
    await co.async_refresh()
    assert co.last_update_success and not co.data[VEHICLE.vin].stale


async def test_partial_failure_keeps_other_data(hass, entry, mock_client):
    co = await setup(hass, entry)
    mock_client.get_telemetry.side_effect = ToyotaConnectionError("x")
    await co.async_refresh()
    d = co.data[VEHICLE.vin]
    assert co.last_update_success and not d.stale and d.telemetry.fuel_percent == 84


async def test_auth_failure_starts_reauth(hass, entry, mock_client):
    co = await setup(hass, entry)
    mock_client.get_location.side_effect = ToyotaAuthError("bad")
    await co.async_refresh()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_first_refresh_auth_error_sets_reauth(hass, entry, mock_client):
    mock_client.get_vehicles.side_effect = ToyotaAuthError("bad")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_address_opt_in_and_cache(hass, entry, mock_client):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={"resolve_address": True})
    co = await setup(hass, entry)
    assert co.data[VEHICLE.vin].address == "Rua X, 1"
    await co.async_refresh()
    assert mock_client.reverse_geocode.call_count == 1
