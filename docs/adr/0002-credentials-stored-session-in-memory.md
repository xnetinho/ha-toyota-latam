# 0002 - Store credentials, keep session in memory

Auth0 requires a full web login; there is no refresh token. The entry stores email+password (like ha-toyota-na) and re-logs in transparently on session expiry (one login at a time, lock-guarded). Cookies/CSRF are never persisted. Invalid credentials raise `ConfigEntryAuthFailed` -> HA reauth flow.
