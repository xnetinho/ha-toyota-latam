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
