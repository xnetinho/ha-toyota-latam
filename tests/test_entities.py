from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.toyota_latam.api import ToyotaConnectionError

from .conftest import LOC_MOVING, VEHICLE
from .test_coordinator import setup


def _state(hass, domain, key):
    reg = er.async_get(hass)
    eid = reg.async_get_entity_id(domain, "toyota_latam", f"{VEHICLE.vin}_{key}")
    assert eid, key
    return hass.states.get(eid)


async def test_entities(hass, entry, mock_client):
    await setup(hass, entry)
    assert _state(hass, "sensor", "fuel_level").state == "84"
    assert _state(hass, "sensor", "odometer").state == "89"
    t = _state(hass, "sensor", "last_trip_distance")
    assert t.state == "5.0" and t.attributes["fuel_start"] == 90.0
    assert _state(hass, "sensor", "active_geofences").attributes["geofences"][0]["name"] == "Casa"
    assert _state(hass, "binary_sensor", "moving").state == "off"
    assert _state(hass, "binary_sensor", "stolen_tracking").state == "off"
    tr = _state(hass, "device_tracker", "location")
    assert tr.attributes["latitude"] == -23.55 and tr.attributes["event_type"] == "IG-OFF"
    dev = dr.async_get(hass).async_get_device(identifiers={("toyota_latam", VEHICLE.vin)})
    assert dev.name == "Corolla Cross TST1A23" and dev.manufacturer == "Toyota"


async def test_moving_and_refresh_button(hass, entry, mock_client):
    co = await setup(hass, entry)
    mock_client.get_location.return_value = LOC_MOVING
    eid = er.async_get(hass).async_get_entity_id("button", "toyota_latam", f"{VEHICLE.vin}_refresh")
    await hass.services.async_call("button", "press", {"entity_id": eid}, blocking=True)
    await hass.async_block_till_done()
    assert _state(hass, "binary_sensor", "moving").state == "on"
    assert _state(hass, "binary_sensor", "ignition").state == "on"
    assert co.last_update_success


async def test_unavailable_after_repeated_failures(hass, entry, mock_client):
    co = await setup(hass, entry)
    mock_client.get_location.side_effect = ToyotaConnectionError("x")
    mock_client.get_telemetry.side_effect = ToyotaConnectionError("x")
    for _ in range(3):
        await co.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", "fuel_level").state == "unavailable"


async def test_diagnostics_redacted(hass, entry, mock_client):
    from custom_components.toyota_latam.diagnostics import async_get_config_entry_diagnostics

    await setup(hass, entry)
    out = str(await async_get_config_entry_diagnostics(hass, entry))
    for secret in ("pw", VEHICLE.vin, "TST1A23", "KEY", "-23.55"):
        assert secret not in out


async def test_address_and_maps_key_sensors(hass, entry, mock_client):
    await setup(hass, entry)
    assert _state(hass, "sensor", "address").state == "Rua X, 1"
    reg = er.async_get(hass)
    eid = reg.async_get_entity_id("sensor", "toyota_latam", f"{VEHICLE.vin}_maps_key")
    assert reg.async_get(eid).disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_no_address_sensor_when_option_off(hass, entry, mock_client):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={"resolve_address": False})
    await setup(hass, entry)
    assert er.async_get(hass).async_get_entity_id("sensor", "toyota_latam", f"{VEHICLE.vin}_address") is None
    mock_client.reverse_geocode.assert_not_called()


async def test_long_address_keeps_full_text_in_attribute(hass, entry, mock_client):
    mock_client.reverse_geocode.return_value = "R" * 300
    await setup(hass, entry)
    st = _state(hass, "sensor", "address")
    assert len(st.state) == 255 and st.attributes["full_address"] == "R" * 300


async def test_color_plate_score_services_problem(hass, entry, mock_client):
    await setup(hass, entry)
    assert _state(hass, "sensor", "color").state == "Black"
    assert _state(hass, "sensor", "plate").state == "TST1A23"
    sc = _state(hass, "sensor", "driving_score")
    assert sc.state == "1850" and sc.attributes["level_max_points"] == 2999
    assert _state(hass, "sensor", "driving_level").state == "1"
    assert _state(hass, "sensor", "available_services").state == "1"
    pb = _state(hass, "binary_sensor", "problem")
    assert pb.state == "off" and pb.attributes["problems"] == []


async def test_image_entity_and_tracker_picture(hass, entry, mock_client):
    await setup(hass, entry)
    eid = er.async_get(hass).async_get_entity_id("image", "toyota_latam", f"{VEHICLE.vin}_picture")
    assert eid
    ent = hass.data["image"].get_entity(eid)
    assert (await ent.async_image()).startswith(b"\x89PNG") and ent.content_type == "image/png"
    tr = _state(hass, "device_tracker", "location")
    assert tr.attributes["entity_picture"] == f"/api/image_proxy/{eid}"


async def test_no_image_entity_without_picture(hass, entry, mock_client):
    from dataclasses import replace

    mock_client.get_vehicles.return_value = [replace(VEHICLE, image=None)]
    await setup(hass, entry)
    assert er.async_get(hass).async_get_entity_id("image", "toyota_latam", f"{VEHICLE.vin}_picture") is None
    assert "entity_picture" not in _state(hass, "device_tracker", "location").attributes


async def test_optional_endpoint_failure_does_not_affect_core(hass, entry, mock_client):
    for m in (mock_client.get_driving_score, mock_client.get_diagnostics, mock_client.get_services):
        m.side_effect = ToyotaConnectionError("nope")
    co = await setup(hass, entry)
    assert co.last_update_success and not co.data[VEHICLE.vin].stale
    assert _state(hass, "sensor", "fuel_level").state == "84"
    assert _state(hass, "sensor", "driving_score").state == "unknown"
