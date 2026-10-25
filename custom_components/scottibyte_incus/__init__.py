"""ScottiBYTE Incus integration and bundled dashboard."""

import asyncio
import shutil
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv

from . import websocket
from .api import IncusClient, make_ssl_context
from .bootstrap import api_url
from .const import DOMAIN, PANEL_URL, PLATFORMS, STATIC_URL, VERSION
from .coordinator import IncusCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass, config):
    hass.data[DOMAIN] = {"coordinators": {}, "terminals": {}, "locks": {}}
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
        await client.close()
        raise
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await websocket.close_terminals(hass, entry.entry_id)
    coordinator = hass.data[DOMAIN]["coordinators"].pop(entry.entry_id)
    await coordinator.client.close()
    if not hass.data[DOMAIN]["coordinators"]:
        # Keep the panel registered: adding a new server needs no restart.
        pass
    return True


async def async_remove_entry(hass, entry):
    """Remove local credentials; remote trust revocation is documented separately."""
    directory = Path(hass.config.path(".storage", DOMAIN, entry.data["credential_id"]))
    await hass.async_add_executor_job(shutil.rmtree, directory, True)
    from homeassistant.helpers.storage import Store

    await Store(hass, 1, f"{DOMAIN}.inventory.{entry.entry_id}").async_remove()
