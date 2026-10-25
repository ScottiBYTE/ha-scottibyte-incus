"""Small asynchronous Incus API client with pinned server certificate trust."""

import asyncio
import hashlib
import re
import ssl
import time
from contextlib import suppress
from urllib.parse import quote

import aiohttp


class IncusError(Exception):
    """An Incus request failed."""


def path_segment(value):
    return quote(value, safe="")


def make_ssl_context(server_pem, cert_path, key_path):
    """Trust only the enrolled server certificate (including self-signed servers)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False  # Identity was pinned during enrollment.
    context.load_verify_locations(cadata=server_pem)
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    context.load_cert_chain(cert_path, key_path)
    return context


def certificate_fingerprint(pem):
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()


class IncusClient:
    def __init__(self, url, context):
        self._cpu_cache = {}
        self.url = url.rstrip("/")
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=context),
            timeout=aiohttp.ClientTimeout(total=25),
        )

    async def close(self):
        await self.session.close()

    async def request(self, method, path, *, params=None, payload=None, timeout=None):
        if not path.startswith("/1.0") or "://" in path or ".." in path:
            raise IncusError("Invalid Incus API path")
        kwargs = {"params": params, "json": payload, "allow_redirects": False}
        if timeout is not None:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout)
        async with self.session.request(method, self.url + path, **kwargs) as response:
            if response.status in (301, 302, 303, 307, 308):
                raise IncusError("Incus redirects are not accepted; use the direct server address")
            data = await response.json()
            if response.status >= 400 or data.get("type") == "error":
                raise IncusError(data.get("error") or f"Incus returned HTTP {response.status}")
            return data

    async def metadata(self, path, **kwargs):
        return (await self.request("GET", path, **kwargs))["metadata"]

    async def inventory(self, projects):
        info = await self.metadata("/1.0")
        if info.get("auth") != "trusted":
            raise IncusError("Home Assistant certificate is not trusted")
        if projects == ["*"]:
            projects = [p["name"] for p in await self.metadata("/1.0/projects", params={"recursion": 1})]
        rows = []
        # Bounded parallelism across projects, no per-instance request fan-out.
        semaphore = asyncio.Semaphore(3)

        async def fetch(project):
            async with semaphore:
                items = await self.metadata("/1.0/instances", params={"recursion": 2, "project": project})
                return [(project, item) for item in items]

        for items in await asyncio.gather(*(fetch(p) for p in projects)):
            rows.extend(items)
        locations = {str(item.get("location") or "") for _, item in rows}
        if not info.get("environment", {}).get("server_clustered"):
            locations = {""}
        capacities = {}

        async def capacity(location):
            if location == "none":
                location = ""
            if not location and info.get("environment", {}).get("server_clustered"):
                return location, None
            cached = self._cpu_cache.get(location)
            if cached and cached[1] > time.monotonic():
                return location, cached[0]
            try:
                async with semaphore:
                    resources = await self.metadata("/1.0/resources", params={"target": location} if location else None, timeout=5)
                cpu = resources.get("cpu") or {}
                threads = [thread for socket in cpu.get("sockets", []) for core in socket.get("cores", []) for thread in core.get("threads", [])]
                count = sum(thread.get("online", True) for thread in threads) if threads else cpu.get("total")
                count = int(count) if count and int(count) > 0 else None
            except (IncusError, aiohttp.ClientError, TimeoutError, TypeError, ValueError):
                count = None
            self._cpu_cache[location] = (count, time.monotonic() + (300 if count else 60))
            return location, count

        for location, count in await asyncio.gather(*(capacity(location) for location in locations)):
            capacities[location] = count
        info["host_cpu_counts"] = capacities
        return info, rows

    async def state(self, project, name):
        return await self.metadata(f"/1.0/instances/{path_segment(name)}/state", params={"project": project})

    async def change_state(self, project, name, action):
        if action not in ("start", "stop"):
            raise IncusError("Unsupported action")
        result = await self.request(
            "PUT",
            f"/1.0/instances/{path_segment(name)}/state",
            params={"project": project},
            payload={"action": action, "timeout": 60, "force": False},
        )
        if result.get("operation"):
            operation = await self.metadata(
                result["operation"] + "/wait", params={"timeout": 75, "project": project}, timeout=85
            )
            if operation.get("status_code") != 200:
                raise IncusError(operation.get("err") or "Incus operation failed")

    async def snapshots(self, project, name):
        items = await self.metadata(f"/1.0/instances/{path_segment(name)}/snapshots", params={"project": project, "recursion": 1})
        return [{"name": item["name"].removeprefix(name + "/"), "created_at": item.get("created_at"),
                 "expires_at": item.get("expires_at"), "stateful": item.get("stateful", False)} for item in items]

    async def snapshot_action(self, project, name, action, snapshot, new_name=""):
        for value in (snapshot, new_name) if action == "rename" else (snapshot,):
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}", value) or ".." in value:
                raise IncusError("Use a snapshot name of 1–63 letters, digits, dots, underscores or hyphens; no consecutive dots")
        base = f"/1.0/instances/{path_segment(name)}"
        if action == "create":
            method, path, payload = "POST", base + "/snapshots", {"name": snapshot, "stateful": False}
        elif action == "rename":
            method, path, payload = "POST", base + "/snapshots/" + path_segment(snapshot), {"name": new_name}
        elif action == "delete":
            method, path, payload = "DELETE", base + "/snapshots/" + path_segment(snapshot), None
        elif action == "restore":
            method, path, payload = "PUT", base, {"restore": snapshot, "stateful": False}
        else:
            raise IncusError("Unknown snapshot action")
        result = await self.request(method, path, params={"project": project}, payload=payload)
        if result.get("operation"):
            operation = await self.metadata(result["operation"] + "/wait", params={"project": project, "timeout": 300}, timeout=310)
            if operation.get("status_code") != 200:
                raise IncusError(operation.get("err") or "Snapshot operation did not complete; refresh before retrying")

    async def terminal(self, project, name, cols, rows):
        result = await self.request(
            "POST",
            f"/1.0/instances/{path_segment(name)}/exec",
            params={"project": project},
            payload={
                "command": [
                    "/bin/sh",
                    "-c",
                    "if command -v bash >/dev/null 2>&1; then exec bash -l; else exec /bin/sh -l; fi",
                ],
                "interactive": True,
                "wait-for-websocket": True,
                "environment": {"TERM": "xterm-256color", "HOME": "/root", "USER": "root"},
                "user": 0,
                "group": 0,
                "cwd": "/",
                "width": cols,
                "height": rows,
            },
        )
        operation = result["operation"]
        fds = result["metadata"]["metadata"]["fds"]
        sockets = await asyncio.gather(
            *(
                self.session.ws_connect(
                    self.url + operation + "/websocket",
                    params={"secret": fds[fd], "project": project},
                    max_msg_size=1024 * 1024,
                )
                for fd in ("control", "0")
            ),
            return_exceptions=True,
        )
        errors = [sock for sock in sockets if isinstance(sock, BaseException)]
        if errors:
            for sock in sockets:
                if not isinstance(sock, BaseException):
                    await sock.close()
            raise errors[0]
        return TerminalSession(*sockets)


class TerminalSession:
    """An interactive exec's control and PTY websockets."""

    def __init__(self, control, data):
        self.control, self.data = control, data
        self.closed = False

    async def resize(self, cols, rows):
        await self.control.send_json({"command": "window-resize", "args": {"width": str(cols), "height": str(rows)}})

    async def write(self, data):
        await self.data.send_bytes(data)

    async def close(self):
        if self.closed:
            return
        self.closed = True
        # SIGHUP the shell before disconnecting so sessions do not accumulate.
        with suppress(Exception):
            await self.control.send_json({"command": "signal", "signal": 1})
        await self.data.close()
        await self.control.close()
