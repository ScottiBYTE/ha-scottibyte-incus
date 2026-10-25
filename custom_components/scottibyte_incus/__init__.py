"""ScottiBYTE Incus integration and bundled dashboard."""

import asyncio
import logging
import shutil
from pathlib import Path

from homeassistant.components import panel_custom, persistent_notification
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from . import websocket
from .api import IncusClient, certificate_fingerprint, make_ssl_context
from .bootstrap import api_url
from .const import DOMAIN, PANEL_URL, PLATFORMS, STATIC_URL, VERSION
from .coordinator import IncusCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass, config):
    hass.data[DOMAIN] = {"coordinators": {}, "terminals": {}, "locks": {}}
    dashboard_store = Store(hass, 1, f"{DOMAIN}.dashboard")
    hass.data[DOMAIN]["dashboard_store"] = dashboard_store
    hass.data[DOMAIN]["dashboard"] = await dashboard_store.async_load() or {"server_order": []}
    hass.data[DOMAIN]["dashboard_lock"] = asyncio.Lock()
    websocket.register(hass)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), cache_headers=False)]
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="scottibyte-incus-panel",
        sidebar_title="Incus",
        sidebar_icon="mdi:server-network",
        module_url=f"{STATIC_URL}/panel.js?v={VERSION}",
        require_admin=True,
        embed_iframe=False,
    )

    async def shutdown(event):
        await asyncio.gather(*(c.dns.close() for c in hass.data[DOMAIN]["coordinators"].values()))
        await websocket.close_terminals(hass)
        await asyncio.gather(*(c.client.close() for c in hass.data[DOMAIN]["coordinators"].values()))

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown)
    return True


async def async_setup_entry(hass, entry):
    directory = Path(hass.config.path(".storage", DOMAIN, entry.data["credential_id"]))

    def context():
        return make_ssl_context(
            (directory / "server.crt").read_text(), directory / "client.crt", directory / "client.key"
        )

    client = IncusClient(
        api_url(entry.data["host"], entry.data["api_port"]), await hass.async_add_executor_job(context)
    )
    coordinator = IncusCoordinator(hass, entry, client)
    try:
        await coordinator.load_snapshot()
        await coordinator.async_config_entry_first_refresh()
        # Upgrade only the old generic label; preserve deliberately chosen names.
        if entry.title.strip().casefold() == "incus":
            detected_name = str(coordinator.snapshot.get("server_name") or entry.data.get("server_name") or "").strip()
            if detected_name and detected_name.casefold() != "incus":
                hass.config_entries.async_update_entry(entry, title=detected_name)
        hass.data[DOMAIN]["coordinators"][entry.entry_id] = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        hass.data[DOMAIN]["coordinators"].pop(entry.entry_id, None)
        await coordinator.dns.close()
        await client.close()
        raise
    return True


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await websocket.close_terminals(hass, entry.entry_id)
    coordinator = hass.data[DOMAIN]["coordinators"].pop(entry.entry_id)
    await coordinator.dns.close()
    await coordinator.client.close()
    if not hass.data[DOMAIN]["coordinators"]:
        # Keep the panel registered: adding a new server needs no restart.
        pass
    return True


async def async_remove_entry(hass, entry):
    """Revoke only this entry's identity; allow local removal if unreachable."""
    directory = Path(hass.config.path(".storage", DOMAIN, entry.data["credential_id"]))
    client = None
    fingerprint = None

    def credentials():
        fingerprint = certificate_fingerprint((directory / "client.crt").read_text())
        context = make_ssl_context((directory / "server.crt").read_text(), directory / "client.crt", directory / "client.key")
        return fingerprint, context

    try:
        fingerprint, context = await hass.async_add_executor_job(credentials)
        client = IncusClient(api_url(entry.data["host"], entry.data["api_port"]), context)
        await client.request("DELETE", f"/1.0/certificates/{fingerprint}", timeout=10)
    except Exception:
        _LOGGER.warning("Could not revoke remote trust for removed Incus server %s", entry.title)
        persistent_notification.async_create(
            hass,
            f"Server {entry.title} was removed from Home Assistant, but its remote trust could not be revoked. "
            f"On that Incus server, inspect `incus config trust list` and remove only the matching certificate "
            f"with `incus config trust remove {fingerprint or '<matching fingerprint>'}`. Guests are unaffected.",
            title="Incus trust cleanup required",
            notification_id=f"{DOMAIN}_trust_{entry.entry_id}",
        )
    finally:
        if client:
            await client.close()
    await hass.async_add_executor_job(shutil.rmtree, directory, True)
    await Store(hass, 1, f"{DOMAIN}.inventory.{entry.entry_id}").async_remove()
