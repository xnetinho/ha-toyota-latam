"""Async client for Toyota LATAM Connected Services (Auth0 PKCE + OutSystems). No HA imports."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://toyotaargentinasa1.outsystemsenterprise.com/Toyota_OneApp_EU"
OIDC_ORIGINAL_URL = "https://toyotaargentinasa1.outsystemsenterprise.com/OIDC/rest/Callback/Redirect"
AUTH0_URL = "https://prod-tlac.us.auth0.com"
APP_SCHEME = "com.toyotaargentina.oneapp://"
CALLBACK_URL = f"{APP_SCHEME}Toyota_OneApp_EU/LoginCallback"
ANON_CSRF = "T6C+9iB49TLra4jEsMeSckDMNhQ="
FALLBACK_MODULE_VERSION = "ATQAKriP_E6m9WKUFYMekw"
USER_AGENT = "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36"
ACTIVE_EVENTS = frozenset({"IG-ON", "NOTIF1"})
TIMEOUT = aiohttp.ClientTimeout(total=20)
_SVC = f"{BASE_URL}/screenservices"


class ToyotaError(Exception):
    """Base error."""


class ToyotaAuthError(ToyotaError):
    """Credentials rejected."""


class ToyotaConnectionError(ToyotaError):
    """Network / timeout / 5xx."""


class ToyotaSessionExpired(ToyotaError):
    """OutSystems session no longer valid."""


class ToyotaApiError(ToyotaError):
    """Unexpected API answer."""


@dataclass(frozen=True)
class Endpoint:
    path: str
    api_version: str
    view: str


GARAGE = Endpoint(
    "One_App_MDB_Sync/CarSync/Bra_CarSync/DataActionGetCarsGarage",
    "EEFiudv295iQFXLqEzuisg",
    "NewDesign_TLAC.Home_V3",
)
LOCATION = Endpoint(
    "MyToyota_MCW/OptimizationBlocks/VehicleStatusMap_V2/DataActionGetConnectedMapInfo",
    "SMMTstf+9iTNPkzNRMP1qQ",
    "NewDesign_TLAC.MyToyota_V3",
)
TELEMETRY = Endpoint(
    "MyToyota_MCW/OptimizationBlocks/VehicleStatus_V2/DataActionGetVehicleStatusInfo",
    "b_7E9Yzb5XwXKLpOy806Lg",
    "NewDesign_TLAC.MyToyota_V3",
)
TRIPS = Endpoint(
    "Connected_Car_MCW_NEW/FuelConsumptionLastTrip/LastTrip_V2/DataActionGetLastTrips",
    "HIIxBlBdma9Spi2CHTDvAQ",
    "ConnectedCar_V2.LastTrips_V2",
)
GEOFENCES = Endpoint(
    "Connected_Car_MCW_NEW/Geofence/GeofenceHome_V2/DataActionGetGeofences",
    "nrim6nXWO8vQkc+L3hxugQ",
    "ConnectedCar_V2.GeofenceHome_V2",
)


def _f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int | None:
    f = _f(v)
    return None if f is None else int(f)


def _dt(v: Any) -> datetime | None:
    if not v or not isinstance(v, str):
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _list(d: Any, *path: str) -> list[dict]:
    for p in path:
        d = d.get(p) if isinstance(d, dict) else None
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []


def _dict(d: Any, *path: str) -> dict:
    for p in path:
        d = d.get(p) if isinstance(d, dict) else None
    return d if isinstance(d, dict) else {}


@dataclass(frozen=True)
class Vehicle:
    vin: str
    car_id: str
    model: str
    trim: str | None
    plate: str | None
    color: str | None
    year: int | None
    connected: bool

    @classmethod
    def from_api(cls, d: dict) -> Vehicle | None:
        if not d.get("VIN"):
            return None
        return cls(
            vin=str(d["VIN"]),
            car_id=str(d.get("CarId", "")),
            model=d.get("Model") or "Toyota",
            trim=d.get("ComercialDenomination") or None,
            plate=d.get("LicensePlated") or None,
            color=d.get("CarColor") or None,
            year=_i(d.get("Year")),
            connected=bool(d.get("IsConnected", True)),
        )


@dataclass(frozen=True)
class Location:
    latitude: float | None
    longitude: float | None
    event_type: str | None
    svt_mode: str | None
    maps_key: str | None = field(default=None, repr=False)

    @property
    def is_active(self) -> bool:
        return self.event_type in ACTIVE_EVENTS

    @classmethod
    def from_api(cls, data: dict) -> Location:
        ev = (_list(data, "VehicleData", "Carevents", "List") or [{}])[0]
        gps = _dict(ev, "GpsInformation")
        return cls(
            latitude=_f(gps.get("Latitude")),
            longitude=_f(gps.get("Longitude")),
            event_type=ev.get("EventType") or None,
            svt_mode=_dict(data, "SvtStatus").get("CurrentOperationMode") or None,
            maps_key=data.get("MapsKey") or None,
        )


@dataclass(frozen=True)
class Telemetry:
    fuel_percent: int | None
    odometer: int | None
    odometer_unit: str
    ignition_on_at: datetime | None
    reported_at: datetime | None

    @classmethod
    def from_api(cls, data: dict) -> Telemetry:
        ev = (_list(data, "VehicleData", "Carevents", "List") or [{}])[0]
        return cls(
            fuel_percent=_i(ev.get("FuelRemainingPercentage")),
            odometer=_i(ev.get("Odometer")),
            odometer_unit=ev.get("OdometerUnit") or "km",
            ignition_on_at=_dt(ev.get("TimestampON")),
            reported_at=_dt(ev.get("DataCreationTime")),
        )


@dataclass(frozen=True)
class Trip:
    start: datetime | None
    end: datetime | None
    start_lat: float | None
    start_lon: float | None
    end_lat: float | None
    end_lon: float | None
    odometer_start: float | None
    odometer_end: float | None
    fuel_start: float | None
    fuel_end: float | None

    @property
    def distance(self) -> float | None:
        if self.odometer_start is None or self.odometer_end is None:
            return None
        return max(self.odometer_end - self.odometer_start, 0.0)

    @classmethod
    def from_api(cls, d: dict) -> Trip:
        gps = _dict(d, "GPS")
        return cls(
            _dt(d.get("DateInit")),
            _dt(d.get("DateEnd")),
            _f(gps.get("LatitudeInit")),
            _f(gps.get("LongitudeInit")),
            _f(gps.get("LatitudeEnd")),
            _f(gps.get("LongitudeEnd")),
            _f(d.get("OdometerInit")),
            _f(d.get("OdometerEnd")),
            _f(d.get("FuelRemainingInit")),
            _f(d.get("FuelRemainingEnd")),
        )


@dataclass(frozen=True)
class Geofence:
    name: str
    active: bool
    latitude: float | None
    longitude: float | None
    radius: float | None
    direction: str | None

    @classmethod
    def from_api(cls, d: dict) -> Geofence:
        a = _dict(d, "GeofencingAreaSetting")
        return cls(
            name=d.get("GeoFenceName") or "Geofence",
            active=str(d.get("GeoFenceStatus")) == "1",
            latitude=_f(a.get("Latitude")),
            longitude=_f(a.get("Longitude")),
            radius=_f(a.get("Radius")),
            direction=a.get("Direction") or None,
        )


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(96)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def parse_csrf(cookie_value: str | None) -> str | None:
    """Extract ``crf`` from an ``nr2Users`` cookie (URL-encoded or raw)."""
    if not cookie_value:
        return None
    for part in unquote(cookie_value).replace("&", ";").split(";"):
        key, _, val = part.strip().partition("=")
        if key == "crf" and val:
            return val
    return None


def _query(url: str, key: str) -> str | None:
    return (parse_qs(urlparse(url).query).get(key) or [None])[0]


class ToyotaLatamClient:
    """``session`` must own its cookie jar (HA ``async_create_clientsession``): it is cleared on login."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._version: str | None = None
        self._csrf = ANON_CSRF
        self._login_lock = asyncio.Lock()
        self._generation = 0
        self._logged_in = False

    def set_credentials(self, username: str, password: str) -> None:
        self._username, self._password = username, password

    async def _fetch_version(self) -> str:
        try:
            async with self._session.get(
                f"{BASE_URL}/precache.manifest", timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
            ) as r:
                r.raise_for_status()
                data = await r.json(content_type=None)
            self._version = data.get("versionToken") or FALLBACK_MODULE_VERSION
        except (TimeoutError, aiohttp.ClientError, ValueError, AttributeError) as err:
            if self._version is None:
                _LOGGER.debug("precache.manifest unavailable (%s), using fallback version", err)
                self._version = FALLBACK_MODULE_VERSION
        return self._version

    def _update_csrf(self, resp: aiohttp.ClientResponse) -> None:
        morsel = resp.cookies.get("nr2Users")
        token = parse_csrf(morsel.value if morsel else None)
        if token is None:
            for c in self._session.cookie_jar:
                if c.key == "nr2Users":
                    token = parse_csrf(c.value)
        if token:
            self._csrf = token

    async def _post(self, url: str, payload: dict, csrf: str | None = None) -> dict:
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json; charset=UTF-8",
            "X-CSRFToken": csrf or self._csrf,
        }
        try:
            async with self._session.post(url, json=payload, headers=headers, timeout=TIMEOUT) as r:
                if r.status in (401, 403):
                    raise ToyotaSessionExpired(f"HTTP {r.status}")
                if r.status == 429 or r.status >= 500:
                    raise ToyotaConnectionError(f"HTTP {r.status}")
                if r.status >= 400:
                    raise ToyotaApiError(f"HTTP {r.status}")
                self._update_csrf(r)
                body = await r.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise ToyotaConnectionError(str(err) or type(err).__name__) from err
        except ValueError as err:
            raise ToyotaApiError("invalid JSON") from err
        if not isinstance(body, dict):
            raise ToyotaApiError("unexpected response")
        exc = body.get("exception")
        if exc:
            msg = str(_dict(body, "exception").get("message", exc))
            if any(k in msg.lower() for k in ("role", "csrf", "login", "session", "authenticat")):
                raise ToyotaSessionExpired(msg)
            raise ToyotaApiError(msg)
        return body

    async def login(self) -> None:
        """Full Auth0 PKCE login. Raises ToyotaAuthError on bad credentials."""
        async with self._login_lock:
            await self._login()

    async def _login(self) -> None:
        self._csrf = ANON_CSRF
        self._session.cookie_jar.clear()
        version = await self._fetch_version()
        verifier, challenge = pkce_pair()
        body = await self._post(
            f"{_SVC}/OIDC/ActionMobile_Get_Authorization_URL",
            {
                "versionInfo": {"moduleVersion": version, "apiVersion": "vL4NLHMzTpU8s3JblSxqMQ"},
                "viewName": "Common.Login",
                "inputParameters": {
                    "AppName": "Toyota",
                    "OriginalURL": OIDC_ORIGINAL_URL,
                    "LoginHint": "",
                    "AdditionalScopes": "",
                    "CallbackURL": CALLBACK_URL,
                    "CodeChallenge": challenge,
                    "CodeChallengeMethod": "S256",
                },
            },
        )
        auth_url = _dict(body, "data").get("URL")
        if not auth_url:
            raise ToyotaApiError("no authorization URL")
        code, state = await self._auth0_flow(auth_url)
        body = await self._post(
            f"{_SVC}/OIDCMobile/OIDC_SSO/Login_Callback/ActionMobile_Login_OIDC",
            {
                "versionInfo": {"moduleVersion": version, "apiVersion": "0NT1+xCL2FQ7dcDSxkTX1g"},
                "viewName": "Common.LoginCallback",
                "inputParameters": {
                    "code": code,
                    "state": state,
                    "CallBackURL": CALLBACK_URL,
                    "CodeVerifier": verifier,
                    "PersistentLogin": True,
                    "DeviceId": f"ha_{secrets.token_hex(6)}",
                },
            },
            csrf=ANON_CSRF,
        )
        if self._csrf == ANON_CSRF:
            raise ToyotaAuthError("login did not establish a session")
        self._generation += 1
        self._logged_in = True
        _LOGGER.debug("Toyota LATAM login ok")

    async def _auth0_flow(self, auth_url: str) -> tuple[str, str]:
        hdr = {"User-Agent": USER_AGENT}
        try:
            idp = self._session
            async with idp.get(auth_url, headers=hdr, timeout=TIMEOUT) as r:
                state = _query(str(r.url), "state")
            if not state:
                raise ToyotaApiError("no Auth0 state")
            loc = await self._idp_post(
                idp,
                "/u/login/identifier",
                state,
                {"username": self._username, "js-available": "true", "action": "default"},
            )
            pwd_state = _query(loc, "state") if "/u/login/password" in loc else None
            if not pwd_state:
                raise ToyotaAuthError("unknown account")
            loc = await self._idp_post(
                idp,
                "/u/login/password",
                pwd_state,
                {"username": self._username, "password": self._password, "action": "default"},
            )
            if "/u/login/password" in loc:
                raise ToyotaAuthError("invalid credentials")
            for _ in range(10):
                if loc.startswith(APP_SCHEME):
                    break
                if "/u/mfa-detect-browser-capabilities" in loc:
                    loc = await self._idp_post(
                        idp,
                        "/u/mfa-detect-browser-capabilities",
                        _query(loc, "state") or pwd_state,
                        {"js-available": "true", "action": "default"},
                    )
                    continue
                async with idp.get(urljoin(AUTH0_URL, loc), headers=hdr, timeout=TIMEOUT, allow_redirects=False) as r:
                    if r.status not in (301, 302, 303, 307):
                        raise ToyotaAuthError("login interrupted (unsupported challenge)")
                    loc = r.headers.get("Location", "")
            else:
                raise ToyotaApiError("too many redirects")
        except (TimeoutError, aiohttp.ClientError) as err:
            raise ToyotaConnectionError(str(err) or type(err).__name__) from err
        code, st = _query(loc, "code"), _query(loc, "state")
        if not code or not st:
            raise ToyotaAuthError("no authorization code")
        return code, st

    async def _idp_post(self, idp: aiohttp.ClientSession, path: str, state: str, data: dict) -> str:
        async with idp.post(
            f"{AUTH0_URL}{path}?state={state}",
            data={"state": state, **data},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            allow_redirects=False,
        ) as r:
            if r.status == 429:
                raise ToyotaConnectionError("Auth0 rate limited")
            if r.status >= 500:
                raise ToyotaConnectionError(f"Auth0 HTTP {r.status}")
            if r.status not in (301, 302, 303, 307):
                raise ToyotaAuthError(f"Auth0 rejected {path} (HTTP {r.status})")
            return r.headers.get("Location", "")

    async def _call(self, ep: Endpoint, variables: dict[str, Any]) -> dict:
        """Authenticated data action. One transparent re-login on expired session / stale module."""
        if not self._logged_in:
            await self._relogin(self._generation)
        for attempt in (0, 1):
            gen = self._generation
            payload = {
                "versionInfo": {"moduleVersion": self._version, "apiVersion": ep.api_version},
                "viewName": ep.view,
                "screenData": {"variables": variables},
            }
            try:
                body = await self._post(f"{_SVC}/{ep.path}", payload)
            except ToyotaSessionExpired:
                if attempt:
                    raise
                await self._relogin(gen)
                continue
            if _dict(body, "versionInfo").get("hasModuleVersionChanged") and attempt == 0:
                self._version = None
                await self._fetch_version()
                continue
            return _dict(body, "data")
        raise ToyotaApiError("unreachable")  # pragma: no cover

    async def _relogin(self, seen_generation: int) -> None:
        async with self._login_lock:
            if self._generation != seen_generation and self._logged_in:
                return
            await self._login()

    async def get_vehicles(self) -> list[Vehicle]:
        data = await self._call(GARAGE, {})
        return [v for d in _list(data, "Out_CarouselCarsList", "List") if (v := Vehicle.from_api(d))]

    async def get_location(self, vin: str) -> Location:
        return Location.from_api(
            await self._call(
                LOCATION,
                {
                    "Vin": vin,
                    "ShowMap": False,
                    "Address": "",
                    "IsDestroyed": False,
                    "IsMapInitialize": False,
                    "IsDarkMode": False,
                    "IsMoving": False,
                    "IsPopupTracking": False,
                    "IsSVTProcess": False,
                    "Latitude": "",
                    "Longitude": "",
                },
            )
        )

    async def get_telemetry(self, vin: str, car_id: str) -> Telemetry:
        return Telemetry.from_api(
            await self._call(
                TELEMETRY,
                {
                    "Vin": vin,
                    "CarId": str(car_id),
                    "ShowPopupPlate": False,
                    "PastMinuteLastUpdate": "",
                    "PastMinuteLastEngine": "",
                },
            )
        )

    async def get_trips(self, vin: str) -> list[Trip]:
        data = await self._call(TRIPS, {"Vin": vin})
        return [Trip.from_api(d) for d in _list(data, "Record", "Trips", "List")]

    async def get_geofences(self, vin: str) -> list[Geofence]:
        data = await self._call(GEOFENCES, {"Vin": vin})
        return [Geofence.from_api(d) for d in _list(data, "Response", "GeoFencesList", "List")]

    async def reverse_geocode(self, lat: float, lon: float, maps_key: str, language: str = "pt-BR") -> str | None:
        try:
            async with self._session.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"latlng": f"{lat},{lon}", "key": maps_key, "language": language},
                timeout=TIMEOUT,
            ) as r:
                if r.status != 200:
                    return None
                res = _list(await r.json(content_type=None), "results")
        except (TimeoutError, aiohttp.ClientError, ValueError):
            return None
        return res[0].get("formatted_address") if res else None
