import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import Unauthorized

from custom_components.scottibyte_incus import websocket as ws
from custom_components.scottibyte_incus.const import DOMAIN


@pytest.mark.parametrize("handler", [ws.inventory, ws.dashboard, ws.server_order, ws.refresh, ws.action, ws.terminal_open, ws.terminal_input])
def test_non_admin_cannot_call_any_backend_endpoint(handler):
    connection = SimpleNamespace(user=SimpleNamespace(is_admin=False))
    with pytest.raises(Unauthorized):
        handler(None, connection, {"id": 1})


class Connection:
    def __init__(self):
        self.user = SimpleNamespace(is_admin=True, id="admin")
        self.results = []
        self.errors = []

    def send_result(self, *args):
        self.results.append(args)

    def send_error(self, *args):
        self.errors.append(args)


async def call_original(handler, *args):
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__
    return await handler(*args)


@pytest.mark.asyncio
async def test_terminal_session_is_bound_to_original_connection():
    owner = Connection()
    intruder = Connection()
    session = SimpleNamespace(write=AsyncMock())
    hass = SimpleNamespace(data={DOMAIN: {"terminals": {"secret": {"owner": owner, "session": session}}}})
    await call_original(ws.terminal_input, hass, intruder, {"id": 1, "session": "secret", "data": "aWQK"})
    assert intruder.errors and not session.write.called


@pytest.mark.asyncio
async def test_unknown_instance_and_offline_server_cannot_be_managed():
    coordinator = SimpleNamespace(snapshot={"online": False, "instances": []})
    hass = SimpleNamespace(data={DOMAIN: {"coordinators": {"server": coordinator}}})
    with pytest.raises(Exception, match="unavailable"):
        ws.coordinator_for(hass, {"server": "server", "name": "unknown", "project": "default"})
    coordinator.snapshot["online"] = True
    with pytest.raises(Exception, match="not in the configured inventory"):
        ws.coordinator_for(hass, {"server": "server", "name": "unknown", "project": "default"})


@pytest.mark.asyncio
async def test_server_order_saved_and_invalid_order_rejected():
    store = SimpleNamespace(async_save=AsyncMock())
    data = {"dashboard_store": store, "dashboard": {}, "dashboard_lock": asyncio.Lock()}
    hass = SimpleNamespace(data={DOMAIN: data}, config_entries=SimpleNamespace(
        async_entries=lambda domain: [SimpleNamespace(entry_id="storm"), SimpleNamespace(entry_id="mist")]))
    connection = Connection()
    await call_original(ws.server_order, hass, connection, {"id": 1, "order": ["mist", "storm"]})
    assert data["dashboard"]["server_order"] == ["mist", "storm"]
    store.async_save.assert_awaited_once_with({"server_order": ["mist", "storm"]})
    for order in (["unknown"], ["storm", "storm"]):
        await call_original(ws.server_order, hass, connection, {"id": 2, "order": order})
    assert len(connection.errors) == 2
    assert store.async_save.await_count == 1
