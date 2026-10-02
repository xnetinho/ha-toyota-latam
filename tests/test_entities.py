from dataclasses import replace

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

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


def _rich_mocks(mock_client):
    from custom_components.toyota_latam.api import (
        Alarm,
        Alerts,
        CarEvent,
        Diagnostics,
        GeofenceBreak,
        GeofenceData,
        Problem,
        SpeedAlert,
        Ticket,
    )

    from .conftest import GEOFENCE, LOC_PARKED, TELE

    ev = CarEvent(
        vehicle_speed=42.5, engine_speed=2100.0, battery_voltage=12.6, battery_status="OK", fuel_remaining=35.5
    )
    ev2 = CarEvent(mileage=1234.0, status="Running", dtc=("P0420",), heading="NE")
    mock_client.get_location.return_value = replace(LOC_PARKED, event=ev)
    mock_client.get_telemetry.return_value = replace(TELE, event=ev2)
    mock_client.get_diagnostics.return_value = Diagnostics(1, ("Cat",), (Problem("Cat", None, "High", "P0420"),))
    mock_client.get_geofences.return_value = GeofenceData(
        (GEOFENCE,), (GeofenceBreak("Casa", dt_util.utcnow(), "Out", True, 1.0, 2.0, 100.0),)
    )
    mock_client.get_alerts.return_value = Alerts(
        speed_alert=SpeedAlert("Max", 110.0, "Daily", "On"),
        tracking_tickets=(Ticket("T1", 1, 1, "Track", None, None, None, None),),
        ecall_tickets=(Ticket("E1", 1, 1, "Call", None, None, None, None),),
        alarm=Alarm("Triggered", "Y", None, None, None, None),
    )


async def test_fields_empty_on_this_model_get_no_entity(hass, entry, mock_client):
    await setup(hass, entry)
    reg = er.async_get(hass)
    for key in ("speed", "engine_speed", "battery_voltage", "dtc_codes", "alarm_status", "geofence_breaks"):
        assert reg.async_get_entity_id("sensor", "toyota_latam", f"{VEHICLE.vin}_{key}") is None, key
    assert reg.async_get_entity_id("binary_sensor", "toyota_latam", f"{VEHICLE.vin}_geofence_break_unread") is None


async def test_richer_model_gets_all_extra_entities(hass, entry, mock_client):
    _rich_mocks(mock_client)
    await setup(hass, entry)
    assert _state(hass, "sensor", "speed").state == "42.5"
    assert _state(hass, "sensor", "engine_speed").state == "2100.0"
    assert _state(hass, "sensor", "battery_voltage").state == "12.6"
    assert _state(hass, "sensor", "battery_status").state == "OK"
    assert _state(hass, "sensor", "fuel_remaining").state == "35.5"
    assert _state(hass, "sensor", "mileage").state == "1234.0"
    assert _state(hass, "sensor", "vehicle_status").state == "Running"
    assert _state(hass, "sensor", "heading").state == "NE"
    dtc = _state(hass, "sensor", "dtc_codes")
    assert dtc.state == "1" and dtc.attributes["codes"] == ["P0420"]
    assert _state(hass, "sensor", "speed_alert_limit").state == "110.0"
    assert _state(hass, "binary_sensor", "speed_alert_enabled").state == "on"
    assert _state(hass, "sensor", "tracking_tickets").attributes["tickets"][0]["id"] == "T1"
    assert _state(hass, "sensor", "ecall_tickets").state == "1"
    assert _state(hass, "sensor", "alarm_status").state == "Triggered"
    br = _state(hass, "sensor", "geofence_breaks")
    assert br.state == "1" and br.attributes["breaks"][0]["direction"] == "Out"
    assert _state(hass, "binary_sensor", "geofence_break_unread").state == "on"
    assert _state(hass, "sensor", "last_geofence_break").state != "unknown"
    assert _state(hass, "binary_sensor", "problem").attributes["problems"] == ["Cat"]


async def test_entity_appears_later_when_value_first_arrives(hass, entry, mock_client):
    co = await setup(hass, entry)
    reg = er.async_get(hass)
    assert reg.async_get_entity_id("sensor", "toyota_latam", f"{VEHICLE.vin}_speed") is None
    _rich_mocks(mock_client)
    await co.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", "speed").state == "42.5"


async def test_address_from_api_event_skips_google(hass, entry, mock_client):
    from custom_components.toyota_latam.api import CarEvent

    from .conftest import LOC_PARKED

    mock_client.get_location.return_value = replace(LOC_PARKED, event=CarEvent(address="Rua da API, 9"))
    await setup(hass, entry)
    assert _state(hass, "sensor", "address").state == "Rua da API, 9"
    mock_client.reverse_geocode.assert_not_called()
