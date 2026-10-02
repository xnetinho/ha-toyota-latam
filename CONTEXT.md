# Toyota LATAM (Home Assistant)

Custom integration (domain `toyota_latam`) exposing Toyota Connected Services LATAM vehicles in Home Assistant. Read-only: the API has no remote commands.

## Glossary

- **Vehicle**: a car in the user's Garage, identified by VIN. One HA device per Vehicle.
- **Garage**: list of Vehicles of the account (`DataActionGetCarsGarage`).
- **Session**: authenticated OutSystems cookies + CSRF token + module version token. Held in memory only.
- **Module version**: `versionToken` from `precache.manifest`; sent as `moduleVersion` in every call.
- **Ignition state**: last `EventType` (`IG-ON`, `IG-OFF`, `NOTIF1`). `IG-ON`/`NOTIF1` = *active*.
- **Adaptive polling**: short interval while any Vehicle is active, long when all parked.
- **Stale data**: last known values kept during transient failures (< 3 consecutive).
- **SVT**: stolen vehicle tracking (`CurrentOperationMode` `04` = tracking).

## Layout

- `custom_components/toyota_latam/api.py`: async HTTP client (Auth0 PKCE + OutSystems), no HA imports.
- `coordinator.py`: DataUpdateCoordinator, adaptive polling, failure isolation.
- `config_flow.py`: user / reauth / options.
- Platforms: `sensor`, `binary_sensor`, `device_tracker`, `button`.

Decisions: `docs/adr/`. API spec: `docs/TOYOTA_LATAM_API_SPEC.md`.
