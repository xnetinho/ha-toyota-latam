# 0004 - Reverse geocoding uses Toyota's Google Maps key

The location response includes a Google `MapsKey` owned by Toyota. Using it for geocoding mirrors the official app, but it is a credential we do not own.

Update (E05): the Address sensor is **on by default** (users expected it); option `resolve_address` turns it off. Lookups only happen when the vehicle moved > 50 m. The key itself is exposed only through a diagnostic sensor that is disabled by default, and is redacted in diagnostics.
