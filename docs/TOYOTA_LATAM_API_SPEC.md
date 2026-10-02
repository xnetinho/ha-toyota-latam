# Toyota LATAM Connected Services — API Specification

Private API behind the **Toyota LATAM Connected Services** app (`com.toyotaargentina.oneapp`; Brazil, Argentina, Chile, Colombia, Peru, Dominican Republic, Panama).

> Sanitized copy: credentials from the original document were removed. Section 6 (Traccar bridge) omitted: out of scope for the HA integration.

## 1. Architecture

1. **IdP:** Auth0 Universal Login, OIDC + PKCE (`S256`).
   - Host: `https://prod-tlac.us.auth0.com`
   - Client ID: `c4zixa2fjqwoJIKwwV9HtFzFUzjEFi11`
   - Redirect: `com.toyotaargentina.oneapp://Toyota_OneApp_EU/LoginCallback`
   - Scopes: `openid profile phone email`
2. **Backend:** OutSystems.
   - Base URL: `https://toyotaargentinasa1.outsystemsenterprise.com/Toyota_OneApp_EU`
   - HTTP `POST` JSON to `/screenservices/...`
   - Needs `viewName`, dynamic `moduleVersion`, `X-CSRFToken`.

## 2. Protocol

### 2.1 Headers

```http
Content-Type: application/json; charset=UTF-8
User-Agent: Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36
X-CSRFToken: <CSRF_TOKEN>
Cookie: nr1Users=<ENCRYPTED_USER_SESSION>; nr2Users=crf=<CSRF_TOKEN>&uid=<USER_ID>&unm=<AUTH0_USER_ID>; OIDC_SESSION=<DEVICE_ID>
```

- Anonymous CSRF token: `T6C+9iB49TLra4jEsMeSckDMNhQ=`
- Authenticated CSRF token: `crf=` key inside the `nr2Users` cookie after login.

### 2.2 Envelope

```json
{
  "versionInfo": {"moduleVersion": "<DYNAMIC_VERSION_TOKEN>", "apiVersion": "<ENDPOINT_HASH>"},
  "viewName": "<EXACT_SCREEN_VIEW_NAME>",
  "screenData": {"variables": {"<PARAM>": "<VALUE>"}}
}
```

Data actions: params under `screenData.variables`. Server actions: params under `inputParameters`.
Wrong values give `400 Bad Request` ("Failed to parse JSON") or `System.InvalidOperationException` ("No role validation found").

## 3. Authentication

```
1. GET precache.manifest                       -> versionToken
2. POST ActionMobile_Get_Authorization_URL     -> Auth0 /authorize URL
3. GET /authorize                              -> state
4. POST /u/login/identifier (email)            -> 302 /u/login/password
5. POST /u/login/password                      -> 302 /authorize/resume
6. GET /authorize/resume (or /u/mfa-detect-browser-capabilities) -> 302 com.toyotaargentina.oneapp://...?code=...
7. POST ActionMobile_Login_OIDC (code, verifier) -> cookies nr1Users, nr2Users
```

### 3.1 Version token
`GET {BASE}/precache.manifest` -> `.versionToken` (e.g. `ATQAKriP_E6m9WKUFYMekw`).

### 3.2 Authorization URL
`POST {BASE}/screenservices/OIDC/ActionMobile_Get_Authorization_URL`, header `X-CSRFToken: T6C+9iB49TLra4jEsMeSckDMNhQ=`

```json
{
  "versionInfo": {"moduleVersion": "<VERSION_TOKEN>", "apiVersion": "vL4NLHMzTpU8s3JblSxqMQ"},
  "viewName": "Common.Login",
  "inputParameters": {
    "AppName": "Toyota",
    "OriginalURL": "https://toyotaargentinasa1.outsystemsenterprise.com/OIDC/rest/Callback/Redirect",
    "LoginHint": "",
    "AdditionalScopes": "",
    "CallbackURL": "com.toyotaargentina.oneapp://Toyota_OneApp_EU/LoginCallback",
    "CodeChallenge": "<BASE64URL_SHA256_CODE_VERIFIER>",
    "CodeChallengeMethod": "S256"
  }
}
```
Response: `data.URL`.

### 3.3 Auth0 web login
1. Independent HTTP session. `GET data.URL`; take `state` from the resulting URL.
2. `POST https://prod-tlac.us.auth0.com/u/login/identifier?state=<STATE>` form `state, username, js-available=true, action=default` -> `302 Location: /u/login/password?state=<PWD_STATE>`.
3. `POST https://prod-tlac.us.auth0.com/u/login/password?state=<PWD_STATE>` form `state, username, password, action=default` -> `302 Location: /authorize/resume?state=...`.
4. If redirected to `/u/mfa-detect-browser-capabilities`, POST `js-available=true&action=default`.
5. Follow redirects until Location starts with `com.toyotaargentina.oneapp://`; parse `code` and `state`.

### 3.4 Code exchange
`POST {BASE}/screenservices/OIDCMobile/OIDC_SSO/Login_Callback/ActionMobile_Login_OIDC`, header `X-CSRFToken: T6C+9iB49TLra4jEsMeSckDMNhQ=`

