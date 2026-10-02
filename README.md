# Toyota LATAM for Home Assistant

Custom integration (HACS) for **Toyota Connected Services Latin America** (Brazil, Argentina, Chile, Colombia, Peru, Dominican Republic, Panama). Inspired by [ha-toyota-na](https://github.com/widewing/ha-toyota-na).

Integração personalizada (HACS) para os **Serviços Conectados Toyota na América Latina**.

## Install / Instalação

1. HACS -> Custom repositories -> `https://github.com/xnetinho/ha-toyota-latam` (Integration).
2. Install, restart Home Assistant.
3. Settings -> Devices & services -> Add integration -> **Toyota LATAM**; use the email/password of the Toyota app.

## Entities per vehicle / Entidades por veículo

| Platform | Entities |
|---|---|
| `device_tracker` | Location (+ event type, optional street address) |
| `sensor` | Address (street, on by default), Google Maps key (diagnostic, disabled by default), fuel level, odometer, last report, last ignition on, last trip (distance + attributes), last trip end, active geofences |
| `binary_sensor` | Ignition, moving, stolen-vehicle tracking, connected services |
| `button` | Refresh now |

Read-only: the Toyota LATAM API exposes no remote commands (lock, climate...).

## Behaviour / Comportamento

- **Adaptive polling:** 30 s while a vehicle is driving, 300 s parked (Options: 15-3600 s).
- **Resilient:** automatic re-login on expired session; last known values kept through 2 failed updates, then entities go `unavailable` with exponential back-off (max 15 min).
- **Reauth:** wrong/changed password triggers the standard Home Assistant re-authentication prompt, no reinstall needed.
- **Street address:** reverse-geocoded with the Google Maps key that Toyota's API returns, only when the car moved > 50 m. Can be turned off in Options (the Address sensor then disappears).
- **Google Maps key sensor:** exposes Toyota's key as a diagnostic sensor, **disabled by default**. Enabling it stores the key in the HA database/history and shows it to every HA user; treat it as a secret.
- **Diagnostics:** downloadable and redacted (credentials, VIN, plate, coordinates).
- Languages: English, Português (BR), Español.

## Privacy

Credentials are stored in the HA config entry (Auth0 has no refresh token). Session cookies stay in memory only. This is an unofficial integration, not affiliated with Toyota; it uses a private API that may change.

## Development

```
pip install pytest-homeassistant-custom-component aioresponses ruff
ruff check . && ruff format --check . && pytest
```

Spec: [docs/TOYOTA_LATAM_API_SPEC.md](docs/TOYOTA_LATAM_API_SPEC.md). Decisions: [docs/adr](docs/adr).
