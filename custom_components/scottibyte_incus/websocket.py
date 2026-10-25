"""Administrator-only dashboard API and connection-bound terminal subscriptions."""

import asyncio
import base64
import logging
import secrets
import time
from contextlib import suppress
from datetime import datetime, timezone
from uuid import uuid4

import aiohttp

try:
    import probatio as vol
except ImportError:  # Home Assistant versions before the schema migration
    import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback

from .api import IncusError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
TARGET = {vol.Required("server"): str, vol.Required("project"): str, vol.Required("name"): str}
DIMENSIONS = {
    vol.Optional("cols", default=100): vol.All(int, vol.Range(min=20, max=500)),
    vol.Optional("rows", default=30): vol.All(int, vol.Range(min=5, max=200)),
}


def coordinator_for(hass, msg):
    coordinator = hass.data[DOMAIN]["coordinators"].get(msg["server"])
    if coordinator is None or not coordinator.snapshot["online"]:
        raise IncusError("Server is unavailable")
    if not any(i["name"] == msg["name"] and i["project"] == msg["project"] for i in coordinator.snapshot["instances"]):
        raise IncusError("Instance is not in the configured inventory")
    return coordinator


def safe_error(connection, msg, error):
    # Certificate/SSH/token material is never returned. Incus API errors concern the requested action.
    message = (
        str(error)
        if isinstance(error, IncusError)
        else "Connection failed; check server availability and certificate trust."
    )
    connection.send_error(msg["id"], "incus_error", message)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/inventory"})
@websocket_api.require_admin
@websocket_api.async_response
async def inventory(hass, connection, msg):
    connection.send_result(msg["id"], [c.public_data() for c in hass.data[DOMAIN]["coordinators"].values()])


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/dashboard"})
@websocket_api.require_admin
@websocket_api.async_response
async def dashboard(hass, connection, msg):
    connection.send_result(msg["id"], hass.data[DOMAIN]["dashboard"])


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/server_order", vol.Required("order"): [str]})
@websocket_api.require_admin
@websocket_api.async_response
async def server_order(hass, connection, msg):
    data = hass.data[DOMAIN]
    known = {entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)}
    order = msg["order"]
    if len(order) != len(set(order)) or any(value not in known for value in order):
        connection.send_error(msg["id"], "invalid_order", "Server list changed; refresh and try again.")
        return
    async with data["dashboard_lock"]:
        updated = {"server_order": order}
        await data["dashboard_store"].async_save(updated)
        data["dashboard"] = updated
    connection.send_result(msg["id"], updated)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/refresh"})
@websocket_api.require_admin
@websocket_api.async_response
async def refresh(hass, connection, msg):
    await asyncio.gather(*(c.async_request_refresh() for c in hass.data[DOMAIN]["coordinators"].values()))
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/action", **TARGET, vol.Required("action"): vol.In(["start", "stop"])}
)
@websocket_api.require_admin
@websocket_api.async_response
async def action(hass, connection, msg):
    try:
        coordinator = coordinator_for(hass, msg)
        identity = (msg["server"], msg["project"], msg["name"])
        locks = hass.data[DOMAIN]["locks"]
        lock = locks.setdefault(identity, asyncio.Lock())
        if lock.locked():
            raise IncusError("An operation is already running for this instance")
        async with lock:
            state = await coordinator.client.state(msg["project"], msg["name"])
            required = "Stopped" if msg["action"] == "start" else "Running"
            if state.get("status") != required:
                raise IncusError(f"Instance must be {required.lower()} for this action; refresh its status")
            _LOGGER.info(
                "Incus %s requested by HA user %s on %s/%s/%s",
                msg["action"],
                connection.user.id,
                coordinator.entry.title,
                msg["project"],
                msg["name"],
            )
            await coordinator.client.change_state(msg["project"], msg["name"], msg["action"])
            await coordinator.async_request_refresh()
        connection.send_result(msg["id"])
    except Exception as err:
        safe_error(connection, msg, err)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/snapshots", **TARGET})
@websocket_api.require_admin
@websocket_api.async_response
async def snapshots(hass, connection, msg):
    try:
        coordinator = coordinator_for(hass, msg)
        connection.send_result(msg["id"], await coordinator.client.snapshots(msg["project"], msg["name"]))
    except Exception as err:
        safe_error(connection, msg, err)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/snapshot_action", **TARGET,
    vol.Required("action"): vol.In(["create", "rename", "delete", "restore"]),
    vol.Optional("snapshot", default=""): str, vol.Optional("new_name", default=""): str})