```json
{
  "versionInfo": {"moduleVersion": "<VERSION_TOKEN>", "apiVersion": "0NT1+xCL2FQ7dcDSxkTX1g"},
  "viewName": "Common.LoginCallback",
  "inputParameters": {
    "code": "<AUTH_CODE>",
    "state": "<STATE>",
    "CallBackURL": "com.toyotaargentina.oneapp://Toyota_OneApp_EU/LoginCallback",
    "CodeVerifier": "<ORIGINAL_CODE_VERIFIER>",
    "PersistentLogin": true,
    "DeviceId": "<DEVICE_ID>"
  }
}
```
Sets `nr1Users` and `nr2Users`; take `crf=` from `nr2Users` as the new `X-CSRFToken`.

## 4. Endpoints

All URLs prefixed with `{BASE}/screenservices/`.

### 4.1 Client profile
- `Toyota_OneApp_EU/Common/LoginCallback/DataActionGetClientById`
- apiVersion `gQXvi1z7YWoZJWexxY1QGA`, viewName `Common.LoginCallback`, variables `{}`
- Response: `SalesForceId`, `ClientId`, `ClientName`, `CountryId` (2 = Brazil, 1 = Argentina), `IsAcceptTermAndConditions`, `IsVerified`

### 4.2 Garage
- `One_App_MDB_Sync/CarSync/Bra_CarSync/DataActionGetCarsGarage`
- apiVersion `EEFiudv295iQFXLqEzuisg`, viewName `NewDesign_TLAC.Home_V3`, variables `{}`
- Response `data.Out_CarouselCarsList.List[]`: `VIN`, `CarId`, `ClientCarId`, `Model`, `ComercialDenomination`, `LicensePlated`, `CarColor`, `Year`, `IsConnected`

### 4.3 Location and moving state
- `MyToyota_MCW/OptimizationBlocks/VehicleStatusMap_V2/DataActionGetConnectedMapInfo`
- apiVersion `SMMTstf+9iTNPkzNRMP1qQ`, viewName `NewDesign_TLAC.MyToyota_V3`
- variables: `Vin`, `ShowMap=false`, `Address=""`, `IsDestroyed=false`, `IsMapInitialize=false`, `IsDarkMode=false`, `IsMoving=false`, `IsPopupTracking=false`, `IsSVTProcess=false`, `Latitude=""`, `Longitude=""`
- Response:
  - `VehicleData.Carevents.List[0].GpsInformation.Latitude|Longitude` (strings)
  - `VehicleData.Carevents.List[0].EventType`: `IG-ON` (moving), `NOTIF1` (movement notification), `IG-OFF` (parked)
  - `SvtStatus.CurrentOperationMode`: `02` normal, `04` SVT tracking
  - `MapsKey`: Google Maps key

### 4.4 Reverse geocoding
`GET https://maps.googleapis.com/maps/api/geocode/json?latlng=<LAT>,<LON>&key=<MapsKey>&language=pt-BR` -> `results[0].formatted_address`

### 4.5 Telemetry
- `MyToyota_MCW/OptimizationBlocks/VehicleStatus_V2/DataActionGetVehicleStatusInfo`
- apiVersion `b_7E9Yzb5XwXKLpOy806Lg`, viewName `NewDesign_TLAC.MyToyota_V3`
- variables: `Vin`, `CarId`, `ShowPopupPlate=false`, `PastMinuteLastUpdate=""`, `PastMinuteLastEngine=""`
- Response `data.VehicleData.Carevents.List[0]`: `FuelRemainingPercentage`, `Odometer`, `OdometerUnit`, `TimestampON` (UTC ISO), `DataCreationTime` (UTC ISO)

### 4.6 Trips
- `Connected_Car_MCW_NEW/FuelConsumptionLastTrip/LastTrip_V2/DataActionGetLastTrips`
- apiVersion `HIIxBlBdma9Spi2CHTDvAQ`, viewName `ConnectedCar_V2.LastTrips_V2`, variables `{Vin}`
- Response `data.Record.Trips.List[]`: `DateInit`, `DateEnd`, `GPS.LatitudeInit|LongitudeInit|LatitudeEnd|LongitudeEnd`, `OdometerInit|OdometerEnd`, `FuelRemainingInit|FuelRemainingEnd`

### 4.7 Geofences
- `Connected_Car_MCW_NEW/Geofence/GeofenceHome_V2/DataActionGetGeofences`
- apiVersion `nrim6nXWO8vQkc+L3hxugQ`, viewName `ConnectedCar_V2.GeofenceHome_V2`, variables `{Vin}`
- Response `data.Response.GeoFencesList.List[]`: `GeoFenceName`, `GeoFenceStatus` (`1` active / `0` inactive), `GeofencingAreaSetting.Latitude|Longitude|Radius|Direction` (`In`, `Out`, `In/Out`)

## 5. Reference behaviour (from original Python client)

- PKCE verifier: `secrets.token_urlsafe(96)`; challenge: base64url(sha256(verifier)) without padding.
- `moduleVersion` falls back to `ATQAKriP_E6m9WKUFYMekw` if the manifest has no `versionToken`.
- HTTP 401/403 -> re-authenticate.
- Polling hint: 30 s while `IG-ON`, 300 s while `IG-OFF`.
