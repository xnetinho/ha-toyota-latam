# API discovery notes

Method: `precache.manifest` lists every file of the OutSystems app. Each screen script (`scripts/<Module>.<Flow>.<Screen>.mvc.js`) contains `callDataAction("<name>", "screenservices/<path>", "<apiVersion>", ...)` and a `VariablesRecord` with the input variables. 83 data actions were found; 22 were called against a real account. All values below are shape-only (no real data).

## Used by the integration

| Action | Path (under `/screenservices/`) | apiVersion | viewName | Variables |
|---|---|---|---|---|
| Garage | `One_App_MDB_Sync/CarSync/Bra_CarSync/DataActionGetCarsGarage` | `lij9jkSisTwmPt_BpS+Wmw` | `NewDesign_TLAC.Home_V3` | none |
| Location | `MyToyota_MCW/OptimizationBlocks/VehicleStatusMap_V2/DataActionGetConnectedMapInfo` | `SMMTstf+9iTNPkzNRMP1qQ` | `UI_MyToyota.MyToyota_V3` | `Vin`, etc. |
| Telemetry | `MyToyota_MCW/OptimizationBlocks/VehicleStatus_V2/DataActionGetVehicleStatusInfo` | `b_7E9Yzb5XwXKLpOy806Lg` | `UI_MyToyota.MyToyota_V3` | `Vin`, `CarId`, etc. |
| Trips | `Connected_Car_MCW_NEW/FuelConsumptionLastTrip/LastTrip_V2/DataActionGetLastTrips` | `HIIxBlBdma9Spi2CHTDvAQ` | `UI_Connected.LastTrips_V2` | `Vin` |
| Driving score | `Connected_Car_MCW_NEW/FuelConsumption/FuelScore_V2/DataActionGetGamification` | `+Vljc2BMdTwIFoxWsVjCcg` | `UI_Connected.FuelScore_V2` | `Vin` |
| Diagnostics (DTC) | `Connected_Car_MCW_NEW/Ecare/CarDiagnostic_V2/DataActionGetEcareDtcs` | `+8w5wjdCooh2Lr8KIp9J8w` | `UI_Connected.EcareCarDiagnostic_V2` | `Vin`, `ShowPopup=false` |
| Available services | `MyToyota_MCW/OptimizationBlocks/VehicleStatusServices_V2/DataActionShowServices` | `BzTW0YOfkIV13CC23Gsj9Q` | `UI_MyToyota.MyToyota_V3` | `Vin`, `UserType="OWNER"` |
| Geofences | `Connected_Car_MCW_NEW/Geofence/GeofenceHome_V2/DataActionGetGeofences` | `nrim6nXWO8vQkc+L3hxugQ` | `UI_Connected.GeofenceHome_V2` | `Vin` |

### Garage item extras
`CarImage` is a **base64 PNG** (~600x353, ~37 KB, no data-URI prefix); `CarColor` (e.g. "Black Metallic"); `CarNickName`; `DateEntry`; many `Contract_*`/`Plan_*`/`Kinto_*`/`Salestracking_*` fields (financing, empty for most users; intentionally not exposed).

### Driving score `Response`
`TotalPoints`, `Level`, `LevelPoints`, `MinPointsLevel`, `MaxLevelPoints`, `Quantity{Speed,Acceleration,Rpm}Badge`, `Quantity{Speed,Acceleration,Rpm}Challenge` (all strings).

### Services
Booleans `ShowSubscription|Assistance|Drivers|Geofence|Insurance|SLastTrips|SpeedAlert|Tracking|Wifi`.

## Works, but not exposed (no useful data or personal data)

| Action | Notes |
|---|---|
| `VehicleStatusService_SpeedAlert/DataActionGetSpeedAlertInfo` (`c5q7M19yIXzmWcFUt_otYQ`, var `Vin`) | `SpeedAlertData{NotificationFrequency, SpeedAlertConfigurationStatus, SpeedAlertName, SpeedLimitSetting}` |
| `SpeedAlert/SpeedAlert_V2/DataActionGetSpeedAlertInfo` (`aoE325nO1ri3Ggd11CezcA`) | `TripsList` = same trips as LastTrips (15 items, `HasMore=false`) |
| `Tracking/Tracking_V2/DataActionGetTrackingInfo` | stolen-vehicle ticket list (empty) + support phone/e-mail |
| `ECareStatus_V2/DataActionGetCentralNotifications8` | open e-care tickets (empty) |
| `AlarmNotification_V2` (action renamed to `DataActionGetAlarmNotification`, apiVersion `KF4PdgNq8HBzQDKzmAYX3w`), `ECallAlert_V2`, `GeofenceCardNotify_V2`, `VehicleStatusService_Geofence` | alarm/e-call/geofence-break notifications (empty in a healthy account); contain client name/phone/e-mail |
| `GeofenceMapFences_V2/DataActionGetVehicleInfo` | geofence list + car position (duplicate of existing data) |
| `Components/CarManual/DataActionGetManual` | `Url_CarManual` (empty) |

## Not usable (tested)
- `TripDetails_V2/DataActionGetTripDetails`, `ServiceHistory_TLAC/*`: `No role validation found` (needs a different `viewName` or is gated by account role).
- `SpeedAlert_V2/DataActionGetSpeedAlertConfig`, `ConnectedSection_V2/*`: server `NullReference` (missing screen state).

## Schema fields exposed even when empty on the tested vehicle

The API declares these fields for every vehicle; the tested car (Corolla Cross, no hybrid/EV) returns them empty, but other models may fill them. The integration parses all of them and creates the matching entity **the first time a value appears** (entities are never removed afterwards). Nothing is created for fields that stay empty.

