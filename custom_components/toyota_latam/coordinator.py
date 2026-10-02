"""Adaptive-polling coordinator (see docs/adr/0003)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, fields, replace
from datetime import timedelta
from math import asin, cos, radians, sin, sqrt

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    Alerts,
    CarEvent,
    Diagnostics,
    DrivingScore,
    GeofenceData,
    Location,
    Services,
    Telemetry,
    ToyotaAuthError,
    ToyotaError,
    ToyotaLatamClient,
    Trip,
    Vehicle,
)
from .const import (
    ALERTS_REFRESH,
    CONF_ACTIVE_INTERVAL,
    CONF_PARKED_INTERVAL,
    CONF_RESOLVE_ADDRESS,
    DEFAULT_ACTIVE_INTERVAL,
    DEFAULT_PARKED_INTERVAL,
    DEFAULT_RESOLVE_ADDRESS,
    DIAGNOSTICS_REFRESH,
    DOMAIN,
    GARAGE_REFRESH,
    GEOCODE_MIN_MOVE_M,
    GEOFENCE_REFRESH,
    MAX_BACKOFF,
    MAX_STALE_FAILURES,
    SLOW_REFRESH,
    TRIPS_REFRESH,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class VehicleData:
    vehicle: Vehicle
    location: Location | None = None
    telemetry: Telemetry | None = None
    trips: tuple[Trip, ...] = ()
    geofences: GeofenceData = field(default_factory=GeofenceData)
    address: str | None = None
    score: DrivingScore | None = None
    diagnostics: Diagnostics | None = None
    services: Services | None = None
    alerts: Alerts | None = None
    stale: bool = False

    @property
    def event(self) -> CarEvent:
        """CarEvent fields merged from both vehicle endpoints (first non-empty value wins)."""
        parts = [x.event for x in (self.telemetry, self.location) if x]
        return CarEvent(
            **{
                f.name: next((v for p in parts if (v := getattr(p, f.name)) not in (None, ())), None)
                or (() if f.name == "dtc" else None)
                for f in fields(CarEvent)
            }
        )

    @property
    def last_trip(self) -> Trip | None:
        return max(self.trips, key=lambda t: t.end.timestamp() if t.end else 0, default=None)


@dataclass
class _Timers:
    trips: float = float("-inf")
    geofences: float = float("-inf")
    score: float = float("-inf")
    diagnostics: float = float("-inf")
    services: float = float("-inf")
    alerts: float = float("-inf")
    geo_pos: tuple[float, float] | None = field(default=None)
    was_active: bool = False


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(radians, (*a, *b))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


class ToyotaCoordinator(DataUpdateCoordinator[dict[str, VehicleData]]):
    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ToyotaLatamClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(seconds=30))
        self.client = client
        self._vehicles: list[Vehicle] = []
        self._garage_at = float("-inf")
        self._timers: dict[str, _Timers] = {}
        self._failures = 0
        self._maps_key: str | None = None

    @property
    def _opts(self):
        return self.config_entry.options

    @property
    def active_interval(self) -> int:
        return int(self._opts.get(CONF_ACTIVE_INTERVAL, DEFAULT_ACTIVE_INTERVAL))

    @property
    def parked_interval(self) -> int:
        return int(self._opts.get(CONF_PARKED_INTERVAL, DEFAULT_PARKED_INTERVAL))

    async def _async_update_data(self) -> dict[str, VehicleData]:
        try:
            data = await self._poll()
        except ToyotaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ToyotaError as err:
            return self._on_failure(err)
        self._failures = 0
        any_active = any(d.location and d.location.is_active for d in data.values())
        self.update_interval = timedelta(seconds=self.active_interval if any_active else self.parked_interval)
        return data

    def _on_failure(self, err: Exception) -> dict[str, VehicleData]:
        self._failures += 1
        base = self.parked_interval
        self.update_interval = timedelta(seconds=min(base * 2 ** (self._failures - 1), MAX_BACKOFF))
        if self.data and self._failures < MAX_STALE_FAILURES:
            _LOGGER.warning("Toyota update failed (%s); keeping last known data (%d)", err, self._failures)
            return {k: replace(v, stale=True) for k, v in self.data.items()}
        raise UpdateFailed(f"Toyota LATAM unavailable: {err}") from err

    async def _poll(self) -> dict[str, VehicleData]:
        now = time.monotonic()
        if not self._vehicles or now - self._garage_at > GARAGE_REFRESH:
            vehicles = await self.client.get_vehicles()
            self._garage_at = now
            if self._vehicles and {v.vin for v in vehicles} != {v.vin for v in self._vehicles}:
                _LOGGER.info("Garage changed, reloading integration")
                self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
            self._vehicles = vehicles
        prev = self.data or {}
        out: dict[str, VehicleData] = {}
        errors: list[ToyotaError] = []
        for veh in self._vehicles:
            old = prev.get(veh.vin)
            cur = VehicleData(
                vehicle=veh,
                location=old.location if old else None,
                telemetry=old.telemetry if old else None,
                trips=old.trips if old else (),
                geofences=old.geofences if old else GeofenceData(),
                address=old.address if old else None,
                score=old.score if old else None,
                diagnostics=old.diagnostics if old else None,
                services=old.services if old else None,
                alerts=old.alerts if old else None,
            )
            tm = self._timers.setdefault(veh.vin, _Timers())
            try:
                cur = replace(cur, location=await self.client.get_location(veh.vin))
                if cur.location.maps_key:
                    self._maps_key = cur.location.maps_key
            except ToyotaAuthError:
                raise
            except ToyotaError as err:
                errors.append(err)
            try:
                cur = replace(cur, telemetry=await self.client.get_telemetry(veh.vin, veh.car_id))
            except ToyotaAuthError:
                raise
            except ToyotaError as err:
                errors.append(err)
            active = bool(cur.location and cur.location.is_active)
            if now - tm.trips > TRIPS_REFRESH or (tm.was_active and not active):
                try:
                    cur = replace(cur, trips=tuple(await self.client.get_trips(veh.vin)))
                    tm.trips = now
                except ToyotaAuthError:
                    raise
                except ToyotaError as err:
                    _LOGGER.debug("trips failed: %s", err)
            if now - tm.geofences > GEOFENCE_REFRESH:
                try:
                    cur = replace(cur, geofences=await self.client.get_geofences(veh.vin))
                    tm.geofences = now
                except ToyotaAuthError:
                    raise
                except ToyotaError as err:
                    _LOGGER.debug("geofences failed: %s", err)
            cur = await self._slow(cur, tm, now)
            tm.was_active = active
            cur = replace(cur, address=await self._address(tm, cur))
            out[veh.vin] = cur
        if self._vehicles and len(errors) >= 2 * len(self._vehicles):
            raise errors[0]
        return out

    async def _slow(self, cur: VehicleData, tm: _Timers, now: float) -> VehicleData:
        """Optional endpoints: failures are logged at debug and never affect core data."""
        vin = cur.vehicle.vin
        for attr, interval, fetch in (
            ("score", SLOW_REFRESH, self.client.get_driving_score),
            ("diagnostics", DIAGNOSTICS_REFRESH, self.client.get_diagnostics),
            ("services", SLOW_REFRESH, self.client.get_services),
            ("alerts", ALERTS_REFRESH, self.client.get_alerts),
        ):
            if now - getattr(tm, attr) <= interval:
                continue
            try:
                cur = replace(cur, **{attr: await fetch(vin)})
            except ToyotaAuthError:
                raise
            except ToyotaError as err:
                _LOGGER.debug("%s unavailable: %s", attr, err)
            setattr(tm, attr, now)
        return cur

    async def _address(self, tm: _Timers, cur: VehicleData) -> str | None:
        loc = cur.location
        if not loc:
            return None
        if loc.event.address:
            return loc.event.address
        if not self._opts.get(CONF_RESOLVE_ADDRESS, DEFAULT_RESOLVE_ADDRESS) or not self._maps_key:
            return None
        if loc.latitude is None or loc.longitude is None:
            return cur.address
        pos = (loc.latitude, loc.longitude)
        if cur.address and tm.geo_pos and _distance_m(tm.geo_pos, pos) < GEOCODE_MIN_MOVE_M:
            return cur.address
        lang = self.hass.config.language
        addr = await self.client.reverse_geocode(*pos, self._maps_key, lang if lang != "en" else "pt-BR")
        if addr:
            tm.geo_pos = pos
            return addr
        return cur.address
