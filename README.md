# Toyota LATAM for Home Assistant

Custom integration (HACS) for **Toyota Connected Services Latin America** (Brazil, Argentina, Chile, Colombia, Peru, Dominican Republic, Panama). Inspired by [ha-toyota-na](https://github.com/widewing/ha-toyota-na).

Integração personalizada (HACS) para os **Serviços Conectados Toyota na América Latina**.

## Install / Instalação

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=xnetinho&repository=ha-toyota-latam&category=integration)

1. Click the button above, or HACS -> Custom repositories -> `https://github.com/xnetinho/ha-toyota-latam` (Integration).
2. Install, restart Home Assistant.
3. Settings -> Devices & services -> Add integration -> **Toyota LATAM**; use the email/password of the Toyota app.

## Entities per vehicle / Entidades por veículo

| Platform | Entities |
|---|---|
| `device_tracker` | Location (+ event type, optional street address) |
| `image` | Vehicle picture (from the Toyota garage; also used as the tracker picture) |
| `sensor` | Color, license plate, driving score/level (+ badges), available services, address (street, on by default), Google Maps key (diagnostic, disabled by default), fuel level, odometer, last report, last ignition on, last trip (distance + attributes), last trip end, active geofences |
| `binary_sensor` | Problem (diagnostic trouble codes), ignition, moving, stolen-vehicle tracking, connected services |
| `button` | Refresh now |

Read-only: the Toyota LATAM API exposes no remote commands (lock, climate...).

### Fields that depend on the model / Campos que dependem do modelo

Toyota's API declares more fields than every car fills in (speed, engine rpm, battery voltage and status, litres of fuel, mileage, trouble codes, heading, speed-alert, tickets, alarm, geofence breaks). The integration reads all of them and **creates each entity the first time the car reports a value**, so hybrids/other models get them automatically and your device list stays free of permanently-empty entities.

A API da Toyota declara mais campos do que todo carro preenche. A integração lê todos e **cria cada entidade na primeira vez que o carro informa um valor**.

## Behaviour / Comportamento

- **Adaptive polling:** 30 s while a vehicle is driving, 300 s parked (Options: 15-3600 s).
- **Resilient:** automatic re-login on expired session; last known values kept through 2 failed updates, then entities go `unavailable` with exponential back-off (max 15 min).
- **Reauth:** wrong/changed password triggers the standard Home Assistant re-authentication prompt, no reinstall needed.
- **Street address:** reverse-geocoded with the Google Maps key that Toyota's API returns, only when the car moved > 50 m. Can be turned off in Options (the Address sensor then disappears).
- **Google Maps key sensor:** exposes Toyota's key as a diagnostic sensor, **disabled by default**. Enabling it stores the key in the HA database/history and shows it to every HA user; treat it as a secret.
- **Diagnostics:** downloadable and redacted (credentials, VIN, plate, coordinates).
- Languages: English, Português (BR), Español.

## Icon / Ícone

The Toyota icon is shipped in `custom_components/toyota_latam/brand/`. Home Assistant shows it from **2026.3** on (earlier versions show the generic placeholder; the integration works the same). The Toyota logo is a trademark of Toyota Motor Corporation; this project is unofficial and not affiliated with Toyota.

## Privacy

Credentials are stored in the HA config entry (Auth0 has no refresh token). Session cookies stay in memory only. This is an unofficial integration, not affiliated with Toyota; it uses a private API that may change.

## Development

```
pip install pytest-homeassistant-custom-component aioresponses ruff
ruff check . && ruff format --check . && pytest
```

Endpoint discovery: [docs/API_DISCOVERY.md](docs/API_DISCOVERY.md). Spec: [docs/TOYOTA_LATAM_API_SPEC.md](docs/TOYOTA_LATAM_API_SPEC.md). Decisions: [docs/adr](docs/adr).