Source of truth for the field list: the OutSystems model scripts (`Connected_Car_BL.model.js`, `CarEventItem_BLRec`, `TicketItem3_BLRec`, ...).

| API field (`Carevents.List[0]`) | Entity | Notes |
|---|---|---|
| `VehicleSpeed.List[]`, `VehicleSpeedCount` | `sensor.speed` (km/h) | last sample; sample count as attribute |
| `EngineSpeed` | `sensor.engine_speed` (rpm) | |
| `VehicleBatteryVoltage` | `sensor.battery_voltage` (V) | |
| `BatteryStatus` | `sensor.battery_status` | text |
| `FuelRemaining` | `sensor.fuel_remaining` (L) | `FuelRemainingPercentage` is always exposed |
| `Mileage` | `sensor.mileage` (km) | `Odometer` is always exposed |
| `Status`, `TypeMerged` | `sensor.vehicle_status` | `record_type` attribute |
| `DTC.List[]` | `sensor.dtc_codes` | codes as attribute |
| `GpsInformation.Direction` | `sensor.heading` | |
| `GpsInformation.Address` | address sensor | used before calling Google geocoding |
| `GpsInformation.Radius`, `PlaceId` | parsed in `CarEvent` | no entity |
| `Vin`, `DataCreationTime`, `EventType`, `TimestampON` | already exposed | |

| Other source | Entity |
|---|---|
| Trip `SpeedLimitSetting`, `SpeedAlertConfigurationStatus` | `sensor.last_trip_speed_limit` |
| Trip `Event`, `CreatedAt` | parsed in `Trip` |
| `DataActionGetSpeedAlertInfo` -> `SpeedAlertData.*` | `sensor.speed_alert_limit`, `binary_sensor.speed_alert_enabled` |
| Tracking / road assistance / eCall `Tickets.List[]` (`TicketItem`) | `sensor.tracking_tickets`, `assistance_tickets`, `ecall_tickets` (tickets as attribute) |
| `AlarmNotificationResponse.*` | `sensor.alarm_status` |
| `GetGeofences` -> `BrokenUnread/BrokenRead.BrokenFences.List[]` | `sensor.geofence_breaks`, `last_geofence_break`, `binary_sensor.geofence_break_unread` |
| Geofence `PlaceId`, `CrossBorderDirection` | parsed in `Geofence` |
| `ErrorCodes.List[]` (`Code`, `Title`, `Description`, `Prioritydesc`) | `binary_sensor.problem` (`problems` attribute) |
| Garage `DateEntry` | `sensor.registered_at` (disabled by default) |

Alerts, geofence breaks and tickets contain no personal data in the entities we expose. The `ClientInfo`/`Bound` blocks (name, phone, e-mail) returned by the alarm/e-call endpoints are intentionally **not** parsed.

## Not available in this API (confirmed absent)
Tire pressure, doors/windows/locks, range, remote commands. Speed, battery voltage, engine speed and DTC exist in the schema (see above) but are empty on the tested vehicle.

## Notes on pytoyoda/ha_toyota
Targets the **European** backend (`ctpa-oneapi.tceu-ctp-prd.toyotaconnectedeurope.io`, ForgeRock auth) via the `pytoyoda` library. Different auth, host and schema: it cannot be used as a dependency. It was used as a reference for UX (image as `entity_picture`, color as a vehicle attribute, diagnostic sensors).

## Drift log

The backend hot-reloads without notice. Two different things have changed so far, and they fail differently:

| When | What changed | Symptom |
|---|---|---|
| 2026-10 | Screen names (`viewName`): `NewDesign_TLAC.MyToyota_V3` -> `UI_MyToyota.MyToyota_V3`, `ConnectedCar_V2.*` -> `UI_Connected.*`. `apiVersion` hashes were unchanged. | exception `No role validation found` |
| 2026-11 | Garage `apiVersion` hash; alarm action renamed (`DataActionGetCentralNotifications3` -> `DataActionGetAlarmNotification`). `viewName`s unchanged. | **empty `data` + `versionInfo.hasApiVersionChanged: true`, no exception** |

The server validates the `apiVersion` **before** the screen name, so a stale hash hides a stale screen name.

## Self-healing (`discovery.py`)

The app publishes both values itself, so the client re-reads them instead of depending only on constants:

1. `GET precache.manifest` -> `urlVersions` lists every script with its cache hash.
2. The script defining an action is `scripts/<Module>.<Flow>.<Screen>.mvc.js` (the action path minus its last segment, dots instead of slashes). It contains `callDataAction("<name>", "screenservices/<path>", "<apiVersion>")`.
3. Screen names are read from file names only: `scripts/Toyota_OneApp_EU.<Flow>.<Screen>.mvc.js` -> `<Flow>.<Screen>`. A renamed flow keeps the screen leaf, so candidates are "same leaf, other flow".

`ToyotaLatamClient._call` recovers once per endpoint when it sees `hasApiVersionChanged` or `No role validation found`: it fetches the current hash and tries it with the known screen name, then with same-leaf screens, and remembers the first combination the server accepts. A failed recovery is not retried for 30 minutes. Session expiry gives the same `No role validation found`, so if the manifest cannot explain the refusal the client falls back to one re-login.

Limits: an action that is removed or renamed (like the alarm one) is not found by path, and a screen renamed to an unrelated leaf is not guessed. Both still need a release; the client logs a warning naming the action.

Re-extract everything by hand: the 519 `callDataAction`/`callServerAction` entries in all `*.mvc.js` scripts.
