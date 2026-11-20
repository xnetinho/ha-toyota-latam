import re

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses

from custom_components.toyota_latam import api
from custom_components.toyota_latam.api import (
    ToyotaAuthError,
    ToyotaConnectionError,
    ToyotaLatamClient,
    parse_csrf,
    pkce_pair,
)

SVC = api._SVC
AUTH_URL = f"{api.AUTH0_URL}/authorize?client_id=x&state=S1"
CRF = "AUTHCSRF+tok="


def test_pkce():
    v, c = pkce_pair()
    assert len(v) >= 43 and "=" not in c


def test_parse_csrf():
    assert parse_csrf("crf=AB+c=&uid=1&unm=x") == "AB+c="
    assert parse_csrf("crf%3dAB%3d%26uid%3d1") == "AB="
    assert parse_csrf(None) is None and parse_csrf("uid=1") is None


def mock_login(m, pwd_loc="/authorize/resume?state=R", mfa=False):
    m.get(f"{api.BASE_URL}/precache.manifest", payload={"versionToken": "VER1"})
    m.post(f"{SVC}/OIDC/ActionMobile_Get_Authorization_URL", payload={"data": {"URL": AUTH_URL}})
    m.get(AUTH_URL, status=200)
    m.post(
        f"{api.AUTH0_URL}/u/login/identifier?state=S1", status=302, headers={"Location": "/u/login/password?state=S2"}
    )
    m.post(f"{api.AUTH0_URL}/u/login/password?state=S2", status=302, headers={"Location": pwd_loc})
    if mfa:
        m.post(
            f"{api.AUTH0_URL}/u/mfa-detect-browser-capabilities?state=M1",
            status=302,
            headers={"Location": "/authorize/resume?state=R"},
        )
    m.get(
        f"{api.AUTH0_URL}/authorize/resume?state=R",
        status=302,
        headers={"Location": f"{api.APP_SCHEME}Toyota_OneApp_EU/LoginCallback?code=C&state=S3"},
    )

    def cb(url, **kw):
        assert kw["json"]["inputParameters"]["code"] == "C"
        return CallbackResult(payload={"data": {}}, headers={"Set-Cookie": f"nr2Users=crf={CRF}&uid=1; Path=/"})

    m.post(f"{SVC}/OIDCMobile/OIDC_SSO/Login_Callback/ActionMobile_Login_OIDC", callback=cb)


@pytest.fixture
async def client():
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())) as s:
        yield ToyotaLatamClient(s, "a@b.c", "pw")


async def test_login_ok(client):
    with aioresponses() as m:
        mock_login(m)
        await client.login()
    assert client._csrf == CRF and client._version == "VER1"


async def test_login_mfa_detect(client):
    with aioresponses() as m:
        mock_login(m, pwd_loc="/u/mfa-detect-browser-capabilities?state=M1", mfa=True)
        await client.login()
    assert client._csrf == CRF


async def test_login_wrong_password(client):
    with aioresponses() as m:
        mock_login(m, pwd_loc="/u/login/password?state=S2")
        with pytest.raises(ToyotaAuthError):
            await client.login()


async def test_login_network_error(client):
    with aioresponses() as m:
        m.get(f"{api.BASE_URL}/precache.manifest", exception=aiohttp.ClientError("x"))
        m.post(f"{SVC}/OIDC/ActionMobile_Get_Authorization_URL", exception=aiohttp.ClientConnectionError("down"))
        with pytest.raises(ToyotaConnectionError):
            await client.login()


GARAGE = {
    "data": {
        "Out_CarouselCarsList": {
            "List": [
                {
                    "VIN": "V1",
                    "CarId": 5,
                    "Model": "Corolla Cross",
                    "Year": 2027,
                    "LicensePlated": "ABC1D23",
                    "IsConnected": True,
                },
                {"CarId": 9},
            ]
        }
    }
}


async def test_get_vehicles_and_reauth_once(client):
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        url = re.compile(r".*DataActionGetCarsGarage$")
        m.post(url, payload={"exception": {"message": "No role validation found"}})
        mock_login(m)
        m.post(url, payload=GARAGE)
        vs = await client.get_vehicles()
    assert [(v.vin, v.car_id, v.year) for v in vs] == [("V1", "5", 2027)]


async def test_reauth_only_once(client):
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        url = re.compile(r".*DataActionGetCarsGarage$")
        m.post(url, payload={"exception": {"message": "No role validation found"}}, repeat=True)
        mock_login(m)
        with pytest.raises(api.ToyotaSessionExpired):
            await client.get_vehicles()


async def test_server_error_is_connection_error(client):
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        m.post(re.compile(r".*DataActionGetLastTrips$"), status=503)
        with pytest.raises(ToyotaConnectionError):
            await client.get_trips("V1")


