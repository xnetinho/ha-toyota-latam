from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.toyota_latam.api import (
    Diagnostics,
    DrivingScore,
    Geofence,
    Location,
    Services,
    Telemetry,
    Trip,
    Vehicle,
)
from custom_components.toyota_latam.const import DOMAIN

PNG = b"\x89PNG\r\n\x1a\nfake"
VEHICLE = Vehicle(
    "9BRTESTVIN0000001", "100001", "Corolla Cross", "XRE", "TST1A23", "Black", 2027, True, "Corolla Cross", PNG
)
LOC_PARKED = Location(-23.55, -46.63, "IG-OFF", "02", "KEY")
LOC_MOVING = Location(-23.56, -46.64, "IG-ON", "02", "KEY")
TELE = Telemetry(84, 89, "km", None, None)
TRIP = Trip(None, None, None, None, None, None, 10.0, 15.0, 90.0, 85.0)
GEOFENCE = Geofence("Casa", True, -23.0, -46.0, 200.0, "In/Out")


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN, unique_id="a@b.c", title="a@b.c", data={"username": "a@b.c", "password": "pw"}
    )


@pytest.fixture
def mock_client():
    with patch("custom_components.toyota_latam.ToyotaLatamClient", autospec=True) as cls:
        c = cls.return_value
        c.login = AsyncMock()
        c.get_vehicles = AsyncMock(return_value=[VEHICLE])
        c.get_location = AsyncMock(return_value=LOC_PARKED)
        c.get_telemetry = AsyncMock(return_value=TELE)
        c.get_trips = AsyncMock(return_value=[TRIP])
        c.get_geofences = AsyncMock(return_value=[GEOFENCE])
        c.get_driving_score = AsyncMock(return_value=DrivingScore(1850, 1, 300, 1500, 2999, 17, 3, 17))
        c.get_diagnostics = AsyncMock(return_value=Diagnostics(0, ()))
        c.get_services = AsyncMock(return_value=Services({"geofence": True, "wifi": False}))
        c.reverse_geocode = AsyncMock(return_value="Rua X, 1")
        yield c


@pytest.fixture(autouse=True)
def _no_real_session():
    with (
        patch("custom_components.toyota_latam.async_create_clientsession"),
        patch("custom_components.toyota_latam.config_flow.async_create_clientsession"),
    ):
        yield
