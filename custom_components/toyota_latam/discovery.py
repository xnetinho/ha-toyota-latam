"""Self-healing endpoint metadata read from the app's own ``precache.manifest``.

The OutSystems backend changes per-action ``apiVersion`` hashes and screen (``viewName``) names without notice.
Both are published by the app itself, so we read them instead of relying only on the values baked into ``api.py``.
No HA imports.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import aiohttp

_LOGGER = logging.getLogger(__name__)

_ACTION = re.compile(r'callDataAction\("[A-Za-z0-9_]+",\s*"screenservices/([^"]+)",\s*"([^"]+)"')
_SCREEN_FILE = re.compile(r"/scripts/Toyota_OneApp_EU\.([A-Za-z_]+)\.([A-Za-z0-9_]+)\.mvc\.js$")
_FETCH_CONCURRENCY = 8
_FETCH_TIMEOUT = aiohttp.ClientTimeout(total=20)


@dataclass(frozen=True)
class Manifest:
    version: str
    sequence: int | None
    files: dict[str, str]

    @classmethod
    def from_json(cls, data: dict) -> Manifest | None:
        files = data.get("urlVersions")
        version = data.get("versionToken")
        if not isinstance(files, dict) or not version:
            return None
        seq = data.get("versionSequence")
        return cls(str(version), seq if isinstance(seq, int) else None, files)

    def script_for_module(self, path: str) -> str | None:
        """Script that defines an action: ``Mod/Flow/Screen/Action`` -> ``Mod.Flow.Screen.mvc.js``."""
        parts = path.split("/")
        if len(parts) < 4:
            return None
        name = ".".join(parts[:-1])
        key = f"/Toyota_OneApp_EU/scripts/{name}.mvc.js"
        return key if key in self.files else None

    def screens(self) -> list[str]:
        """All screen names of the app (``Flow.Screen``), read from file names only."""
        out = []
        for key in self.files:
            m = _SCREEN_FILE.search(key)
            if m:
                out.append(f"{m.group(1)}.{m.group(2)}")
        return sorted(set(out))


def candidate_screens(manifest: Manifest, current: str, limit: int = 5) -> list[str]:
    """Same screen name under another flow, e.g. ``NewDesign_TLAC.MyToyota_V3`` -> ``UI_MyToyota.MyToyota_V3``.

    Renames observed so far only changed the flow prefix, so this keeps the number of probes tiny.
    """
    leaf = current.split(".", 1)[-1]
    return [s for s in manifest.screens() if s != current and s.split(".", 1)[-1] == leaf][:limit]


async def fetch_manifest(session: aiohttp.ClientSession, base_url: str, user_agent: str) -> Manifest | None:
    try:
        async with session.get(
            f"{base_url}/precache.manifest", timeout=_FETCH_TIMEOUT, headers={"User-Agent": user_agent}
        ) as r:
            r.raise_for_status()
            return Manifest.from_json(await r.json(content_type=None))
    except (TimeoutError, aiohttp.ClientError, ValueError, AttributeError) as err:
        _LOGGER.debug("precache.manifest unavailable: %s", err)
        return None


async def _fetch_script(
    session: aiohttp.ClientSession, base_origin: str, key: str, version_suffix: str, user_agent: str
) -> str | None:
    try:
        async with session.get(
            f"{base_origin}{key}{version_suffix}", timeout=_FETCH_TIMEOUT, headers={"User-Agent": user_agent}
        ) as r:
            if r.status != 200:
                return None
            return await r.text(errors="ignore")
    except (TimeoutError, aiohttp.ClientError):
        return None


async def discover_hashes(
    session: aiohttp.ClientSession,
    manifest: Manifest,
    base_origin: str,
    paths: list[str],
    user_agent: str,
) -> dict[str, str]:
    """Map each requested action ``path`` to the ``apiVersion`` currently published by the app.

    Paths whose script is missing or no longer defines the action are simply absent from the result.
    """
    by_script: dict[str, list[str]] = {}
    for p in paths:
        key = manifest.script_for_module(p)
        if key:
            by_script.setdefault(key, []).append(p)
    sem = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async def one(key: str) -> tuple[str, str | None]:
        async with sem:
            return key, await _fetch_script(session, base_origin, key, manifest.files[key], user_agent)

    found: dict[str, str] = {}
    for _key, text in await asyncio.gather(*(one(k) for k in by_script)):
        if not text:
            continue
        published = {p: v for p, v in _ACTION.findall(text)}
        for p in by_script[_key]:
            if p in published:
                found[p] = published[p]
    return found