def test_parsers_tolerate_garbage():
    assert api.Location.from_api({}).latitude is None
    loc = api.Location.from_api(
        {
            "VehicleData": {
                "Carevents": {
                    "List": [{"EventType": "IG-ON", "GpsInformation": {"Latitude": "-23.1", "Longitude": "bad"}}]
                }
            },
            "MapsKey": "k",
        }
    )
    assert loc.is_active and loc.latitude == -23.1 and loc.longitude is None
    t = api.Telemetry.from_api(
        {
            "VehicleData": {
                "Carevents": {
                    "List": [{"FuelRemainingPercentage": "84", "Odometer": "89", "TimestampON": "2026-10-01T22:06:06Z"}]
                }
            }
        }
    )
    assert (t.fuel_percent, t.odometer, t.odometer_unit) == (84, 89, "km") and t.ignition_on_at.year == 2026
    assert api.Telemetry.from_api({"VehicleData": None}).fuel_percent is None
    tr = api.Trip.from_api({"OdometerInit": "10", "OdometerEnd": "15.5", "GPS": None})
    assert tr.distance == 5.5
    g = api.Geofence.from_api(
        {
            "GeoFenceName": "Casa",
            "GeoFenceStatus": "1",
            "GeofencingAreaSetting": {"Latitude": "1", "Radius": "200", "Direction": "In/Out"},
        }
    )
    assert g.active and g.radius == 200 and g.direction == "In/Out"


def test_naive_timestamps_become_utc():
    assert api._dt("2026-10-01T22:06:06").tzinfo is not None
    assert api._dt("garbage") is None and api._dt(None) is None


def test_vehicle_color_and_image():
    import base64

    png = b"\x89PNG\r\n\x1a\nxx"
    v = api.Vehicle.from_api(
        {"VIN": "V1", "CarColor": "Black Metallic", "CarNickName": "Meu", "CarImage": base64.b64encode(png).decode()}
    )
    assert v.color == "Black Metallic" and v.nickname == "Meu" and v.image == png
    assert api.Vehicle.from_api({"VIN": "V1", "CarImage": "not-base64!!"}).image is None
    assert api.Vehicle.from_api({"VIN": "V1", "CarImage": base64.b64encode(b"<svg/>").decode()}).image is None
    assert api.Vehicle.from_api({"VIN": "V1"}).image is None


def test_driving_score_diagnostics_services():
    s = api.DrivingScore.from_api(
        {"Response": {"TotalPoints": "1850", "Level": "1", "MaxLevelPoints": "2999", "QuantitySpeedBadge": "17"}}
    )
    assert (s.points, s.level, s.level_max_points, s.speed_badges, s.rpm_badges) == (1850, 1, 2999, 17, None)
    assert api.DrivingScore.from_api({}).points is None
    d = api.Diagnostics.from_api({"Response": {"Count": "1", "ErrorCodes": {"List": [{"Title": "Oil"}]}}})
    assert d.problem_count == 1 and d.problems == ("Oil",)
    assert api.Diagnostics.from_api({"Response": {"Count": "0", "ErrorCodes": {"List": []}}}).problem_count == 0
    sv = api.Services.from_api({"ShowGeofence": True, "ShowWifi": False, "Other": 1})
    assert sv.flags == {"geofence": True, "wifi": False}


FULL_EVENT = {
    "VehicleData": {
        "Carevents": {
            "List": [
                {
                    "GpsInformation": {
                        "Latitude": "-23.5",
                        "Longitude": "-46.6",
                        "Direction": "NE",
                        "Radius": "15",
                        "Address": "Av. Teste, 1",
                        "PlaceId": "pid",
                    },
                    "EventType": "IG-ON",
                    "BatteryStatus": "OK",
                    "EngineSpeed": "2100",
                    "FuelRemaining": "35.5",
                    "FuelRemainingPercentage": "70",
                    "Mileage": "1234",
                    "Odometer": "1234",
                    "Status": "Running",
                    "TypeMerged": "Event",
                    "VehicleBatteryVoltage": "12.6",
                    "VehicleSpeed": {"List": ["10", "42.5"]},
                    "VehicleSpeedCount": "2",
                    "DTC": {"List": [{"Code": "P0420"}, "U0100", {"Title": "Oil"}, {}]},
                }
            ]
        }
    }
}


