# 0001 - Own async client, no PyPI dependency

The API is an undocumented OutSystems backend with no maintained library. `api.py` is a self-contained aiohttp client (HA-free, unit-testable); manifest has no `requirements`. Avoids the monkey-patching of a pinned library that ha-toyota-na needs.
