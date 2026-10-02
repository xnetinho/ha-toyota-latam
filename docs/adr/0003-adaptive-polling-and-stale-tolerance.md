# 0003 - Adaptive polling and stale tolerance

Single coordinator per account. Interval: 30 s while any vehicle is active (IG-ON/NOTIF1), 300 s otherwise (configurable). Trips refetched every 15 min or when a vehicle stops; geofences (incl. breaks) and alerts every 10 min; score/services hourly; diagnostics every 15 min; garage every 6 h. Per-endpoint failures keep previous values; after 3 consecutive total failures entities become unavailable and retry backs off (max 15 min).