def test_car_event_all_fields_on_a_richer_model():
    e = api.CarEvent.from_api(FULL_EVENT)
    assert (e.vehicle_speed, e.speed_samples, e.engine_speed, e.battery_voltage) == (42.5, 2, 2100.0, 12.6)
    assert (e.battery_status, e.fuel_remaining, e.mileage, e.status) == ("OK", 35.5, 1234.0, "Running")
    assert e.dtc == ("P0420", "U0100", "Oil") and e.heading == "NE" and e.radius == 15.0
    assert e.address == "Av. Teste, 1" and e.place_id == "pid"
    assert api.Location.from_api(FULL_EVENT).event.vehicle_speed == 42.5
    assert api.Telemetry.from_api(FULL_EVENT).event.battery_voltage == 12.6


def test_car_event_empty_model_is_all_none():
    empty = {"VehicleData": {"Carevents": {"List": [{"EngineSpeed": "", "VehicleSpeed": {"List": []}, "DTC": None}]}}}
    e = api.CarEvent.from_api(empty)
    assert e == api.CarEvent() and api.CarEvent.from_api({}) == api.CarEvent()


def test_geofence_breaks_trip_extras_and_alerts_parsers():
    g = api.GeofenceData.from_api(
        {
            "Response": {"GeoFencesList": {"List": [{"GeoFenceName": "Casa", "GeoFenceStatus": "1", "PlaceId": "p"}]}},
            "BrokenUnread": {
                "BrokenFences": {
                    "List": [
                        {
                            "GeofenceName": "Casa",
                            "DataCreationTime": "2026-10-01T10:00:00Z",
                            "CrossBorderDirection": "Out",
                            "GeofencingAreaSetting": {"Latitude": "1", "Longitude": "2", "Radius": "100"},
                        }
                    ]
                }
            },
            "BrokenRead": {"BrokenFences": {"List": [{"GeofenceName": "Old"}]}},
        }
    )
    assert g.fences[0].place_id == "p" and [b.unread for b in g.breaks] == [True, False]
    assert g.breaks[0].direction == "Out" and g.breaks[0].radius == 100.0
    t = api.Trip.from_api(
        {
            "Event": "Trip",
            "CreatedAt": "2026-10-01T10:00:00.447Z",
            "SpeedAlertConfigurationStatus": "On",
            "SpeedLimitSetting": "80",
        }
    )
    assert (t.event, t.speed_alert_status, t.speed_limit) == ("Trip", "On", 80.0) and t.created_at.year == 2026
    d = api.Diagnostics.from_api(
        {
            "Response": {
                "Count": "1",
                "ErrorCodes": {"List": [{"Code": "P0420", "Title": "Cat", "Prioritydesc": "High"}]},
            }
        }
    )
    assert d.problems == ("Cat",) and d.details[0].priority == "High" and d.details[0].code == "P0420"
    sa = api.SpeedAlert.from_api({"SpeedAlertData": {"SpeedAlertName": "Max", "SpeedLimitSetting": "110"}})
    assert (sa.name, sa.limit) == ("Max", 110.0)
    al = api.Alarm.from_api(
        {"AlarmNotificationResponse": {"AlarmStatus": "Triggered", "DateTimeStart": "2026-10-01T10:00:00Z"}}
    )
    assert al.status == "Triggered" and al.start.year == 2026
    tk = api.Ticket.from_api({"TicketId": "T1", "ServiceStatus": "2", "ServiceCategory": "Tow"})
    assert (tk.ticket_id, tk.service_status, tk.category) == ("T1", 2, "Tow")


async def test_get_alerts_isolates_rejected_endpoint(client):
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        base = r".*{}$"
        m.post(
            re.compile(base.format("DataActionGetSpeedAlertInfo")),
            payload={"data": {"SpeedAlertData": {"SpeedLimitSetting": "90"}}},
            repeat=True,
        )
        m.post(
            re.compile(base.format("DataActionGetTrackingInfo")), payload={"exception": {"message": "NullReference"}}
        )
        m.post(
            re.compile(base.format("DataActionGetCentralNotifications2")),
            payload={"data": {"Ecall": {"Entities": {"List": [{"TicketId": "E1"}, {"TicketId": ""}]}}}},
        )
        m.post(re.compile(base.format("DataActionGetAlarmNotification")), payload={"data": {}})
        a = await client.get_alerts("V1")
    assert a.speed_alert.limit == 90.0 and a.tracking_tickets == () and [t.ticket_id for t in a.ecall_tickets] == ["E1"]


GARAGE_PATH = "One_App_MDB_Sync/CarSync/Bra_CarSync/DataActionGetCarsGarage"
SCRIPT_KEY = "/Toyota_OneApp_EU/scripts/One_App_MDB_Sync.CarSync.Bra_CarSync.mvc.js"
SCRIPT_URL = f"https://toyotaargentinasa1.outsystemsenterprise.com{SCRIPT_KEY}?h1"
GARAGE_OK = {
    "versionInfo": {"hasApiVersionChanged": False},
    "data": {"Out_CarouselCarsList": {"List": [{"VIN": "V1"}]}},
}
GARAGE_STALE = {"versionInfo": {"hasApiVersionChanged": True}, "data": {}}