@websocket_api.require_admin
@websocket_api.async_response
async def snapshot_action(hass, connection, msg):
    try:
        coordinator = coordinator_for(hass, msg)
        identity = (msg["server"], msg["project"], msg["name"])
        lock = hass.data[DOMAIN]["locks"].setdefault(identity, asyncio.Lock())
        if lock.locked():
            raise IncusError("An operation is already running for this instance")
        async with lock:
            state = await coordinator.client.state(msg["project"], msg["name"])
            if msg["action"] == "restore" and state.get("status") != "Stopped":
                raise IncusError("Stop the instance before restoring a snapshot")
            if msg["action"] == "create" and state.get("status") not in ("Running", "Stopped"):
                raise IncusError("Instance must be running or stopped to create a snapshot")
            snapshot = msg.get("snapshot", "").strip()
            if msg["action"] == "create" and not snapshot:
                snapshot = datetime.now(timezone.utc).strftime("ha-%Y%m%d-%H%M%S-") + uuid4().hex[:6]
            if msg["action"] != "create":
                items = await coordinator.client.snapshots(msg["project"], msg["name"])
                if not any(item["name"] == snapshot for item in items):
                    raise IncusError("Snapshot no longer exists; refresh the list")
            _LOGGER.info("Incus snapshot %s requested by HA user %s on %s/%s/%s", msg["action"], connection.user.id, *identity)
            await coordinator.client.snapshot_action(msg["project"], msg["name"], msg["action"], snapshot, msg.get("new_name", "").strip())
            if msg["action"] == "restore":
                coordinator._sample_at = None
            await coordinator.async_request_refresh()
        connection.send_result(msg["id"], {"snapshot": snapshot})
    except Exception as err:
        safe_error(connection, msg, err)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/terminal_open", **TARGET, **DIMENSIONS})
@websocket_api.require_admin
@websocket_api.async_response
async def terminal_open(hass, connection, msg):
    record = None
    terminals = hass.data[DOMAIN]["terminals"]
    try:
        coordinator = coordinator_for(hass, msg)
        if len(terminals) >= 10 or sum(r["owner"].user.id == connection.user.id for r in terminals.values()) >= 2:
            raise IncusError("Terminal limit reached; close another terminal first")
        item = next(
            i for i in coordinator.snapshot["instances"] if i["name"] == msg["name"] and i["project"] == msg["project"]
        )
        if item["type"] != "container":
            raise IncusError("Version one supports terminals for containers only")
        token = secrets.token_urlsafe(32)
        # Reserve before awaiting connection: concurrent opens cannot bypass the limit.
        record = {
            "owner": connection,
            "server": msg["server"],
            "session": None,
            "task": asyncio.current_task(),
            "last_input": time.monotonic(),
            "created": time.monotonic(),
        }
        terminals[token] = record

        @callback
        def unsubscribe():
            if record["task"]:
                record["task"].cancel()

        connection.subscriptions[msg["id"]] = unsubscribe
        state = await coordinator.client.state(msg["project"], msg["name"])
        if state.get("status") != "Running":
            raise IncusError("Start the container before opening its terminal")
        record["session"] = await coordinator.client.terminal(msg["project"], msg["name"], msg["cols"], msg["rows"])
        _LOGGER.info(
            "Incus root terminal opened by HA user %s on %s/%s/%s",
            connection.user.id,
            coordinator.entry.title,
            msg["project"],
            msg["name"],
        )

        connection.send_result(msg["id"])
        connection.send_event(msg["id"], {"session": token})

        async def pump():
            try:
                while True:
                    if not connection.user.is_admin or not connection.user.is_active:
                        break
                    if time.monotonic() - record["last_input"] > 900 or time.monotonic() - record["created"] > 14400:
                        break
                    try:
                        frame = await asyncio.wait_for(record["session"].data.receive(), 30)
                    except TimeoutError:
                        await record["session"].data.ping()
                        continue
                    if frame.type == aiohttp.WSMsgType.BINARY:
                        connection.send_event(msg["id"], {"data": base64.b64encode(frame.data).decode()})
                    elif frame.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            finally:
                terminals.pop(token, None)
                await record["session"].close()
                connection.subscriptions.pop(msg["id"], None)
                with suppress(Exception):
                    connection.send_event(msg["id"], {"closed": True})

        record["task"] = hass.async_create_background_task(pump(), "Incus terminal")
    except BaseException as err:
        if record:
            connection.subscriptions.pop(msg["id"], None)
            terminals.pop(token, None)
            if record["session"]:
                await record["session"].close()
        if isinstance(err, asyncio.CancelledError):
            raise
        safe_error(connection, msg, err)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/terminal_input",
        vol.Required("session"): str,
        vol.Optional("data"): vol.All(str, vol.Length(max=90000)),
        **DIMENSIONS,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def terminal_input(hass, connection, msg):
    try:
        record = hass.data[DOMAIN]["terminals"].get(msg["session"])
        if record is None or record["owner"] is not connection or record["session"] is None:
            raise IncusError("Terminal session has expired")
        record["last_input"] = time.monotonic()
        if "data" in msg:
            try:
                data = base64.b64decode(msg["data"], validate=True)
            except ValueError as err:
                raise IncusError("Invalid terminal input") from err
            if len(data) > 65536:
                raise IncusError("Terminal input is too large")
            await record["session"].write(data)
        else:
            await record["session"].resize(msg["cols"], msg["rows"])
        connection.send_result(msg["id"])
    except Exception as err:
        safe_error(connection, msg, err)


async def close_terminals(hass, server=None):
    records = [r for r in hass.data[DOMAIN]["terminals"].values() if server is None or r["server"] == server]
    tasks = []
    for record in records:
        if record["task"]:
            record["task"].cancel()
            tasks.append(record["task"])
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@callback
def register(hass):
    for handler in (inventory, dashboard, server_order, refresh, action, snapshots, snapshot_action, terminal_open, terminal_input):
        websocket_api.async_register_command(hass, handler)