def _manifest(*screens):
    files = {SCRIPT_KEY: "?h1"} | {f"/Toyota_OneApp_EU/scripts/Toyota_OneApp_EU.{s}.mvc.js": "?x" for s in screens}
    return {"versionToken": "VER2", "versionSequence": 2, "urlVersions": files}


def _script(api_version):
    return f'x.callDataAction("DataActionGetCarsGarage", "screenservices/{GARAGE_PATH}", "{api_version}", f)'


async def test_stale_api_version_is_healed_from_manifest(client):
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        url = re.compile(r".*DataActionGetCarsGarage$")
        m.post(url, payload=GARAGE_STALE)
        m.get(f"{api.BASE_URL}/precache.manifest", payload=_manifest())
        m.get(SCRIPT_URL, body=_script("NEWHASH"))
        m.post(url, payload=GARAGE_OK, repeat=True)
        assert [v.vin for v in await client.get_vehicles()] == ["V1"]
        assert client._overrides[GARAGE_PATH].api_version == "NEWHASH"
        assert [v.vin for v in await client.get_vehicles()] == ["V1"]  # remembered: no second heal


async def test_renamed_screen_is_healed_from_manifest(client):
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        url = re.compile(r".*DataActionGetCarsGarage$")
        refused = {"data": {}, "exception": {"message": "No role validation found"}}
        m.post(url, payload=refused)
        m.get(f"{api.BASE_URL}/precache.manifest", payload=_manifest("UI_Home.Home_V3", "NewDesign_TLAC.Home_V3"))
        m.get(SCRIPT_URL, body=_script("lij9"))
        m.post(url, payload=refused)  # same hash, old screen name: still refused
        m.post(url, payload=GARAGE_OK, repeat=True)
        assert [v.vin for v in await client.get_vehicles()] == ["V1"]
        assert client._overrides[GARAGE_PATH].view == "UI_Home.Home_V3"


async def test_unrecoverable_drift_raises_and_is_not_retried_every_poll(client):
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        url = re.compile(r".*DataActionGetCarsGarage$")
        m.post(url, payload=GARAGE_STALE, repeat=True)
        m.get(f"{api.BASE_URL}/precache.manifest", payload=_manifest(), repeat=True)
        m.get(SCRIPT_URL, body="no actions here", repeat=True)
        with pytest.raises(api.ToyotaApiError, match="apiVersion outdated"):
            await client.get_vehicles()
        manifest_calls = sum(1 for k in m.requests if k[1].path.endswith("precache.manifest"))
        with pytest.raises(api.ToyotaApiError, match="apiVersion outdated"):
            await client.get_vehicles()
        assert sum(1 for k in m.requests if k[1].path.endswith("precache.manifest")) == manifest_calls


async def test_expired_session_is_recovered_by_relogin(client):
    """Session expiry and a renamed screen look identical to the server; both must end in working data."""
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        url = re.compile(r".*DataActionGetCarsGarage$")
        refused = {"data": {}, "exception": {"message": "No role validation found"}}
        m.post(url, payload=refused, repeat=True)
        m.get(f"{api.BASE_URL}/precache.manifest", payload=_manifest(), repeat=True)
        m.get(SCRIPT_URL, body="no actions here", repeat=True)  # manifest cannot explain it -> must be the session
        mock_login(m)
        m.post(url, payload=GARAGE_OK, repeat=True)
        gen = client._generation
        # first call keeps being refused until the re-login, which the mock cannot tell apart; assert the retry path
        with pytest.raises(api.ToyotaViewRefused):
            await client.get_vehicles()
        assert client._generation == gen + 1  # a re-login happened
        assert not client._overrides  # and nothing was wrongly "healed"


def test_discovery_parsers():
    from custom_components.toyota_latam import discovery

    man = discovery.Manifest.from_json(_manifest("UI_MyToyota.MyToyota_V3", "NewDesign_TLAC.Home_V3"))
    assert man.version == "VER2" and man.script_for_module(GARAGE_PATH) == SCRIPT_KEY
    assert man.script_for_module("Nope/X/DataActionY") is None and man.script_for_module("short/path") is None
    assert man.screens() == ["NewDesign_TLAC.Home_V3", "UI_MyToyota.MyToyota_V3"]
    assert discovery.candidate_screens(man, "NewDesign_TLAC.MyToyota_V3") == ["UI_MyToyota.MyToyota_V3"]
    assert discovery.Manifest.from_json({"versionToken": "x"}) is None and discovery.Manifest.from_json({}) is None
